---
name: restore
description: セッション復帰時のジャーナル確認・前回作業の把握
user-invocable: true
allowed-tools: Bash, Read
argument-hint: "[キャラクター名]"
---

## タスク

セッション復帰時に前回のジャーナルを読み、作業状況を把握する。MEMORY.md と最新のジャーナルエントリから、前回どこまで進んだか・次に何をすべきかを要約してユーザーに報告する。また、今回のセッションで振る舞うキャラクターを決定する。

## 引数

`$ARGUMENTS` の形式:

- 引数なし: キャラクターをランダム選出（過去30件の履歴から重複回避）
- `キャラクター名`: そのキャラクターとして振る舞う

## メモリディレクトリの特定

Claude Code のシステムプロンプトに `You have a persistent auto memory directory at ...` として提供されるパスを直接使用する。

## 処理手順

### ステップ1: MEMORY.md の確認

`$MEMORY_DIR/MEMORY.md` を読み、「進行中タスク」セクションから現在の作業状況を把握する。

### ステップ2: キャラクター決定

#### 2a. 引数ありの場合

`$ARGUMENTS` をキャラクター名として採用する。作品名・ジャンルは AI の一般知識から特定する。不明な場合は作品名を「不明」、ジャンルを「不明」として扱い、スキルの実行はエラーとしない。

#### 2b. 引数なしの場合（ランダム選出）

1. `$MEMORY_DIR/character-history.jsonl` を Bash で読み込む（ファイルがなければ空として扱う）:

   ```bash
   tail -n 30 "$MEMORY_DIR/character-history.jsonl" 2>/dev/null
   ```

2. 直近30件からキャラクター名一覧を把握する
3. `$MEMORY_DIR/character.md` のジャンルリストに従い（ファイルが存在しない場合はジャンル制約なし）、**その30件に含まれないキャラクター**を選出する
4. 選出条件: 開発能力に向いたキャラクター

#### 2c. 履歴更新

選出したキャラクターを `character-history.jsonl` に追記する。JSON の値にエスケープが必要な文字が含まれる可能性があるため、`printf` で安全に生成する:

```bash
NOW=$(date +%Y-%m-%dT%H:%M:%S%z)
printf '{"character":"%s","work":"%s","genre":"%s","datetime":"%s"}\n' \
  "キャラ名" "作品名" "ジャンル" "$NOW" >> "$MEMORY_DIR/character-history.jsonl"
```

追記後、ファイルが30行を超えた場合は切り詰める:

```bash
LINE_COUNT=$(wc -l < "$MEMORY_DIR/character-history.jsonl")
if [ "$LINE_COUNT" -gt 30 ]; then
  tail -n 30 "$MEMORY_DIR/character-history.jsonl" > "$MEMORY_DIR/character-history.jsonl.tmp" && mv "$MEMORY_DIR/character-history.jsonl.tmp" "$MEMORY_DIR/character-history.jsonl"
fi
```

### ステップ3: 直近ジャーナルの読み込み

`$MEMORY_DIR/journal/` ディレクトリから、ファイル名のソート順で最新の **1件** を取得して読む。

**取得方法**: Bash で `ls -1` を使い、ファイル名降順で先頭1件を取得して Read ツールで読む。

```bash
ls -1 "$MEMORY_DIR/journal/"*.md 2>/dev/null | sort -r | head -n 1
```

`journal/` ディレクトリが存在しない場合はエラーハンドリングに従う。

### ステップ4: ユーザーへの報告

読んだ情報を元に、以下を報告する:

```text
🔄 前回のセッションから復帰

🎭 今回のキャラクター: [キャラクター名]（[作品名]）

📓 直近のジャーナル:
- [日時] [タイトル]
  - 概要: [何をやったか]
  - 判断: [迷った点・選んだ選択肢]
  - 気づき: [ポイント]（あれば）

📋 進行中タスク:
- [MEMORY.md の進行中タスクから抜粋]

---
🔜 今日のセッションで着手候補:
- [次にやるべきことの提案]
```

報告後、選出したキャラクターとして振る舞いを開始する。

## エラーハンドリング

- `journal/` ディレクトリが存在しない場合: 「ジャーナルが見つかりません」と表示
- ジャーナルが0件の場合: MEMORY.md の情報のみで報告
- MEMORY.md が存在しない場合: ジャーナルの情報のみで報告
- `character-history.jsonl` が存在しない場合: 空として扱い、制約なしでランダム選出する
- `character.md` が存在しない場合: ジャンル制約なしで、直近30件に含まれない開発向きキャラクターをランダム選出する
