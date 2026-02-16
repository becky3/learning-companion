---
name: handoff
description: セッション引き継ぎ（MEMORY.md更新・ジャーナル記録・次セッション申し送り）
user-invocable: true
allowed-tools: Bash, Read, Edit, Write, Grep, Glob
argument-hint: "[メッセージ]"
---

## タスク

セッション終了時の引き継ぎ処理を一括実行する。MEMORY.mdの更新、ジャーナル記録（JSONL形式）、ローリング、次セッションへの申し送りを行う。

仕様: docs/specs/handoff-skill.md

## 引数

`$ARGUMENTS` の形式:

- 引数なし: セッション引き継ぎを実行
- `"メッセージ"`: カスタムメッセージ付きで引き継ぎ（ジャーナルの「insight」フィールドに記録）

## メモリディレクトリの特定

MEMORY.md等のファイルは Claude Code のプロジェクトメモリディレクトリに配置する。

Claude Code のシステムプロンプトに `You have a persistent auto memory directory at ...` として現在のプロジェクトのメモリディレクトリパスが提供されている。**そのパスを直接使用すること**（`find` で探索しない）。

ディレクトリが見つからない場合はエラーとして扱い、ユーザーに設定の確認を促して処理を中断する。

## 処理手順

### ステップ1: セッション情報の収集

以下の情報を収集する:

1. **今日のコミット履歴**

   ```bash
   git log --oneline --since="midnight" --author="$(git config user.name)"
   ```

2. **現在のブランチとステータス**

   ```bash
   git branch --show-current
   git status --short
   ```

3. **今日マージされたPR**

   ```bash
   gh pr list --state merged --search "merged:>=$(date -I)" --json number,title 2>/dev/null || echo "[]"
   ```

4. **未完了の作業**
   - 未コミットの変更
   - 作業中のブランチ

### ステップ2: MEMORY.md の更新

MEMORY.md の「進行中タスク」セクションを更新する。

**ファイルパス**: `$MEMORY_DIR/MEMORY.md`

**存在しない場合は新規作成:**

```markdown
# AI Assistant 開発メモリ

## 進行中タスク

（ここにタスク情報を記述）

## プロジェクト知見

（ここに知見を記述）
```

**更新ルール:**

- 「## 進行中タスク」セクションを今セッションの成果と次の作業で上書き
- 「## プロジェクト知見」は追記のみ（新たに学んだことがあれば追加）
- **200行を超えないよう簡潔に記述する**（Claude Codeのシステムプロンプトに読み込まれるため）

### ステップ3: journal.jsonl にエントリ追加

**ファイルパス**: `$MEMORY_DIR/journal.jsonl`

**存在しない場合は新規作成**（空ファイル）。

**エントリ形式（ファイルの先頭に1行追加）:**

```json
{"at": "2026-02-17T07:40:00+09:00", "title": "一言タイトル", "did": "概要（1-2行）", "decision": "迷った点・選んだ選択肢・理由", "result": "良かった / 悪かった / 未検証", "insight": "次に活かすこと、ユーザーへの提案候補"}
```

**フィールド説明:**

| フィールド | 内容 |
|-----------|------|
| `at` | ISO 8601形式のタイムスタンプ（`date -Iseconds` で取得） |
| `title` | セッションの一言タイトル |
| `did` | やったことの概要 |
| `decision` | 迷った判断・選んだ選択肢・理由 |
| `result` | 結果（良かった / 悪かった / 未検証） |
| `insight` | 気づき・次に活かすこと |

カスタムメッセージ（引数）がある場合は `insight` フィールドの末尾に追記する。

**タイムスタンプ取得:**

```bash
date -Iseconds
```

**エントリの追加方法:**

新しいエントリをファイルの先頭に追加する（新しいものが上に来る）:

```bash
# 新しいエントリを先頭に追加
echo '{"at": "...", ...}' | cat - "$MEMORY_DIR/journal.jsonl" > /tmp/journal_tmp.jsonl && mv /tmp/journal_tmp.jsonl "$MEMORY_DIR/journal.jsonl"
```

### ステップ4: ジャーナルのローリング

ローリングスクリプトを呼び出す:

```bash
python3 "$(git rev-parse --show-toplevel)/.claude/scripts/journal-rolling.py" "$MEMORY_DIR"
```

スクリプトが journal.jsonl のエントリ数を確認し、10件を超えた分を journal-archive.jsonl に移動する。

### ステップ5: ユーザーへの報告

結果を表示する:

```text
✅ セッション引き継ぎ完了

📝 MEMORY.md を更新しました
📓 ジャーナルにエントリを追加しました（現在 N 件）
📦 古いエントリを M 件アーカイブしました（該当時のみ表示）

---
🔜 次のセッションで:
- [次にやることの箇条書き]
```

## エラーハンドリング

- メモリディレクトリが見つからない場合:

  ```text
  エラー: プロジェクトメモリディレクトリが見つかりません。
  Claude Code のプロジェクト設定を確認してください。
  ```

- git コマンドが使用できない場合:
  - コミット履歴・PR情報は「取得できませんでした」と表示し、残りの処理は続行

- ローリングスクリプトが見つからない場合:
  - 警告を表示し、ローリングをスキップして残りの処理は続行

## 注意事項

- MEMORY.md はClaude Codeのシステムプロンプトに読み込まれるため、200行以内に収める
- ジャーナルのローリングは10件を閾値とし、アーカイブに移動する
- カスタムメッセージが長い場合でもそのまま記録する（切り詰めない）
- 既存のMEMORY.mdの「プロジェクト知見」セクションは削除しない（追記のみ）
