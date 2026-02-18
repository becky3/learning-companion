---
name: check-pr
description: PRの内容確認・レビュー指摘対応・実装継続を行う
user-invocable: true
allowed-tools: Bash, Read, Edit, Write, Grep, Glob, Task
argument-hint: [pr-number]
---

## タスク

PRの内容を確認し、未解決のレビュー指摘があれば対応した上で、必要な実装を行う。

## 手順

1. PR番号の決定と変数設定
   - `$ARGUMENTS` が指定されていればその番号を使う
   - 未指定なら `gh pr view --json number -q .number` で現在ブランチのPRを検出
   - 以降の手順では決定したPR番号を `$PR_NUMBER` として参照する

2. PRブランチへのチェックアウト
   - 現在のブランチがPRのブランチでない場合:

     ```bash
     gh pr checkout $PR_NUMBER
     ```

   - 未コミットの変更がある場合はチェックアウトが失敗する。その場合は変更を stash するか、先にコミットしてから再実行する

3. PR情報の確認と表示

   ```bash
   # PR基本情報の取得
   gh pr view $PR_NUMBER --json title,body,headRefName,baseRefName

   # 変更ファイル一覧の取得
   gh pr view $PR_NUMBER --json files --jq '.files[].path'

   # 差分の確認
   gh pr diff $PR_NUMBER
   ```

   以下の形式でサマリーを表示:

   ```text
   ## PR #番号 の概要

   ### タイトル
   PRのタイトル

   ### 説明
   PRの説明（なければ「なし」）

   ### 変更ファイル
   - file1.py
   - file2.py
   ```

4. 未解決コメントの取得
   - owner/repo は `gh repo view --json owner,name` で取得
   - 以下の GraphQL で未解決スレッドのみ抽出（`{owner}`, `{repo}`, `$PR_NUMBER` を実際の値に置換して実行）:

   ```bash
   gh api graphql -f query='
   {
     repository(owner: "{owner}", name: "{repo}") {
       pullRequest(number: $PR_NUMBER) {
         reviewThreads(first: 100) {
           nodes {
             isResolved
             comments(first: 10) {
               nodes {
                 author { login }
                 body
                 path
                 line
               }
             }
           }
         }
       }
     }
   }' --jq '.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved == false) | .comments.nodes[0] | {author: .author.login, path, line, body}'
   ```

5. 指摘の一覧表示（ある場合）:

   ```text
   ### 未解決レビューコメント

   #### [N] ファイル:行番号 (レビュアー)
   指摘内容の要約
   ```

   - `[N]` は指摘の通し番号（1から開始）
   - 指摘がない場合は「未解決の指摘はありません」と表示

6. 関連する仕様書の確認
   - PRの目的に対応する `docs/specs/` の仕様書を特定して読む
   - 仕様書の受け入れ条件（AC）を把握する

7. 実装方針の検討と実施
   - PRの目的と変更内容を踏まえ、必要な実装を検討
   - 未解決の指摘がある場合:
     - 指摘対象のファイル・行を読み、コンテキストを理解する
     - 妥当な指摘かどうかを判断する
     - 妥当でない場合はスキップ理由を述べる
     - 妥当な指摘に対して修正を実施
   - 指摘がない場合も、PRの目的を達成するために必要な実装があれば継続

8. 修正後に **test-runner サブエージェント** で差分テストを実行:
   - `test-runnerサブエージェントで差分テストを実行してください` と呼び出す
   - 直接 `uv run pytest` を実行せず、必ずサブエージェントに委譲すること

9. ドキュメント整合性チェック:
   修正内容が以下のドキュメントの記述と矛盾しないか確認し、必要なら更新する:
   - `docs/specs/` — 仕様・受け入れ条件に影響する変更の場合
   - `CLAUDE.md` — 開発ルール・プロジェクト構造に影響する場合

