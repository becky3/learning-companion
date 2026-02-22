#!/usr/bin/env bash
# resolve-threads.sh — PRの未解決レビュースレッドを resolve する
#
# 使い方:
#   PR_NUMBER=123 ./resolve-threads.sh              # 全未解決スレッドを resolve
#   PR_NUMBER=123 ./resolve-threads.sh PRRT_xxx PRRT_yyy  # 指定スレッドのみ resolve
#
# 入力:
#   環境変数 PR_NUMBER（必須）
#   引数: THREAD_ID のリスト（省略時は全未解決スレッドを取得して resolve）
#
# エラーハンドリング方針（_common.sh と統一）:
#   認証エラー (401/403)   → exit 1 で即停止
#   個別失敗              → ::warning:: でログし続行
#   全件失敗              → ::error:: + exit 1
#   スレッド0件           → ログ出力しスキップ

set -euo pipefail
# 動的パス解決のため静的解析不可
# shellcheck disable=SC1091
source "$(dirname "$0")/_common.sh"

require_env PR_NUMBER

# --- PR番号バリデーション ---
if ! validate_pr_number "$PR_NUMBER" "PR_NUMBER"; then
  exit 1
fi

# --- owner/repo 取得（認証/権限エラー → exit 1）---
OWNER=$(gh_safe gh repo view --json owner --jq '.owner.login')
REPO=$(gh_safe gh repo view --json name --jq '.name')

# --- THREAD_ID フォーマット検証関数 ---
# GitHub thread ID は Base64 エンコードされるため = も許容
validate_thread_id() {
  local id="$1"
  if ! [[ "$id" =~ ^[A-Za-z0-9_=-]+$ ]]; then
    echo "::warning::Invalid thread ID format: $id"
    return 1
  fi
}

# --- スレッドIDリストの決定 ---
if [ $# -gt 0 ]; then
  # 引数指定: 指定スレッドのみ resolve（即時バリデーション）
  THREADS=""
  INVALID_COUNT=0
  for arg in "$@"; do
    if [ -z "$arg" ]; then
      echo "::warning::Skipping empty thread ID argument"
      INVALID_COUNT=$((INVALID_COUNT + 1))
      continue
    fi
    if ! validate_thread_id "$arg"; then
      INVALID_COUNT=$((INVALID_COUNT + 1))
      continue
    fi
    if [ -n "$THREADS" ]; then
      THREADS="$THREADS"$'\n'"$arg"
    else
      THREADS="$arg"
    fi
  done
  # 全引数が無効な場合はエラー終了
  if [ -z "$THREADS" ] && [ "$INVALID_COUNT" -gt 0 ]; then
    echo "::error::All provided thread IDs were invalid ($INVALID_COUNT rejected)"
    exit 1
  fi
  QUERY_SUCCESS=true
else
  # 引数なし: 全未解決スレッドを取得
  # 注意: 100スレッドを超える場合はページネーション未対応
  THREADS=""
  QUERY_SUCCESS=true
  if ! THREADS=$(gh api graphql -f query="
  {
    repository(owner: \"$OWNER\", name: \"$REPO\") {
      pullRequest(number: $PR_NUMBER) {
        reviewThreads(first: 100) {
          nodes {
            id
            isResolved
          }
        }
      }
    }
  }" --jq '.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved == false) | .id' 2>&1); then
    QUERY_SUCCESS=false
    # 認証エラー（401/403）→ 即停止
    if echo "$THREADS" | grep -qE '401|403|authentication|forbidden'; then
      echo "::error::Authentication/permission error: $THREADS"
      exit 1
    fi
    # 一時的障害 → warning でスキップ
    echo "::warning::Failed to query review threads: $THREADS"
    THREADS=""
  fi
fi

# --- resolve 実行 ---
if [ -z "$THREADS" ]; then
  if [ "$QUERY_SUCCESS" = true ]; then
    echo "No unresolved threads to resolve. Skipping."
  else
    echo "::warning::Skipping resolve due to query failure."
  fi
  exit 0
fi

RESOLVED=0
FAILED=0
while IFS= read -r THREAD_ID; do
  [ -z "$THREAD_ID" ] && continue

  # フォーマット検証
  if ! validate_thread_id "$THREAD_ID"; then
    FAILED=$((FAILED + 1))
    continue
  fi

  # Windows Git Bash では GraphQL変数($threadId)が正しく渡らないため、
  # IDをmutationクエリに直接埋め込む
  if ! ERROR=$(gh api graphql -f query="
  mutation {
    resolveReviewThread(input: { threadId: \"$THREAD_ID\" }) {
      thread { isResolved }
    }
  }" 2>&1); then
    FAILED=$((FAILED + 1))
    echo "::warning::Failed to resolve thread $THREAD_ID: $ERROR"
  else
    RESOLVED=$((RESOLVED + 1))
  fi
done <<< "$THREADS"

echo "Resolved: $RESOLVED, Failed: $FAILED"

# 全件失敗は認証/権限エラーの可能性 → exit 1
if [ "$RESOLVED" -eq 0 ] && [ "$FAILED" -gt 0 ]; then
  echo "::error::All thread resolutions failed ($FAILED threads). Possible causes:"
  echo "::error::- Insufficient token permissions"
  echo "::error::- API rate limit exceeded"
  echo "::error::- GraphQL query syntax error"
  exit 1
fi
