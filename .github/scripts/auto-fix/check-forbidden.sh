#!/usr/bin/env bash
# Check forbidden patterns — PRの変更ファイルから禁止パターンを検出
#
# 入力（環境変数）:
#   PR_NUMBER       — 対象PR番号
#   GITHUB_OUTPUT   — GitHub Actions 出力ファイル
#   GH_TOKEN        — GitHub トークン（env経由で gh CLI が自動参照）
#   GH_REPO         — 対象リポジトリ（owner/repo）
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

require_env PR_NUMBER GITHUB_OUTPUT

# PRの変更ファイル一覧を取得
# 方針: セキュリティ必須処理の失敗 → exit 1（禁止パターンチェックのバイパス防止）
if ! CHANGED_FILES=$(gh pr view "$PR_NUMBER" --json files --jq '.files[].path' 2>&1); then
  echo "::error::Failed to get changed files: $CHANGED_FILES"
  exit 1
fi

FORBIDDEN_FOUND=""

while IFS= read -r file; do
  [ -z "$file" ] && continue

  # .env*
  if [[ "$file" == .env* ]]; then
    FORBIDDEN_FOUND="${FORBIDDEN_FOUND}${file}\n"
    continue
  fi

  # pyproject.toml の dependencies 変更検出
  # gh pr diff はファイル指定不可のため、全 diff を取得して pyproject.toml セクションを抽出
  if [ "$file" = "pyproject.toml" ]; then
    if ! FULL_DIFF=$(gh pr diff "$PR_NUMBER" 2>&1); then
      echo "::error::Failed to get PR diff: $FULL_DIFF"
      # 安全側に倒す: diff取得失敗時は依存関係変更ありと見なす
      FORBIDDEN_FOUND="${FORBIDDEN_FOUND}${file} (diff取得失敗のため要手動確認)\n"
      continue
    fi
    # pyproject.toml の diff セクションを抽出（b/ パスでマッチし、リネームケースも検出）
    PYPROJECT_DIFF=$(echo "$FULL_DIFF" | sed -n '/^diff --git [^ ]* b\/pyproject\.toml/,/^diff --git/{/^diff --git [^ ]* b\/pyproject\.toml/p;/^diff --git [^ ]* b\/pyproject\.toml/!{/^diff --git/!p}}')
    # 追加行・削除行の両方を対象にする（セクションヘッダと代入のみ検出、コメント等の誤検知を防止）
    if echo "$PYPROJECT_DIFF" | grep -qE '^[+-]\s*(dependencies\s*=|\[project\.dependencies\]|\[dependency-groups\])'; then
      FORBIDDEN_FOUND="${FORBIDDEN_FOUND}${file} (dependencies変更)\n"
    fi
    continue
  fi

  # .github/workflows/* はチェック対象外（パイプラインが develop 向け PR のみ処理するため）

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