10. `docs/specs/` に変更がある場合、**doc-reviewer サブエージェント** で変更した仕様書の品質レビューを実施:
    - `doc-reviewerサブエージェントを使用して docs/specs/対象ファイル.md をレビューしてください` と呼び出す
    - Critical/Warning の指摘があれば修正し、再度 test-runner でテスト通過を確認

11. PRに対応コメントを投稿（`gh pr comment`）:
    - 各指摘に対して状態（✅ 対応済み / ⏸️ 別Issue化 / ❌ 対応不要）を明記
    - 対応内容の簡潔な説明を含める
    - レビュアーが再確認しやすいよう、変更箇所や判断理由を記載
    - 表形式で投稿する:

      ```text
      ## レビュー指摘への対応

      | # | 状態 | 指摘 | 対応 |
      |---|:----:|------|------|
      | 1 | ✅ | 指摘の要約 | 対応内容の説明 |
      | 2 | ⏸️ | 指摘の要約 | Issue #N に切り出し |
      | 3 | ❌ | 指摘の要約 | 対応不要の理由 |
      ```

12. レビュースレッドの resolve:

    **前提条件**: ステップ4で取得した全ての未解決スレッドに対し、ステップ7・11で判断が完了していること。
    未検討のスレッドがある場合はステップ7に戻ること。

    全スレッドの判断完了後、以下の全ステータスのスレッドを resolve する:
    - ✅ 対応済み: 修正を実施した指摘
    - ❌ 対応不要: 判断理由付きで対応しないと決定した指摘
    - ⏸️ 別Issue化: 別Issueを作成して追跡可能にした指摘

    **実行方法**: `.github/scripts/auto-fix/resolve-threads.sh` を使用する。

    ```bash
    # 全未解決スレッドを resolve（引数なし）
    PR_NUMBER=$PR_NUMBER .github/scripts/auto-fix/resolve-threads.sh

    # 特定のスレッドIDのみ resolve（引数にスレッドIDを指定）
    PR_NUMBER=$PR_NUMBER .github/scripts/auto-fix/resolve-threads.sh PRRT_xxx PRRT_yyy
    ```

    エラーハンドリングはスクリプト内で実施される:
    - 認証/権限エラー → exit 1 で即停止
    - 個別失敗 → `::warning::` でログし続行
    - 全件失敗 → `::error::` + exit 1
    - スレッド0件 → ログ出力しスキップ

13. prt レビュー評価（Issue #265 への記録）:

    レビュー指摘に prt（PR Review Toolkit）の自動レビューコメントが含まれる場合、
    指摘の精度を評価し、**明らかに間違っている指摘や精度に問題がある指摘**があれば
    Issue #265 にコメントとして記録する。

    **評価観点**:
    - 技術的な分析が正確か（例: `set -e` との相互作用の見落とし等）
    - 指摘の文脈理解が適切か（例: CI/CD ワークフローのテスト戦略）
    - 信頼度スコアと実際の妥当性が一致しているか
    - 改善提案が実用的か

    **コメント形式**:

    ```text
    ## PR #番号 レビュー評価メモ

    ### エージェント名（件数）
    **問題の種類**: 具体的な説明
    - 問題のある記述の引用
    - 正しい分析・判断の説明
    **評価**: 総合コメント
    ```

    **注意**:
    - 全て妥当な指摘だった場合はコメント不要（問題がある場合のみ記録）
    - copilot の指摘も含めて評価し、ツール間の精度比較情報を含める

14. 修正をコミット & push:
    - コミットメッセージ:
      - 指摘対応のみ: `fix: レビュー指摘対応 (PR #番号)`
      - 実装継続: `feat: 実装内容の説明 (PR #番号)`
    - 変更内容を箇条書きでコミットメッセージに含める
    - ドキュメント更新がある場合はコミットメッセージにその旨も含める

15. 対応結果のサマリーを表示（prt 評価を Issue #265 に投稿した場合はその旨も報告）
