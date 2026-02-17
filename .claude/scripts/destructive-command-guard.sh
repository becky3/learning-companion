#!/bin/bash
# Destructive Command Guard - 取り消し不能な破壊コマンドをブロックするフック
# PreToolUse フック（matcher: Bash）として実行される
# stdin から JSON を読み取り、command フィールドに危険パターンが含まれていれば deny を返す
# エラー時は fail-open（ブロックしない）: leader-guard.sh と同じ設計方針
#
# ブロック対象:
#   gh issue delete  — Issue の完全削除（復元不可）
#   gh repo delete   — リポジトリの完全削除
#   gh release delete — リリースの削除
#   gh label delete  — ラベルの削除
#
# 背景: Issue #444 がローカル Claude Code セッションから誤削除された疑い (2026-02-17)

INPUT=$(cat)

if [ -z "$INPUT" ]; then
  exit 0
fi

# tool_input.command を抽出（jq 優先、なければ python3 フォールバック）
if command -v jq > /dev/null 2>&1; then
  COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)
elif command -v python3 > /dev/null 2>&1; then
  COMMAND=$(echo "$INPUT" | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("tool_input",{}).get("command",""))' 2>/dev/null)
elif command -v python > /dev/null 2>&1; then
  COMMAND=$(echo "$INPUT" | python -c 'import sys,json; d=json.load(sys.stdin); print(d.get("tool_input",{}).get("command",""))' 2>/dev/null)
else
  # jq も python もない環境では fail-open
  exit 0
fi

if [ -z "$COMMAND" ]; then
  exit 0
fi

# 危険パターンの検出
# gh <subcommand> delete の形式をチェック（先頭 or セパレータ後の gh 呼び出しを対象）
BLOCKED=""
if [[ "$COMMAND" =~ (^|[;\&\|])[[:space:]]*gh[[:space:]]+issue[[:space:]]+delete([[:space:]]|$) ]]; then
  BLOCKED="gh issue delete（Issue の完全削除）"
elif [[ "$COMMAND" =~ (^|[;\&\|])[[:space:]]*gh[[:space:]]+repo[[:space:]]+delete([[:space:]]|$) ]]; then
  BLOCKED="gh repo delete（リポジトリの完全削除）"
elif [[ "$COMMAND" =~ (^|[;\&\|])[[:space:]]*gh[[:space:]]+release[[:space:]]+delete([[:space:]]|$) ]]; then
  BLOCKED="gh release delete（リリースの削除）"
elif [[ "$COMMAND" =~ (^|[;\&\|])[[:space:]]*gh[[:space:]]+label[[:space:]]+delete([[:space:]]|$) ]]; then
  BLOCKED="gh label delete（ラベルの削除）"
fi

if [ -n "$BLOCKED" ]; then
  echo "{\"hookSpecificOutput\": {\"hookEventName\": \"PreToolUse\", \"permissionDecision\": \"deny\", \"permissionDecisionReason\": \"destructive-command-guard: $BLOCKED は取り消し不能な破壊コマンドのためブロックしました。本当に実行する場合はターミナルから直接実行してください。\"}}"
  exit 0
fi

exit 0
