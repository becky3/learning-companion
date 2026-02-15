#!/bin/bash
# Leader Guard - チーム運用中のリーダーによる Edit/Write 使用をブロックするフック
# PreToolUse フックとして実行される
# stdin から JSON を読み取り、permission_mode でリーダー/メンバーを判別する
# エラー時は fail-open（ブロックしない）: 運用支援ツールであり、ユーザーの作業を止めない
# 仕様: docs/specs/agent-teams/common.md（delegate モードセクション）
#
# 注意: このスクリプトはフォールバック（delegate モード未使用時の警告）として残している。
# 主たるリーダー制約手段は delegate モード（Shift+Tab）を使用すること。
# permissions.allow に Edit/Write が含まれている場合、本フックの deny が
# 自動許可に上書きされる可能性がある（#258）。

# stdin から JSON を読み取る
INPUT=$(cat)

# [4] stdin 読み取り失敗時は fail-open
if [ -z "$INPUT" ]; then
    echo "leader-guard: stdin が空です。PreToolUseフックへの入力がありません（fail-open）" >&2
    exit 0
fi

# permission_mode を抽出（jq があれば使う、なければ grep/sed）
if command -v jq > /dev/null 2>&1; then
    PERMISSION_MODE=$(echo "$INPUT" | jq -r '.permission_mode // empty')
else
    GREP_RESULT=$(echo "$INPUT" | grep -o '"permission_mode"[[:space:]]*:[[:space:]]*"[^"]*"') || true
    if [ -z "$GREP_RESULT" ]; then
        echo "leader-guard: grep による permission_mode の抽出に失敗しました（fail-open）" >&2
        exit 0
    fi
    PERMISSION_MODE=$(echo "$GREP_RESULT" | sed 's/.*"permission_mode"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/')
fi

# [3][5][8] permission_mode が空の場合は fail-open
if [ -z "$PERMISSION_MODE" ]; then
    echo "leader-guard: permission_mode フィールドが存在しないか空です（fail-open）" >&2
    echo "leader-guard: 受信した入力の先頭100文字: ${INPUT:0:100}" >&2
    exit 0
fi

# メンバー（bypassPermissions）なら何もしない
if [ "$PERMISSION_MODE" = "bypassPermissions" ]; then
    exit 0
fi

# [7] HOME 未定義チェック
if [ -z "$HOME" ]; then
    echo "leader-guard: HOME が未定義です（fail-open）" >&2
    exit 0
fi

# チームディレクトリの確認
TEAMS_DIR="$HOME/.claude/teams"

if [ ! -d "$TEAMS_DIR" ]; then
    exit 0
fi

# [6] ディレクトリの読み取り権限チェック
if [ ! -r "$TEAMS_DIR" ]; then
    echo "leader-guard: $TEAMS_DIR の読み取り権限がありません（fail-open）" >&2
    exit 0
fi

# サブディレクトリが1つでもあるか確認
shopt -s nullglob
has_teams=false
for entry in "$TEAMS_DIR"/*/; do
    if [ -d "$entry" ]; then
        has_teams=true
        break
    fi
done
shopt -u nullglob

if [ "$has_teams" = false ]; then
    exit 0
fi

# リーダー + チーム稼働中 → ブロック
echo '{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "⚠️ チーム運用中: リーダー管理専任ルールにより、Edit/Write の使用は原則禁止です。メンバーに委譲してください。"}}'

exit 0
