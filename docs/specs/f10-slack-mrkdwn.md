# F10: Slack mrkdwn形式対応

## 概要

LLMからの返信をSlackのmrkdwn形式で出力し、太字・リスト等の装飾が正しく表示されるようにする。

## 背景

LLMはデフォルトでMarkdown形式のテキストを出力するが、Slackは独自のmrkdwn形式を使用しており、
標準Markdownの装飾記法がそのまま表示されてしまう問題がある。

### Markdown と Slack mrkdwn の違い

| 要素 | Markdown | Slack mrkdwn |
|------|----------|--------------|
| 太字 | `**text**` | `*text*` |
| イタリック | `*text*` | `_text_` |
| 取り消し線 | `~~text~~` | `~text~` |
| リンク | `[text](url)` | `<url\|text>` |
| 順序なしリスト | `- item` | `• item` |
| 引用 | `> text` | `> text`（同じ） |
| コードブロック | ` ```code``` ` | ` ```code``` `（同じ） |
| インラインコード | `` `code` `` | `` `code` ``（同じ） |
| 見出し | `# heading` | `*heading*`（太字で代替） |

## ユーザーストーリー

- ユーザーとして、ボットの返信がSlack上で正しく装飾表示されることを期待する。

## 設計方針

### 採用: プロンプト方式

システムプロンプトにSlack mrkdwn形式の出力指示を追加する。

**理由**:

- 実装がシンプル（設定ファイルとエントリーポイントの変更のみ）
- LLMは出力フォーマット指示に従う能力が高い
- 変換処理の正規表現による誤変換リスクがない
- 保守が容易（指示文の修正のみで対応可能）

### 不採用: 後処理変換方式

LLM出力後にMarkdown→mrkdwn変換を行う方式は以下の理由で不採用:

- 正規表現によるMarkdown→mrkdwn変換はエッジケースが多い
- コードブロック内のMarkdown記法を誤変換するリスク
- 変換ロジックの保守コストが高い

## 入出力仕様

### 入力

- `config/assistant.yaml` の `slack_format_instruction` フィールド

### 出力

- システムプロンプトにmrkdwn出力指示が追加された状態でLLMが呼び出される
- LLMの応答がSlack mrkdwn形式で出力される

## 実装詳細

### 1. `config/assistant.yaml` に指示文を追加

```yaml
slack_format_instruction: |
  【出力フォーマット】
  Slackに表示されるため、Slack mrkdwn形式で出力してください:
  • 太字: *テキスト*
  • イタリック: _テキスト_
  • 取り消し線: ~テキスト~
  • リンク: <URL|テキスト>
  • リスト: 「• 」で箇条書き
  • 見出し: *見出しテキスト* （太字で代替）
  • コードブロック: ```コード```
  • インラインコード: `コード`
  Markdown記法（**太字**、[リンク](URL)、- リスト等）は使用しないでください。
```

### 2. `src/main.py` でシステムプロンプトに追加

```python
system_prompt = assistant.get("personality", "")
slack_format = assistant.get("slack_format_instruction", "")
if slack_format:
    system_prompt = system_prompt + "\n\n" + slack_format
```

## 受け入れ条件

- [ ] AC1: `config/assistant.yaml` に `slack_format_instruction` が定義されている
- [ ] AC2: `slack_format_instruction` がシステムプロンプトの末尾に追加される
- [ ] AC3: `slack_format_instruction` が空の場合、システムプロンプトに影響しない

## 関連ファイル

| ファイル | 役割 |
|---------|------|
| `config/assistant.yaml` | アシスタント設定（mrkdwn指示文を追加） |
| `src/main.py` | エントリーポイント（システムプロンプト構築） |
| `src/services/chat.py` | チャットサービス（変更なし） |
| `src/slack/handlers.py` | Slackハンドラ（変更なし） |

## テスト方針

- `slack_format_instruction` が設定されている場合、システムプロンプトに追加されることを確認
- `slack_format_instruction` が未設定の場合、システムプロンプトが変化しないことを確認
- LLMに渡されるメッセージにmrkdwn指示が含まれることを確認
