# AI Assistant — 開発ガイドライン

**最初に [README.md](README.md) を必ず読むこと。** プロジェクトの概要・技術スタック・起動方法・プロジェクト構造・評価CLIの使い方が記載されている。

## LLM使い分けルール

- **デフォルト**: 全サービスでローカルLLM（LM Studio）を使用
- **設定変更**: `.env` で各サービスごとにLLMを変更可能
  - `CHAT_LLM_PROVIDER` / `PROFILER_LLM_PROVIDER` / `TOPIC_LLM_PROVIDER` / `SUMMARIZER_LLM_PROVIDER`
  - 各設定は `"local"` または `"online"` を指定（デフォルト: `"local"`）
- `MCP_ENABLED` — MCP機能の有効/無効（デフォルト: `false`）。MCPサーバー（`mcp_servers/` 配下）は `src/` のモジュールを import しないこと
- `RAG_ENABLED` — RAG機能の有効/無効（デフォルト: `false`）。詳細は `docs/specs/f9-rag.md` 参照

## 開発ルール

### 仕様駆動開発

- **実装前に必ず `docs/specs/` の仕様書を読むこと**。仕様書が実装の根拠。
- **実装前に既存コードを必ず読むこと**。仕様書の「関連ファイル」に記載された実装ファイルを確認し、既存の構造・パターン・抽象化を把握してから設計する。
- **既存コードの拡張を優先する**。新しいメソッドやクラスを作る前に、既存のメソッドにパラメータ追加で対応できないか検討する。
- 仕様書にない機能追加・リファクタリングは別Issueに切り出す。ただし **軽微な修正**（typo、lint エラー等）はその場で修正、**大きな問題** は Issue に切り出す。
- 仕様変更が必要な場合は、先に仕様書を更新してから実装する。
- 外部サービス（GitHub API、CI/CD等）の挙動は仕様書か公式ドキュメントで確認する。

### コーディング規約

- 各サービスクラスのdocstringに仕様書パスを記載: `仕様: docs/specs/f2-feed-collection.md`
- テスト名は仕様書の受け入れ条件(AC)番号と対応: `test_ac1_rss_feed_is_fetched_and_parsed()`
- ruff でリント、mypy (strict) で型チェック
- markdownlint（`npx markdownlint-cli2@0.20.0`）でMarkdownチェック
- shellcheck（`uv run shellcheck`）でシェルスクリプトチェック（`.github/scripts/` 配下）
  - suppress コメントはディレクティブ行と説明行を分ける:

    ```bash
    # Reason for suppression
    # shellcheck disable=SC2016
    ```

- ドキュメント内の図表は mermaid 形式を使用（ASCII図表は不可）
- **フォールバック/暗黙のデフォルト値の禁止**
  - 関数の引数が `None` の場合に settings/env から暗黙に取得するパターンは禁止。呼び出し元が値の出所を決定すること
  - argparse の `default` で具体値を設定するのではなく `required=True` にして明示させること
  - 適用対象: 評価CLI・テストツール・スクリプトの関数引数・argparse
  - 適用対象外: 本番コード（`main.py`）の settings 参照、基盤設定（DB接続先等）、スキル/エージェント定義のデフォルト値

### 作業開始時の手順

1. Issue・Milestoneの確認: `gh milestone list` / `gh issue list --state open` / `gh issue view <番号>`
2. 対象Issueの仕様書を読む（`docs/specs/` の該当ファイル）
3. 既存実装コードの確認（仕様書の「関連ファイル」セクション）
4. ブランチ作成 → 実装 → PR の流れで進める

### Git運用（git-flow）

詳細は `docs/specs/git-flow.md` を参照。

- **常設ブランチ**: `main`（安定版）/ `develop`（開発統合）
- **作業ブランチ**: `feature/f{N}-{機能名}-#{Issue番号}` / `bugfix/{修正内容}-#{Issue番号}` / `release/v{X.Y.Z}` / `hotfix/{修正内容}-#{Issue番号}`
- コミット: `feat(f{N}): 説明 (#{Issue番号})`
- PR作成時に `Closes #{Issue番号}` で紐付け
- **PRのbaseブランチ**: 通常は `develop`、リリース/hotfix は `main`、リリース中の bugfix は `release/*`
- **マージ方式**: feature/bugfix → develop は通常マージ、bugfix → release は通常マージ、release → main は squash マージ、sync → develop は通常マージ
- **サブIssue作成**: `gh` CLI は未サポートのため GraphQL API を使用（`gh api graphql` の `addSubIssue` mutation）。親・子の Node ID は `gh issue view <番号> --json id --jq '.id'` で取得し、直接埋め込む

### 実装完了時の必須手順

1. **ファイル確認**: 作成したファイルが実際に存在するか `ls -la` で確認
2. **テスト実行**: test-runner エージェントで全テスト通過を確認
3. **コードレビュー**: code-reviewer エージェントでセルフレビュー。各指摘は対応すべきかそれぞれ判断
4. **ドキュメントレビュー**: `docs/specs/` 等に変更がある場合、doc-reviewer エージェントで品質レビュー。実装のみのPRでも対応する仕様書との整合性チェックを実施すること
   - スキップ基準: 誤字脱字のみの修正
   - 差分レビュー推奨: PRレビュー指摘対応、軽微な補足追加
