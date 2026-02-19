# AI Assistant — 開発ガイドライン

> プロジェクトの概要・技術スタック・セットアップ手順・プロジェクト構造は [README.md](README.md) を参照してください。

## LLM使い分けルール

- **デフォルト**: 全サービスでローカルLLM（LM Studio）を使用
- **設定変更**: `.env` で各サービスごとにLLMを変更可能
  - `CHAT_LLM_PROVIDER` / `PROFILER_LLM_PROVIDER` / `TOPIC_LLM_PROVIDER` / `SUMMARIZER_LLM_PROVIDER`
  - 各設定は `"local"` または `"online"` を指定（デフォルト: `"local"`）
- `MCP_ENABLED` — MCP機能の有効/無効（デフォルト: `false`）。MCPサーバー（`mcp-servers/` 配下）は `src/` のモジュールを import しないこと
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
- **PRのbaseブランチ**: 通常は `develop`、リリース/hotfix は `main`
- **マージ方式**: feature/bugfix → develop は通常マージ、release → main は squash マージ
- **サブIssue作成**: `gh` CLI は未サポートのため GraphQL API を使用（`gh api graphql` の `addSubIssue` mutation）。親・子の Node ID は `gh issue view <番号> --json id --jq '.id'` で取得し、直接埋め込む

### 実装完了時の必須手順

1. **ファイル確認**: 作成したファイルが実際に存在するか `ls -la` で確認
2. **テスト実行**: `/test-run` スキルで全テスト通過を確認
3. **コードレビュー**: `/code-review` スキルでセルフレビュー。各指摘は対応すべきかそれぞれ判断
4. **ドキュメントレビュー**: `docs/specs/` 等に変更がある場合、`/doc-review` で品質レビュー。実装のみのPRでも対応する仕様書との整合性チェックを実施すること
   - スキップ基準: 誤字脱字のみの修正
   - 差分レビュー推奨: PRレビュー指摘対応、軽微な補足追加
5. **ステージング・コミット・プッシュ・PR作成**
   - PR body は `.github/pull_request_template.md` の形式に従う（仕様: `docs/specs/pr-body-template.md`）
   - 設計書の先行更新PRでは Change type で `docs(pre-impl)` を選択
6. **PR確認**: `gh pr view` で確認し、URLをユーザーに提示

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

### スキル自律呼び出しルール

以下のユーザー表現に対して、対応するスキルを自律的に呼び出すこと:

- 「レビュー指摘に対応して」「レビューを確認して」 → `/check-pr`
- 「テスト実行して」「テスト通して」 → `/test-run`
- 「PRマージされた」「マージ後処理して」 → `/merged`
- 「チームで作業して」「チームを開始して」「チーム立ち上げて」 → `/start-team`
- 利用可能なスキル定義: `.claude/skills/` 配下

### サブエージェント

サブエージェント定義は `.claude/agents/` 配下を参照。

### エージェントチーム

チーム機能の仕様は `docs/specs/agent-teams/` 配下を参照。
