# F10: Slack mrkdwn形式対応

## 概要

LLMからの返信をSlack mrkdwn形式で出力させることで、Slack上での表示を適切にフォーマットする。

## 背景

LLMはデフォルトでMarkdown形式のテキストを生成するが、Slackは独自のmrkdwn形式を使用している。
そのため、`**太字**` がそのまま表示されるなど、装飾が正しくレンダリングされない問題がある。

## ユーザーストーリー

- ユーザーとして、Slackでボットの返信が適切にフォーマットされた状態で読みたい。
- ユーザーとして、太字・リスト・リンクなどの装飾が正しく表示された返信を受け取りたい。

## 設計方針

### 採用: プロンプト方式

システムプロンプトにSlack mrkdwn形式の出力指示を追加し、LLMに直接mrkdwn形式で
出力させる。

**理由**:

- 実装がシンプルで保守しやすい
- LLMは出力形式の指示に従う能力が高い
- 変換ロジックのバグリスク（正規表現の誤変換等）を回避できる

### 不採用: 後処理変換方式

LLMの出力をMarkdownからSlack mrkdwnに正規表現等で変換する方式。

**不採用理由**:

- 正規表現ベースの変換はエッジケース（ネストした装飾、コードブロック内のリテラル等）で
  誤変換のリスクがある
- 追加の変換モジュールが必要になり、保守コストが増加する

## 入出力仕様

### 入力

変更なし（既存のSlackイベント入力をそのまま使用）

### 出力

LLMの応答がSlack mrkdwn形式でフォーマットされる。

### Markdown → Slack mrkdwn 変換ルール

| 要素 | Markdown | Slack mrkdwn |
|------|----------|--------------|
| 太字 | `**text**` | `*text*` |
| イタリック | `_text_` | `_text_` |
| 取り消し線 | `~~text~~` | `~text~` |
| インラインコード | `` `code` `` | `` `code` `` |
| コードブロック | ` ```lang ` | ` ``` ` |
| リスト | `- item` | `- item`（Slack互換） |
| リンク | `[text](url)` | `<url\|text>` |
| 引用 | `> text` | `> text`（Slack互換） |
| 見出し | `### text` | `*text*`（太字で代替） |

## 実装仕様

### 変更箇所

#### 1. `config/assistant.yaml` — フォーマット指示の追加

`slack_format_instruction` キーにSlack mrkdwn形式の出力ルールを定義する。

#### 2. `src/main.py` — システムプロンプトへの追加

`load_assistant_config()` で読み込んだ `slack_format_instruction` を
システムプロンプト（`personality`）に追記してからChatServiceに渡す。

```python
system_prompt = assistant.get("personality", "")
slack_instruction = assistant.get("slack_format_instruction", "")
if slack_instruction:
    system_prompt = system_prompt + "\n\n" + slack_instruction
```

## 受け入れ条件

- [ ] AC1: `config/assistant.yaml` に `slack_format_instruction` が定義されている
- [ ] AC2: システムプロンプトに `slack_format_instruction` の内容が追記される
- [ ] AC3: `slack_format_instruction` が未定義・空の場合は既存動作に影響しない

## 関連ファイル

| ファイル | 役割 |
|---------|------|
| `config/assistant.yaml` | アシスタント設定（フォーマット指示を追加） |
| `src/main.py` | エントリーポイント（システムプロンプト構築） |
| `src/services/chat.py` | チャットサービス（変更なし） |
| `src/config/settings.py` | 設定読み込み（変更なし） |

## テスト方針

- `slack_format_instruction` がシステムプロンプトに追記されることをテスト
- `slack_format_instruction` が空・未定義の場合に既存動作が変わらないことをテスト
