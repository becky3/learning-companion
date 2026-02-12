---
name: auto-finalize
description: 品質チェック後の git commit / push / PR作成 / Issue完了コメント投稿を実行
user-invocable: true
allowed-tools: Bash, Read, Grep, Glob
argument-hint: "<Issue番号>"
---

## タスク

auto-implement 環境で品質チェック通過後に、commit / push / PR作成 / Issue完了コメント投稿までを確実に実行する。

## 引数

`$ARGUMENTS` の形式:

- `<Issue番号>` — 対応するIssue番号（必須、数値）
- 未指定の場合はエラーメッセージを表示して停止

## 処理手順

以下のステップを順番に実行する。各ステップでエラーが出たら即停止すること。

### 1. 変更状態の確認

```bash
git status
```

変更がなければ「コミットする変更がありません」と警告して停止。

### 2. 全変更をステージング

```bash
git add -A
```

### 3. 差分サマリの表示

```bash
git diff --cached --stat
```

### 4. コミット

変更内容からコミットメッセージを自動生成する:

- `src/` の変更あり: `feat: 実装内容の説明 (#Issue番号)`
- `docs/` や `CLAUDE.md` のみ: `docs: 変更内容 (#Issue番号)`
- `.github/workflows/` のみ: `ci: 変更内容 (#Issue番号)`
- バグ修正: `fix: 修正内容 (#Issue番号)`

```bash
git commit -m "生成したメッセージ"
```

### 5. プッシュ

```bash
BRANCH=$(git branch --show-current)
git push origin "$BRANCH"
```

### 6. PR作成

```bash
gh pr create --base develop --title "コミットメッセージと同じタイトル" --body "説明

Closes #Issue番号"
```

- baseブランチは常に `develop`
- bodyに `Closes #Issue番号` を含める

### 7. Issue完了コメント投稿

```bash
gh issue comment <Issue番号> --body "対応が完了しました。PR #<PR番号> をご確認ください。"
```

PR番号は手順6の出力から取得する。

### 8. 結果表示

作成したPRのURLを最終結果として表示する。
