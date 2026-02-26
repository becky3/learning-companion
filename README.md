# AI Assistant

Slack上で動作するAI学習支援アシスタント。
RSS記事の自動収集・要約配信、チャットでの質問応答、ユーザーの興味に基づく学習トピック提案を行う。

コスト最適化のため、タスクの性質に応じてローカルLLM（LM Studio）とオンラインLLM（OpenAI / Anthropic）を使い分ける。

## 主な機能

- **チャット応答** — @メンションで質問に回答（オンラインLLM）
- **情報収集・配信** — RSSフィードから記事を収集・要約し、毎朝Slackに自動配信（要約はローカルLLM）
- **ユーザープロファイリング** — 会話から興味・スキル・目標を自動抽出（ローカルLLM）
- **学習トピック提案** — プロファイルと最新記事をもとにおすすめトピックを提案（オンラインLLM）
- **特定チャンネル自動返信** — 指定したチャンネルではメンションなしで全メッセージに自動応答
- **外部ツール連携（MCP）** — MCPプロトコルで外部ツールを動的に呼び出し（天気予報サンプル付属）
- **RAGナレッジ機能** — Webページを知識ベースに取り込み、質問に関連する情報を自動検索して回答に活用

## 動作環境

- **OS**: Windows 11（主要開発・運用環境）
- **ランタイム**: Python 3.11+
- **パッケージ管理**: uv

## 技術スタック

Python 3.11+ / uv / slack-bolt / OpenAI SDK / Anthropic SDK / SQLite + SQLAlchemy / feedparser / MCP SDK / ChromaDB / BeautifulSoup4

## セットアップ

```bash
uv sync
cp .env.example .env  # 各種トークン・APIキーを設定
```

### 主な環境変数

| 変数名 | 説明 |
|--------|------|
| `SLACK_BOT_TOKEN` | Slack Bot トークン |
| `SLACK_APP_TOKEN` | Slack App トークン（Socket Mode用） |
| `SLACK_NEWS_CHANNEL_ID` | フィード配信先チャンネルID |
| `SLACK_AUTO_REPLY_CHANNELS` | 自動返信を有効にするチャンネルID（カンマ区切り） |
| `CHAT_LLM_PROVIDER` | チャット応答のLLMプロバイダー（`local` / `online`） |
| `MCP_ENABLED` | MCP機能の有効/無効（`true` / `false`、デフォルト: `false`） |
| `RAG_ENABLED` | RAG機能の有効/無効（`true` / `false`、デフォルト: `false`） |

詳細は `.env.example` を参照してください。

## 起動

```bash
# フォアグラウンドで直接起動
uv run python -m src.main

# バックグラウンドで起動（管理コマンド）
uv run python -m src.main --start

# 停止 / 再起動 / 状態確認
uv run python -m src.main --stop
uv run python -m src.main --restart
uv run python -m src.main --status
```

## RAG評価CLI

RAG検索精度の評価パイプラインを提供します。

```bash
# テスト用DB初期化（ChromaDB + BM25）
uv run python -m mcp_servers.rag.cli init-test-db \
  --chunk-size 200 --chunk-overlap 30 \
  --persist-dir .tmp/test_chroma_db \
  --bm25-persist-dir .tmp/test_bm25_index \
  --fixture tests/fixtures/rag_test_documents.json

# RAG検索精度を評価
uv run python -m mcp_servers.rag.cli evaluate \
  --persist-dir .tmp/test_chroma_db \
  --output-dir .tmp/rag-evaluation \
  --chunk-size 200 --chunk-overlap 30 \
  --vector-weight 0.6 \
  --bm25-k1 1.5 --bm25-b 0.75
```

詳細は [RAGナレッジ機能仕様](docs/specs/f9-rag.md) を参照してください。

## プロジェクト構造