5. **ステージング・コミット・プッシュ・PR作成**
   - PR body は `.github/pull_request_template.md` の形式に従う（仕様: `docs/specs/pr-body-template.md`）
   - 設計書の先行更新PRでは Change type で `docs(pre-impl)` を選択
6. **PR確認**: `gh pr view` で確認し、URLをユーザーに提示

**テスト・レビューで検出した問題のスキップ禁止**:

上記ステップ 2〜4 で検出した問題を「対応範囲外」「既存問題」としてスキップしてはならない。検出した問題は以下のルールに従って必ず対処すること:

- **軽微な問題**（typo、lint エラー、簡単な型エラー等）: その場で修正する
- **大きな問題**（設計変更が必要、影響範囲が広い等）: Issue を作成して記録する
- **判断に迷う場合**: ユーザーに相談する（自己判断でスキップしない）

### レビュー指摘対応

レビュー指摘への対応は `/check-pr` スキルを使用する。
「指摘をチェックして」「レビューを確認して」等のユーザー依頼時に自律的に呼び出すこと。

### PR・Issue コメントでのメンション回避

PR や Issue にコメントを投稿する際、`@ユーザー名` 形式のメンションを使用しないこと。

- **理由**: `@copilot` のようなメンションは自動化ツールがトリガーとして検知し、意図しないPR作成やActions minutesの浪費を引き起こす
- **対処法**: `@` プレフィックスを外し、ユーザー名のみを記載する（例: `(copilot)` / `(becky3)`）
- **適用範囲**: `gh pr comment`、`gh issue comment`、PR body 等、GitHub 上に投稿する全てのテキスト

## 自動進行ルール（auto-progress）

自動実装の詳細ルール・品質チェック手順・GA環境の制約は `.claude/CLAUDE-auto-progress.md` を参照。

## Claude Code 拡張機能

### Hooks

- **仕様**: `docs/specs/claude-code-hooks.md`
- **破壊コマンドガード**: `gh issue delete` / `gh repo delete` 等をフックでブロック。実行が必要な場合はターミナルから直接実行する
- シェルスクリプト（`.sh`）は **LF 改行コード** で保存すること（CRLF だとエラー）
- **出力の破棄には必ず `/dev/null` を使うこと。`> nul` は禁止**（Git Bash では `nul` ファイルが生成される）

### 自律呼び出しルール

以下のユーザー表現に対して、対応するスキルまたはエージェントを自律的に呼び出すこと:

| ユーザー表現 | 呼び出し先 | 種別 |
|-------------|-----------|------|
| 「テスト実行して」「テスト通して」 | test-runner | エージェント |
| 「コードレビューして」「セルフレビュー」 | code-reviewer | エージェント |
| 「ドキュメントレビューして」「仕様書レビュー」 | doc-reviewer | エージェント |
| 「レビュー指摘に対応して」「レビューを確認して」 | `/check-pr` | スキル |
| 「PRマージされた」「マージ後処理して」 | `/merged` | スキル |
| 「チームで作業して」「チーム立ち上げて」 | `/start-team` | スキル |
| 「コミットしてPR作成して」「ファイナライズして」 | `/auto-finalize` | スキル |
| 「引き継ぎお願い」「セッション終了」 | `/handoff` | スキル |
| 「前回の続き」「復帰して」 | `/restore` | スキル |
| 「自動マージレビューチェックして」 | `/check-review-batch` | スキル |
| 「仕様書を作って」「スペック作成」 | `/doc-gen` | スキル |
| 「仕様書を更新して」「ドキュメント修正して」 | `/doc-edit` | スキル |

### サブエージェント

サブエージェント定義は `.claude/agents/` 配下。用途と使い分け:

| エージェント | 用途 | 呼び出し元 |
|------------|------|-----------|
| test-runner | テスト・リント・型チェック実行 | `/test-run` スキル |
| code-reviewer | セルフコードレビュー | `/code-review` スキル |
| doc-reviewer | ドキュメントレビュー | `/doc-review` スキル |
| planner | 実装計画の立案 | Issue 対応時に手動 |
| prt-code-reviewer | CLAUDE.md 準拠・バグ検出 | `/check-pr` 経由 |
| prt-code-simplifier | コード簡素化 | `/check-pr` 経由 |
| prt-comment-analyzer | コメント正確性分析 | `/check-pr` 経由 |
| prt-silent-failure-hunter | サイレント障害検出 | `/check-pr` 経由 |
| prt-test-analyzer | テストカバレッジ分析 | `/check-pr` 経由 |
| prt-type-design-analyzer | 型設計の品質分析 | `/check-pr` 経由 |

### エージェントチーム

チーム機能の仕様は `docs/specs/agent-teams/` 配下を参照。
