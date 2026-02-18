---
name: merged
description: PRマージ後の定型処理（develop同期・ブランチ削除・ジャーナル）
user-invocable: true
allowed-tools: Bash, Read, Edit, Write, Glob, Grep
argument-hint: "<PR番号>"
---

## タスク

PRマージ後の定型処理を一括実行する。マージ先ブランチへの同期、マージ済みブランチの削除、ジャーナル記録を行う。

## 引数

`$ARGUMENTS` の形式:

- `N`（PR番号）: 対象のPR番号を指定

PR番号が未指定の場合はエラーとして扱い、入力を促す。

## メモリディレクトリの特定

Claude Code のシステムプロンプトに `You have a persistent auto memory directory at ...` として提供されるパスを直接使用する。

## 処理手順

### ステップ1: PR情報の取得

```bash
gh pr view $PR_NUMBER --json title,headRefName,baseRefName,state,mergedAt
```

- `state` が `MERGED` でない場合: 「PR #N はまだマージされていません」と表示して終了
- PR情報（タイトル、ブランチ名、マージ日時）を記録する

### ステップ2: マージ先ブランチへの同期

ステップ1で取得した `baseRefName` に同期する（通常は `develop`、release/hotfix の場合は `main`）。

```bash
git checkout "$BASE_REF_NAME"
git pull origin "$BASE_REF_NAME"
```

この操作が失敗した場合は、以降の git 操作（ブランチ削除等）を中断し、ジャーナル記録のみ続行する。

### ステップ3: マージ済みブランチの削除

ステップ1で取得した `headRefName` のブランチがローカルに存在する場合、削除する。

```bash
# ブランチ名はダブルクォートで囲み、-- で引数の終わりを明示する
if git show-ref --verify --quiet "refs/heads/$HEAD_REF_NAME"; then
  git branch -d -- "$HEAD_REF_NAME"
fi
```

- ブランチが存在しない場合はスキップ
- リモートブランチは GitHub が自動削除するため操作不要

### ステップ4: ジャーナル記録

`$MEMORY_DIR/journal/` に新規ファイルを作成する（ディレクトリが存在しない場合は作成する）。

`$MEMORY_DIR/journal-guidelines.md` のフォーマットに従い、PRの内容を振り返るエントリを書く:

```markdown
## YYYY-MM-DD HH:MM:SS - 一言タイトル

- **やったこと**: 概要（1-2行）
- **判断**: 迷った点・選んだ選択肢・理由
- **結果**: 良かった / 悪かった / 未検証
- **気づき**: 次に活かすこと、ユーザーへの提案候補
```

**ファイル名**: `YYYYMMDD-HHMMSS-タイトルスラッグ.md`

- タイトルスラッグ: Issue番号や副題を除去し、スペースをハイフンに置換。パス区切り文字や制御文字は除去する

### ステップ5: ユーザーへの報告

ジャーナルの要点を報告し、処理結果を表示する:

```text
✅ マージ後処理完了（PR #N）

🔄 develop を同期しました
🗑️ ブランチ xxx を削除しました（該当時のみ）
📓 ジャーナルを作成しました: {ファイル名}

---
📓 ジャーナル要点:
- [気づきや判断のハイライト]
```

## エラーハンドリング

- PR番号が未指定の場合: 「PR番号を指定してください（例: `/merged 482`）」と表示
- PRが MERGED でない場合: 「PR #N はまだマージされていません」と表示
- `git checkout` / `git pull` に失敗した場合: エラーメッセージを表示し、以降の git 操作（ブランチ削除等）は中断する。ジャーナル記録は続行する
- その他の軽微なエラー: エラーメッセージを表示し、後続処理を続行する
