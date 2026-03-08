#!/usr/bin/env bash
# Check forbidden patterns — PRの変更ファイルから禁止パターンを検出
#
# 入力（環境変数）:
#   PR_NUMBER          — 対象PR番号
#   FORBIDDEN_PATTERNS — 禁止パターン（改行区切りのglob。例: ".env*\npyproject.toml"）
#   GITHUB_OUTPUT      — GitHub Actions 出力ファイル
#   GH_TOKEN           — GitHub トークン（env経由で gh CLI が自動参照）
#
# 出力（$GITHUB_OUTPUT）:
#   forbidden       — "true" / "false"
#   forbidden_files  — 禁止パターンに該当したファイル一覧（multiline）
#
# エラー方針: ファイル一覧取得失敗 → exit 1（セキュリティ処理のため安全側）

set -euo pipefail
# 動的パス解決のため静的解析不可
# shellcheck disable=SC1091
source "$(dirname "$0")/_common.sh"

require_env PR_NUMBER FORBIDDEN_PATTERNS GITHUB_OUTPUT

# PRの変更ファイル一覧を取得
# 方針: セキュリティ必須処理の失敗 → exit 1（禁止パターンチェックのバイパス防止）
if ! CHANGED_FILES=$(gh pr view "$PR_NUMBER" --json files --jq '.files[].path' 2>&1); then
  echo "::error::Failed to get changed files: $CHANGED_FILES"
  exit 1
fi

FORBIDDEN_FOUND=""

while IFS= read -r file; do
  [ -z "$file" ] && continue

  while IFS= read -r pattern; do
    [ -z "$pattern" ] && continue
    # glob パターンマッチ（extglob 不使用。*, ?, [] に対応）
    # Intentional: unquoted $pattern for glob matching
    # shellcheck disable=SC2053
    if [[ "$file" == $pattern ]]; then
      FORBIDDEN_FOUND="${FORBIDDEN_FOUND}${file}\n"
      break
    fi
  done <<< "$FORBIDDEN_PATTERNS"

done <<< "$CHANGED_FILES"

if [ -n "$FORBIDDEN_FOUND" ]; then
  echo "forbidden=true" >> "$GITHUB_OUTPUT"
  FORBIDDEN_LIST=$(printf '%b' "$FORBIDDEN_FOUND" | head -c 1000)
  {
    echo "forbidden_files<<EOF"
    echo "$FORBIDDEN_LIST"
    echo "EOF"
  } >> "$GITHUB_OUTPUT"
  echo "::warning::Forbidden patterns found"
else
  echo "forbidden=false" >> "$GITHUB_OUTPUT"
  echo "No forbidden patterns found"
fi
