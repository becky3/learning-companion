#!/usr/bin/env bash
# Post Merge — レビューIssue更新スクリプト
#
# 全ての自動マージPRを auto:review-batch Issue にコメントとして記録する。
# Issue未存在時は概要bodyで新規作成 + ピン留め。
#
# 必須環境変数:
#   PR_NUMBER       — マージされたPR番号
#   PR_TITLE        — PRタイトル
#   GH_TOKEN        — GitHub トークン
#   GH_REPO         — リポジトリ (owner/repo)
#
# エラー方針: Issue操作失敗 → warning で続行

# _common.sh を auto-fix/ から相対パスで source
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/../auto-fix/_common.sh"

require_env PR_NUMBER
validate_pr_number "$PR_NUMBER"
# PR_TITLE は情報提供目的のため、空でもフォールバックして記録を続行
PR_TITLE="${PR_TITLE:-(タイトル取得失敗)}"

# --- PR の変更ファイル一覧を取得 ---
CHANGED_FILES=""
if ! CHANGED_FILES=$(gh pr view "$PR_NUMBER" --json files --jq '.files[].path' 2>&1); then
  echo "::warning::Failed to get PR files: $CHANGED_FILES"
  CHANGED_FILES=""
fi

# 今日の日付（失敗時はフォールバック）
DATE=$(date -u +"%Y-%m-%d") || DATE="unknown-date"

# ファイル一覧を整形（リスト形式）
FILE_LIST=""
while IFS= read -r file; do
  if [ -n "$file" ]; then
    FILE_LIST="${FILE_LIST}
- \`${file}\`"
  fi
done <<< "$CHANGED_FILES"

if [ -z "$FILE_LIST" ]; then
  FILE_LIST="
- (取得失敗)"
fi

# コメントとして追記するセクション
COMMENT_BODY="## PR #${PR_NUMBER}: ${PR_TITLE} (${DATE})

### 変更ファイル${FILE_LIST}"

# --- 既存 review-batch Issue を検索 ---
EXISTING_ISSUE=""
if ! EXISTING_ISSUE=$(gh issue list --label "auto:review-batch" --state open --json number --jq '.[0].number // empty' 2>&1); then
  echo "::warning::Failed to search for review-batch issue: $EXISTING_ISSUE"
  EXISTING_ISSUE=""
fi

# 数値バリデーション（APIレスポンス異常時の防御）
if [ -n "$EXISTING_ISSUE" ] && ! validate_numeric "$EXISTING_ISSUE" "EXISTING_ISSUE"; then
  echo "::warning::Unexpected issue number format: '$EXISTING_ISSUE'"
  EXISTING_ISSUE=""
fi

if [ -n "$EXISTING_ISSUE" ]; then
  # --- 既存Issueにコメント追記 ---
  echo "Found existing review-batch issue: #$EXISTING_ISSUE"

  if ! gh_safe_warning gh issue comment "$EXISTING_ISSUE" --body "$COMMENT_BODY"; then
    echo "::warning::Failed to add comment to review-batch issue #$EXISTING_ISSUE for PR #$PR_NUMBER"
  else
    echo "Added comment to review-batch issue #$EXISTING_ISSUE"
  fi
else
  # --- 新規Issue作成 + ピン留め ---
  echo "No existing review-batch issue found. Creating new one."

  ISSUE_BODY="# 自動マージレビュー

自動マージされたPRの一覧です。
各PRの変更内容を確認し、問題がなければこのIssueをクローズしてください。"

  NEW_ISSUE_URL=""
  if ! NEW_ISSUE_URL=$(gh issue create \
    --title "自動マージレビュー (created:${DATE})" \
    --body "$ISSUE_BODY" \
    --label "auto:review-batch" 2>&1); then
    echo "::warning::Failed to create review-batch issue: $NEW_ISSUE_URL"
    exit 0
  fi

  # URL形式バリデーション（stderr混入やエラーメッセージの防御）
  if [[ "$NEW_ISSUE_URL" != https://github.com/* ]]; then
    echo "::warning::Unexpected issue URL format: $NEW_ISSUE_URL"
    exit 0
  fi

  # Issue番号を抽出（URLの末尾の数字）
  NEW_ISSUE_NUM="${NEW_ISSUE_URL##*/}"

  # 数値バリデーション（stderr混入時の防御）
  if ! validate_numeric "$NEW_ISSUE_NUM" "NEW_ISSUE_NUM"; then
    echo "::warning::Could not extract issue number from: $NEW_ISSUE_URL"
    exit 0
  fi

  echo "Created review-batch issue: #$NEW_ISSUE_NUM ($NEW_ISSUE_URL)"

  # ピン留め（ベストエフォート）
  if ! gh_safe_warning gh issue pin "$NEW_ISSUE_NUM"; then
    echo "::warning::Failed to pin issue #$NEW_ISSUE_NUM (non-critical)"
  else
    echo "Pinned review-batch issue #$NEW_ISSUE_NUM"
  fi

  # 初回PRもコメントで追記
  if ! gh_safe_warning gh issue comment "$NEW_ISSUE_NUM" --body "$COMMENT_BODY"; then
    echo "::warning::Failed to add initial comment to review-batch issue #$NEW_ISSUE_NUM"
  else
    echo "Added initial comment to review-batch issue #$NEW_ISSUE_NUM"
  fi
fi
