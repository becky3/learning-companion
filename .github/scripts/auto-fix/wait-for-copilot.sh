#!/usr/bin/env bash
# Wait for Copilot -- Copilot レビュー完了を sleep ポーリングで検知
#
# 設計書: docs/specs/copilot-auto-fix.md (Section 2: Copilot レビュー検知)
#
# 入力（環境変数）:
#   PR_NUMBER               -- 対象PR番号（必須）
#   GH_TOKEN                -- GitHub トークン（必須、env経由で gh CLI が自動参照）
#   GH_REPO                 -- 対象リポジトリ owner/repo（必須）
#   GITHUB_OUTPUT           -- GitHub Actions 出力ファイル（必須）
#   COPILOT_REVIEW_TIMEOUT  -- 最大待機時間（秒）。デフォルト: 600
#
# 出力:
#   copilot_reviewed=true|false（$GITHUB_OUTPUT 経由）
#
# 終了コード:
#   0 — タイムアウト or 正常検知（copilot_reviewed で呼び出し元が判断）
#   1 — 回復不能エラー（権限/認証エラー）
# API エラー:
#   認証/権限エラー（401/403/forbidden/resource not accessible）→ exit 1（即停止）
#   一時的障害 → warning を出力して次のポーリングへ（耐性）

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# 動的パス解決のため静的解析不可
# shellcheck disable=SC1091
source "$SCRIPT_DIR/_common.sh"

require_env PR_NUMBER GH_TOKEN GH_REPO GITHUB_OUTPUT
validate_pr_number "$PR_NUMBER" "PR_NUMBER"

TIMEOUT="${COPILOT_REVIEW_TIMEOUT:-600}"
POLL_INTERVAL=30

if ! validate_numeric "$TIMEOUT" "COPILOT_REVIEW_TIMEOUT"; then
  echo "::warning::Invalid COPILOT_REVIEW_TIMEOUT, using default 600"
  TIMEOUT=600
fi

MAX_ATTEMPTS=$((TIMEOUT / POLL_INTERVAL))
echo "Polling for Copilot review on PR #$PR_NUMBER (interval: ${POLL_INTERVAL}s, timeout: ${TIMEOUT}s, max attempts: $MAX_ATTEMPTS)"

for ((i = 1; i <= MAX_ATTEMPTS; i++)); do
  echo "--- Attempt $i/$MAX_ATTEMPTS ---"

  # REST API でレビュー一覧を取得
  if ! REVIEWS=$(gh api "repos/${GH_REPO}/pulls/${PR_NUMBER}/reviews" 2>&1); then
    # 認証/権限エラー（回復不能）→ 即停止
    if echo "$REVIEWS" | grep -qiE "(401|403|authentication|forbidden|resource not accessible)"; then
      echo "::error::Permission/authentication error (non-recoverable): $REVIEWS"
      output "copilot_reviewed" "false"
      exit 1
    fi
    # 一時的 API 障害 → warning でリトライ
    echo "::warning::Failed to fetch reviews (attempt $i): $REVIEWS"
    sleep "$POLL_INTERVAL"
    continue
  fi

  # copilot-pull-request-reviewer[bot] のレビューで state != "PENDING" を検知
  if ! COPILOT_REVIEW_COUNT=$(echo "$REVIEWS" | jq '
    [.[] |
      select(.user.login == "copilot-pull-request-reviewer[bot]") |
      select(.state != "PENDING")
    ] | length
  ' 2>&1); then
    echo "::warning::Failed to parse reviews (attempt $i): $COPILOT_REVIEW_COUNT"
    sleep "$POLL_INTERVAL"
    continue
  fi

  if ! validate_numeric "$COPILOT_REVIEW_COUNT" "copilot review count"; then
    echo "::warning::Invalid review count (attempt $i): $COPILOT_REVIEW_COUNT"
    sleep "$POLL_INTERVAL"
    continue
  fi

  if [ "$COPILOT_REVIEW_COUNT" -gt 0 ]; then
    echo "Copilot review detected on PR #$PR_NUMBER ($COPILOT_REVIEW_COUNT reviews)"
    output "copilot_reviewed" "true"
    exit 0
  fi

  echo "No Copilot review yet. Waiting ${POLL_INTERVAL}s..."
  sleep "$POLL_INTERVAL"
done

echo "::warning::Copilot review not detected within ${TIMEOUT}s (${MAX_ATTEMPTS} attempts)"
output "copilot_reviewed" "false"
exit 0
