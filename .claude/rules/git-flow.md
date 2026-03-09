# Git運用（git-flow）

詳細は `docs/specs/workflows/git-flow.md` を参照。

- **常設ブランチ**: `main`（安定版）/ `develop`（開発統合）
- **作業ブランチ**: `feature/{機能名}-#{Issue番号}` / `bugfix/{修正内容}-#{Issue番号}` / `release/v{X.Y.Z}` / `hotfix/{修正内容}-#{Issue番号}`
- コミット: `type(scope): 説明 (#Issue番号)` ※scope は仕様書ファイル名（拡張子なし）
- PR作成時に `Closes #{Issue番号}` で紐付け
- **PRのbaseブランチ**: 通常は `develop`、リリース/hotfix は `main`、リリース中の bugfix は `release/*`
- **マージ方式**: feature/bugfix → develop は通常マージ、bugfix → release は通常マージ、release → main は squash マージ、sync → develop は通常マージ
- **サブIssue作成**: `gh` CLI は未サポートのため GraphQL API を使用（`gh api graphql` の `addSubIssue` mutation）。親・子の Node ID は `gh issue view <番号> --json id --jq '.id'` で取得し、直接埋め込む
