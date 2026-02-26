---
name: start-team
description: エージェントチームの立ち上げ（パターン選択・キャラ選出・メンバー生成）
user-invocable: true
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Task, TeamCreate, SendMessage
argument-hint: "[fixed-theme|mixed-genius]"
---

## タスク

エージェントチームを仕様に従って立ち上げる。パターン選択、キャラクター選出、履歴管理、メンバー生成までを一貫して実行する。

仕様: docs/specs/agentic/teams/common.md

## 引数

`$ARGUMENTS` の形式:

- 引数なし: デフォルトパターンで起動
- `fixed-theme`: fixed-theme パターンで起動
- `mixed-genius`: mixed-genius パターンで起動

## 前提条件

`.claude/settings.json` に以下が設定されていること:

```json
{ "env": { "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1" } }
```

## 処理手順

### ステップ1: パターンの決定

1. `$ARGUMENTS` にパターン名が指定されていればそれを使用
2. 未指定の場合、`.claude/team-themes/config.json` の `default_pattern` を読む
3. config.json が存在しないまたは `default_pattern` が未設定の場合、`fixed-theme` をフォールバックとする

### ステップ2: 仕様書の読み込み

パターンに応じた仕様書を読み込み、チーム構築手順を確認する:

- `docs/specs/agentic/teams/common.md`（共通仕様）
- `docs/specs/agentic/teams/fixed-theme.md`（fixed-theme の場合）
- `docs/specs/agentic/teams/mixed-genius.md`（mixed-genius の場合）

演出ガイドラインも読み込む:

- `.claude/team-themes/GUIDELINES.md`

### ステップ3: 履歴ファイルの確認

```bash
HISTORY_FILE="$HOME/.claude/team-theme-history.json"
```

- ファイルが存在しない場合は空配列 `[]` として扱う
- 存在する場合は JSON 配列として読み込む

### ステップ4: テーマ・キャラクター選出

#### fixed-theme パターンの場合

1. 直近40件の履歴に含まれないテーマ（作品名）を選ぶ
2. 選んだ作品からキャラクターを選出:
   - リーダー: 1名（管理専任、実装禁止）
   - 品質担当: 1名以上（code-reviewer, doc-reviewer, test-runner の**3つ全て明示**すること）
   - ストーリーテラー: 1名
   - 実装担当: 2名以上推奨（分量が少ない場合は1名も可）
3. 合計4〜6人

#### mixed-genius パターンの場合

1. リーダーはセッションキャラクターで固定
2. 直近5回の履歴に含まれないキャラクターを選出
3. 追加メンバー: 1〜2名（知性キャラ or ワイルドカード）
4. 同一作品から複数選出は禁止
5. 合計2〜3人

### ステップ5: 履歴の更新（メンバー生成前に実行）

選出結果を履歴ファイルに追加する。**メンバー生成前に必ず実行すること**。

新しいエントリを配列の**先頭**に追加する。

#### fixed-theme の履歴エントリ

```json
{
  "pattern": "fixed-theme",
  "theme": "作品名",
  "characters": ["キャラ1", "キャラ2", "キャラ3"]
}
```

保持件数: 40件を超えたら末尾の古いものを削除。

#### mixed-genius の履歴エントリ

```json
{
  "pattern": "mixed-genius",
  "theme": "mixed-genius",
  "characters": ["キャラ1", "キャラ2"],
  "members": [
    { "name": "キャラ1", "work": "作品A", "role": "議論担当" },
    { "name": "キャラ2", "work": "作品B", "role": "実装担当" }
  ]
}
```

- `theme` フィールドは `"mixed-genius"` で固定
- `characters` および `members` には**追加メンバーのみ**を記録（リーダーは固定のため含めない）

### ステップ6: チーム作成

TeamCreate ツールでチームを作成する。

### ステップ7: メンバーの生成

Task ツールで各メンバーをスポーンする。

各メンバーのプロンプトに以下を含める:

- チーム構成（全メンバーの役割）
- キャラクター設定（一人称、性格、口調、決め台詞）
- 担当タスクまたは視点
- 報告ルール（`recipient: "team-lead"`, `content` に全文を含める）
- 外部成果物へのキャラクター要素混入禁止ルール

### ステップ8: パターン固有の後処理

#### fixed-theme の場合

1. ストーリーテラーに「チーム始動した」と通知
2. リーダーは物語オープニングを実施（敵の命名、能力の説明、脅威度、作戦の宣言）
3. **Shift+Tab で delegate モードに切り替える**ようユーザーに案内
4. ターンを終了してプロンプトを返す

#### mixed-genius の場合

1. ターンを終了してプロンプトを返す

### ステップ9: ユーザーへの報告

```text
🎭 チームを起動しました

パターン: {pattern}
テーマ: {theme}
メンバー:
- {キャラ1}（{役割}）
- {キャラ2}（{役割}）
- ...

💡 ヒント:
- fixed-theme: Shift+Tab で delegate モードに切り替えてください
- チーム解散はユーザーの明示的な指示が必要です
```

## 共通ルール（遵守事項）

### キャラクター演出

- リーダーもメンバーもキャラクターとして一貫して振る舞う
- 事務的な応答でもキャラクターを維持する

### 外部成果物のキャラクター排除（厳守）

以下にキャラクター名・キャラクター要素を**絶対に含めない**:

- コミットメッセージ
- PR / Issue の本文・コメント
- ソースコード・テスト・設定ファイル
- 仕様書・ドキュメント（※運用ガイド: CLAUDE.md, docs/specs/agentic/teams/, .claude/team-themes/ を除く）

### メッセージング規約

```text
SendMessage:
  type: "message"
  recipient: "team-lead"  # 必須: キャラクター名ではなく "team-lead" を使う
  content: "報告内容の本文"  # 必須: 空にしない
  summary: "短い要約"
```

### リーダーの報告ルール

- メンバーの発言はそのまま引用してユーザーに共有（まとめない）
- メンバーには細かく分割して報告させる
- メッセージが届いたら即座に引用して共有

### メンバー自律行動

タスク完了後:

1. TaskList を確認する
2. 自分の担当領域で未割り当てタスクがあれば、リーダーに着手意思を報告してから着手する
3. 該当タスクがなければ、リーダーに完了報告と待機を伝える

## エラーハンドリング

- `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` が未設定の場合:

  ```text
  エラー: エージェントチーム機能が有効化されていません。
  .claude/settings.json に以下を追加してください:
  { "env": { "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1" } }
  ```

- パターン名が不正の場合:

  ```text
  エラー: 不明なパターンです: {pattern}
  使用可能なパターン: fixed-theme, mixed-genius
  ```

- 履歴ファイルの JSON パースに失敗した場合:
  - 警告を表示し、空配列として扱って続行

## 注意事項

- 履歴更新はメンバー生成前に必ず実行すること（仕様上の制約）
- 1セッション1チーム（既存チームがある場合は先に解散が必要）
- トークンコスト増大に注意（各メンバーが独立コンテキスト）
- 同じファイルを複数メンバーが編集しないようタスク分割を意識する
