# PR・Issue コメントでのメンション回避

PR や Issue にコメントを投稿する際、`@ユーザー名` 形式のメンションを使用しないこと。

- **理由**: `@copilot` のようなメンションは自動化ツールがトリガーとして検知し、意図しないPR作成やActions minutesの浪費を引き起こす
- **対処法**: `@` プレフィックスを外し、ユーザー名のみを記載する（例: `(copilot)` / `(becky3)`）
- **適用範囲**: `gh pr comment`、`gh issue comment`、PR body 等、GitHub 上に投稿する全てのテキスト
