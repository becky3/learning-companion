# セッション引き継ぎスキル（/handoff）

## 概要

セッション終了時の引き継ぎ処理を `/handoff` コマンドでワンアクション化するClaude Codeスキル。MEMORY.mdの更新、ジャーナル記録、ローリング、次セッションへの申し送りを一括で行う。

## 背景

セッション終了時に毎回「引き継ぎメモリお願い」と手動で打ち込み、MEMORY.mdの更新を依頼している。この定型処理をスキル化することで:

- 引き継ぎ作業の手間を削減（手動依頼 → コマンド1発）
- 記録内容のフォーマットを統一
- ジャーナルによるセッション履歴の蓄積
- 次セッションの開始点を明確にする

## ユーザーストーリー

- 開発者として、`/handoff` でセッション引き継ぎ処理を一括実行したい
- 開発者として、`/handoff "次のタスクのヒント"` でカスタムメッセージを添えて引き継ぎしたい
- 開発者として、過去のセッション履歴をジャーナルで振り返りたい

## 技術仕様

### スキル定義

```yaml
name: handoff
description: セッション引き継ぎ（MEMORY.md更新・ジャーナル記録・次セッション申し送り）
user-invocable: true
allowed-tools: Bash, Read, Edit, Write, Grep, Glob
argument-hint: "[メッセージ]"
```

### コマンド体系

| コマンド | 用途 |
|---------|------|
| `/handoff` | セッション引き継ぎを実行 |
| `/handoff "メッセージ"` | カスタムメッセージ付きで引き継ぎ |

### ファイル構成

| ファイル | パス | 役割 |
|---------|------|------|
| MEMORY.md | `{MEMORY_DIR}/MEMORY.md` | Claude Codeの永続メモリ（セッション横断） |
| journal.jsonl | `{MEMORY_DIR}/journal.jsonl` | セッションジャーナル（直近10件、JSONL形式） |
| journal-archive.jsonl | `{MEMORY_DIR}/journal-archive.jsonl` | アーカイブ済みジャーナル（JSONL形式） |
| journal-rolling.py | `.claude/scripts/journal-rolling.py` | ローリングスクリプト |

> `{MEMORY_DIR}` は Claude Code のシステムプロンプトで提供されるプロジェクトメモリディレクトリパス。

### 処理フロー

```mermaid
flowchart TD
    A[/handoff 実行] --> B[セッション情報の収集]
    B --> C[MEMORY.md 更新]
    C --> D[journal.jsonl にエントリ追加]
    D --> E[journal-rolling.py 実行]
    E --> F{エントリ数 > 10?}
    F -->|Yes| G[超過分を journal-archive.jsonl に移動]
    F -->|No| H[ローリング不要]
    G --> I[ユーザーへの報告]
    H --> I
```

### ステップ1: セッション情報の収集

以下の情報を収集し、引き継ぎの材料とする:

1. **今日のコミット履歴**

   ```bash
   git log --oneline --since="midnight" --author="$(git config user.name)"
   ```

2. **現在のブランチとステータス**

   ```bash
   git branch --show-current
   git status --short
   ```

3. **今日マージされたPR**（あれば）

   ```bash
   gh pr list --state merged --search "merged:>=$(date -I)" --json number,title
   ```

4. **未完了のタスク**
   - 未コミットの変更があるか
   - 作業中のIssue/PRがあるか

### ステップ2: MEMORY.md の更新

MEMORY.mdの「進行中タスク」セクションを、収集した情報に基づいて更新する。

**MEMORY.md の構造:**

```markdown
# AI Assistant 開発メモリ

## 進行中タスク

- 現在取り組んでいるタスクの説明
- 次に着手すべきこと

## プロジェクト知見

- 開発中に学んだ重要な知見
- ハマりやすいポイント
```

**更新ルール:**

- 「進行中タスク」セクションを今セッションの成果と次の作業で上書き
- 「プロジェクト知見」セクションは追記のみ（今セッションで新たに学んだことがあれば追加）
- MEMORY.mdが存在しない場合は新規作成
- 200行を超えないよう簡潔に記述する（Claude Codeのシステムプロンプトに読み込まれるため）

### ステップ3: journal.jsonl にエントリ追加

セッションの記録をジャーナルにJSONL形式で追加する。

**ジャーナルエントリの形式（1行のJSON）:**

```json
{"at": "2026-02-17T07:40:00+09:00", "title": "一言タイトル", "did": "概要", "decision": "判断", "result": "結果", "insight": "気づき"}
```