> **将来改善予定**: このセクションは ARCHITECTURE.md に切り出し、モジュール間の関係図や仕様書との対応表を追加予定（[#626](https://github.com/becky3/ai-assistant/issues/626)）

```
src/
  main.py           # エントリーポイント
  config/settings.py # pydantic-settings による環境変数管理
  db/models.py       # SQLAlchemy モデル (feeds, articles, user_profiles, conversations)
  db/session.py      # DB接続・セッション管理
  slack/app.py       # Slack Bolt AsyncApp 初期化
  slack/handlers.py  # イベントハンドラ
  llm/base.py        # LLMProvider ABC (全プロバイダーの共通インターフェース)
  llm/openai_provider.py
  llm/anthropic_provider.py
  llm/lmstudio_provider.py  # OpenAI SDK で base_url を localhost:1234 に向ける
  llm/factory.py     # プロバイダー生成ファクトリ
  bot_manager.py     # Bot管理コマンド (--start/--stop/--restart/--status)
  process_guard.py   # Bot重複起動防止・PIDファイル管理
  compat.py          # プラットフォーム互換ユーティリティ
  mcp_bridge/
    __init__.py
    client_manager.py  # MCPサーバー接続管理
  services/chat.py           # チャット応答 (オンラインLLM)
  services/feed_collector.py # RSS収集
  services/summarizer.py     # 記事要約 (ローカルLLM)
  services/user_profiler.py  # 会話からユーザー情報抽出 (ローカルLLM)
  services/topic_recommender.py # 学習トピック提案 (オンラインLLM)
  services/ogp_extractor.py   # OGPメタデータ抽出
  services/thread_history.py  # Slackスレッド履歴取得
  scheduler/jobs.py  # 配信ジョブ・フォーマット
mcp_servers/                 # MCPサーバー群（将来リポジトリ分離対象）
  weather/
    server.py          # 天気予報MCPサーバー（気象庁API）
  rag/
    server.py          # RAGナレッジMCPサーバー
    rag_knowledge.py   # RAGナレッジサービス
    web_crawler.py     # Webクローラー（RAG用）
    safe_browsing.py   # Google Safe Browsing API
    embedding/         # Embeddingプロバイダー（LM Studio / OpenAI）
config/
  assistant.yaml     # アシスタントの名前・性格・口調 (システムプロンプトに反映)
  mcp_servers.json   # MCPサーバー接続設定
docs/
  specs/             # 機能仕様書 (実装の根拠)
.claude/
  settings.json      # Claude Code 設定（hooks、サブエージェント定義など）
  agents/            # サブエージェント定義ファイル
  scripts/           # hooks用スクリプト
```

## 開発ガイドライン

**開発を始める前に必ず [CLAUDE.md](CLAUDE.md) を読んでください。**

CLAUDE.mdには以下の重要な情報が含まれています：

- 仕様駆動開発のルール
- コーディング規約
- Git運用フロー
- LLM使い分けルール
- サブエージェントの使用方法

### 開発フロー概要（git-flow）

本プロジェクトは git-flow ベースのブランチ戦略を採用。詳細は [git-flow仕様](docs/specs/workflows/git-flow.md) を参照。

1. Issue・Milestoneの確認 (`gh milestone list`, `gh issue list`)
2. 対象Issueの仕様書を読む (`docs/specs/`)
3. `develop` からブランチ作成 (`feature/{機能名}-#{Issue番号}`)
4. 実装・テスト
5. コミット (`type(scope): 説明 (#Issue番号)`)
6. `develop` に向けてPR作成 (`gh pr create --base develop`)

### テストと lint

```bash
# テスト実行
uv run pytest

# lint
uv run ruff check .

# 型チェック
uv run mypy src
```

## ドキュメント

### 機能仕様

- [全体仕様概要](docs/specs/overview.md)
- [F1: チャット応答](docs/specs/f1-chat.md)
- [F2: 情報収集・配信](docs/specs/f2-feed-collection.md)
- [F3: ユーザー情報抽出](docs/specs/f3-user-profiling.md)
- [F4: トピック提案](docs/specs/f4-topic-recommend.md)
- [F5: MCP統合](docs/specs/f5-mcp-integration.md)
- [F6: 特定チャンネル自動返信](docs/specs/f6-auto-reply.md)
- [F7: ボットステータス](docs/specs/f7-bot-status.md)
- [F8: スレッドサポート](docs/specs/f8-thread-support.md)
- [F9: RAGナレッジ](docs/specs/f9-rag.md)
- [F10: Slack mrkdwn形式対応](docs/specs/f10-slack-mrkdwn.md)
- [F11: CLIアダプター](docs/specs/f11-cli-adapter.md)

### 開発・運用

- [git-flow ブランチ運用](docs/specs/workflows/git-flow.md)
- [PR body テンプレート](docs/specs/workflows/pr-body-template.md)
- [Bot プロセスガード](docs/specs/bot-process-guard.md)
- [自動進行管理](docs/specs/auto-progress.md)
- [Copilot 自動修正ワークフロー](docs/specs/copilot-auto-fix.md)

### Claude Code 関連

- [Claude Code Hooks](docs/specs/claude-code-hooks.md)
- [Claude Code Actions](docs/specs/claude-code-actions.md)
- エージェントチーム: [共通仕様](docs/specs/agent-teams/common.md) / [fixed-theme](docs/specs/agent-teams/fixed-theme.md) / [mixed-genius](docs/specs/agent-teams/mixed-genius.md)
- [Planner サブエージェント](docs/specs/planner-agent.md)
- [Doc Reviewer サブエージェント](docs/specs/doc-review-agent.md)
- [Test Runner サブエージェント](docs/specs/test-runner-agent.md)
- [Code Reviewer サブエージェント](docs/specs/code-review-agent.md)
- [Doc Gen スキル](docs/specs/doc-gen-skill.md)
- [Handoff スキル](docs/specs/handoff-skill.md)
- [Check Review Batch スキル](docs/specs/check-review-batch-skill.md)
- [Topic スキル](docs/specs/topic-skill.md)
