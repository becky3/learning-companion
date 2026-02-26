#!/bin/bash
# Leader Guard - チーム運用中のリーダーによる Edit/Write 使用をブロックするフック
# PreToolUse フックとして実行される
# stdin から JSON を読み取り、permission_mode でリーダー/メンバーを判別する
# エラー時は fail-open（ブロックしない）: 運用支援ツールであり、ユーザーの作業を止めない
# 仕様: docs/specs/agentic/teams/common.md（delegate モードセクション）
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
    # sed capture group extraction cannot be replaced with ${var//search/replace}
    # shellcheck disable=SC2001
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

# サブディレクトリが1つでもあるか確認し、最初に見つかったチームの pattern を取得する
# 仕様: 1セッション1チームのため、最初のエントリのみ処理する
shopt -s nullglob
TEAM_PATTERN=""
has_teams=false
for entry in "$TEAMS_DIR"/*/; do
    if [ -d "$entry" ]; then
        has_teams=true
        CONFIG_FILE="${entry}config.json"
        if [ -f "$CONFIG_FILE" ] && [ -r "$CONFIG_FILE" ]; then
            # config.json から pattern を抽出
            if command -v jq > /dev/null 2>&1; then
                TEAM_PATTERN=$(jq -r '.pattern // empty' "$CONFIG_FILE" 2>/dev/null)
            else
                PATTERN_GREP=$(grep -o '"pattern"[[:space:]]*:[[:space:]]*"[^"]*"' "$CONFIG_FILE" 2>/dev/null) || true
                if [ -n "$PATTERN_GREP" ]; then
                    # sed capture group extraction cannot be replaced with ${var//search/replace}
                    # shellcheck disable=SC2001
                    TEAM_PATTERN=$(echo "$PATTERN_GREP" | sed 's/.*"pattern"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/')
                fi
            fi
        fi
        break
    fi
done
shopt -u nullglob

# チームが存在しない場合は何もしない
if [ "$has_teams" = false ]; then
    exit 0
fi

# チームは存在するが pattern 不明 → fixed-theme として扱う（安全側に倒す）
if [ -z "$TEAM_PATTERN" ]; then
    echo "leader-guard: pattern が取得できませんでした。fixed-theme として扱います" >&2
    TEAM_PATTERN="fixed-theme"
fi

# mixed-genius パターンではリーダーも作業するため、ブロックしない
if [ "$TEAM_PATTERN" = "mixed-genius" ]; then
    exit 0
fi

# fixed-theme パターン: リーダー + チーム稼働中 → ブロック
echo '{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "⚠️ チーム運用中: リーダー管理専任ルールにより、Edit/Write の使用は原則禁止です。メンバーに委譲してください。"}}'

exit 0