**フィールド定義:**

| フィールド | 旧形式の対応 | 内容 |
|-----------|-------------|------|
| `at` | 日付見出し | ISO 8601タイムスタンプ（`date -Iseconds`で取得、同日複数セッション区別用に時分秒含む） |
| `title` | 見出しタイトル | セッションの一言タイトル |
| `did` | やったこと | 概要（1-2行） |
| `decision` | 判断 | 迷った点・選んだ選択肢・理由 |
| `result` | 結果 | 良かった / 悪かった / 未検証 |
| `insight` | 気づき | 次に活かすこと、ユーザーへの提案候補 |

カスタムメッセージ（引数）がある場合は `insight` フィールドの末尾に追記する。

**追加ルール:**

- 常に新しいエントリを先頭（ファイルの1行目）に追加
- journal.jsonlが存在しない場合は新規作成（空ファイル）
- タイムスタンプは `date -Iseconds` で取得

### ステップ4: ジャーナルのローリング

ローリングスクリプト（`.claude/scripts/journal-rolling.py`）を呼び出す:

```bash
python3 "$(git rev-parse --show-toplevel)/.claude/scripts/journal-rolling.py" "$MEMORY_DIR"
```

**ローリングルール:**

- journal.jsonl の行数（= エントリ数）をカウント
- 10件を超えた分（11件目以降）を journal-archive.jsonl に移動
- journal-archive.jsonl が存在しない場合は新規作成
- journal-archive.jsonl では新しいエントリが上部に来るよう追加

### ステップ5: ユーザーへの報告

引き継ぎ結果をユーザーにわかりやすく表示する。

**出力形式:**

```text
✅ セッション引き継ぎ完了

📝 MEMORY.md を更新しました
📓 ジャーナルにエントリを追加しました（現在 N 件）
📦 古いエントリを 2 件アーカイブしました（該当時のみ表示）

---
🔜 次のセッションで:
- [次にやることの箇条書き]
```

## 使用LLMプロバイダー

**Claude Code (Claude Sonnet 4.5)** — スキル実行環境で使用

**選定理由:**

- セッション情報の要約・構造化にはLLMの推論力が必要
- Claude Codeのスキル機能はメインのClaude Sonnet 4.5エージェントによって実行される

## 受け入れ条件

- [ ] AC1: `/handoff` で MEMORY.md の「進行中タスク」セクションが更新される
- [ ] AC2: `/handoff` で journal.jsonl にセッションエントリがJSONL形式で追加される
- [ ] AC3: journal.jsonl のエントリが10件を超えた場合、ローリングスクリプトにより超過分が journal-archive.jsonl に移動される
- [ ] AC4: 引き継ぎ結果がユーザーに報告される（次セッションの開始点が明示される）
- [ ] AC5: `/handoff "メッセージ"` でカスタムメッセージがジャーナルに含まれる
- [ ] AC6: MEMORY.md・journal.jsonl が存在しない場合、新規作成される
- [ ] AC7: MEMORY.md が200行を超えないよう簡潔に記述される

## 関連ファイル

| ファイル | 役割 |
|---------|------|
| `.claude/skills/handoff/SKILL.md` | handoffスキル定義 |
| `.claude/scripts/journal-rolling.py` | ローリングスクリプト |
| `{MEMORY_DIR}/MEMORY.md` | 永続メモリ |
| `{MEMORY_DIR}/journal.jsonl` | セッションジャーナル（JSONL形式） |
| `{MEMORY_DIR}/journal-archive.jsonl` | アーカイブ済みジャーナル（JSONL形式） |
| `CLAUDE.md` | スキル一覧への登録 |

## テスト方針

Claude Codeスキルは実行時テストが中心となるため、手動テストで確認:

- [ ] `/handoff` でMEMORY.md が正しく更新される（AC1）
- [ ] journal.jsonl にJSONLエントリが追加される（AC2）
- [ ] 11件目のエントリ追加時にローリングスクリプトが動作する（AC3）
- [ ] 結果報告に次セッションの開始点が含まれる（AC4）
- [ ] カスタムメッセージが反映される（AC5）

## 拡張性

将来的に以下の機能を追加可能:

- Slack/Discord への引き継ぎ通知
- チーム開発時のメンバー間引き継ぎ
- セッション統計（作業時間、コミット数等）の自動計算

## 参考資料

- Issue #389 — 本機能の議論
- [Claude Code Skills公式ドキュメント](https://code.claude.com/docs/ja/skills)
