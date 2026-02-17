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

# tool_input.command を抽出
if command -v jq > /dev/null 2>&1; then
  COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)
else
  COMMAND=$(echo "$INPUT" | grep -o '"command"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed 's/.*"command"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/')
fi

if [ -z "$COMMAND" ]; then
  exit 0
fi

# 危険パターンの検出
# gh <subcommand> delete の形式をチェック
BLOCKED=""
case "$COMMAND" in
  *"gh issue delete"*)  BLOCKED="gh issue delete（Issue の完全削除）" ;;
  *"gh repo delete"*)   BLOCKED="gh repo delete（リポジトリの完全削除）" ;;
  *"gh release delete"*) BLOCKED="gh release delete（リリースの削除）" ;;
  *"gh label delete"*)  BLOCKED="gh label delete（ラベルの削除）" ;;
esac

if [ -n "$BLOCKED" ]; then
  echo "{\"hookSpecificOutput\": {\"hookEventName\": \"PreToolUse\", \"permissionDecision\": \"deny\", \"permissionDecisionReason\": \"destructive-command-guard: $BLOCKED は取り消し不能な破壊コマンドのためブロックしました。本当に実行する場合はターミナルから直接実行してください。\"}}"
  exit 0
fi

exit 0
