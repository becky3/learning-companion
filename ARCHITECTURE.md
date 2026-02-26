# アーキテクチャガイド

本ドキュメントはプロジェクトのディレクトリ構成とモジュール責務をフォルダ単位で記述する。ファイル単位の詳細は意図的に省略しており、各モジュールの役割と関係性の把握を目的とする。

## トップレベル構造

| ディレクトリ | 説明 |
|---|---|
| `src/` | アプリケーション本体 |
| `mcp_servers/` | MCP サーバー群（独立プロセスとして動作） |
| `config/` | アシスタント設定・MCP サーバー接続設定 |
| `docs/` | 仕様書・テンプレート |
| `tests/` | テストコード・フィクスチャ |
| `scripts/` | 運用・開発用スクリプト |
| `.claude/` | Claude Code 拡張（エージェント・スキル・Hooks） |
| `.github/` | GitHub Actions ワークフロー・PR テンプレート・Copilot 設定 |

## src/ モジュール構成

### サブディレクトリ

| ディレクトリ | 責務 |
|---|---|
| `src/config/` | pydantic-settings による環境変数・設定管理 |
| `src/db/` | SQLAlchemy モデル定義・DB セッション管理 |
| `src/llm/` | LLM プロバイダー抽象化（ローカル / OpenAI / Anthropic）とファクトリ |
| `src/services/` | ビジネスロジック（チャット応答、RSS 収集、要約、プロファイリング、トピック提案等） |
| `src/slack/` | Slack Bolt アプリ初期化・イベントハンドラ |
| `src/messaging/` | メッセージング抽象化（Port/Adapter パターン。Slack アダプター、CLI アダプター） |
| `src/scheduler/` | APScheduler による定期実行ジョブ |
| `src/mcp_bridge/` | MCP サーバーへの接続管理（クライアント側ブリッジ） |

### ルートレベルファイル

| ファイル | 責務 |
|---|---|
| `src/main.py` | エントリーポイント（Bot 起動・管理コマンド振り分け） |
| `src/cli.py` | CLI アダプター起動エントリーポイント |
| `src/bot_manager.py` | Bot 管理コマンド（start / stop / restart / status） |
| `src/process_guard.py` | Bot 重複起動防止・PID ファイル管理 |
| `src/compat.py` | プラットフォーム互換ユーティリティ |

## mcp_servers/ モジュール構成

MCP サーバーは独立プロセスとして動作し、MCP プロトコル経由で `src/` と通信する。`src/` のモジュールを直接 import しないこと。

| ディレクトリ | 責務 |
|---|---|
| `mcp_servers/rag/` | RAG ナレッジサーバー（Web クロール、チャンキング、ベクトル検索、BM25 検索） |
| `mcp_servers/weather/` | 天気予報サーバー（気象庁 API） |

## 補助ディレクトリ

| ディレクトリ | 説明 |
|---|---|
| `config/` | `assistant.yaml`（アシスタント性格設定）、`mcp_servers.json`（MCP 接続設定） |
| `docs/specs/` | 機能仕様書・基盤仕様書・ワークフロー定義（実装の根拠） |
| `tests/` | pytest テストコード・フィクスチャ |
| `scripts/` | 運用・開発用シェルスクリプト |
| `.claude/` | Claude Code 設定・エージェント定義・スキル定義・Hooks スクリプト |
| `.github/` | GitHub Actions ワークフロー・PR テンプレート・Copilot 設定 |

## 仕様書 — 実装モジュール対応表

### features/

| 仕様書 | 実装モジュール |
|---|---|
| `features/chat-response.md` | `src/services/`, `src/llm/` |
| `features/feed-management.md` | `src/services/`, `src/scheduler/` |
| `features/user-profiling.md` | `src/services/`, `src/db/` |
| `features/topic-recommend.md` | `src/services/` |
| `features/auto-reply.md` | `src/slack/`, `src/messaging/` |
| `features/bot-status.md` | `src/slack/` |
| `features/thread-support.md` | `src/slack/`, `src/services/` |
| `features/slack-formatting.md` | `src/services/` |
| `features/cli-adapter.md` | `src/messaging/` |

### infrastructure/

| 仕様書 | 実装モジュール |
|---|---|
| `infrastructure/mcp-integration.md` | `src/mcp_bridge/`, `mcp_servers/` |
| `infrastructure/rag-knowledge.md` | `mcp_servers/rag/` |
| `infrastructure/bot-process-guard.md` | `src/process_guard.py`, `src/bot_manager.py` |

### workflows/

| 仕様書 | 対象 |
|---|---|
| `workflows/git-flow.md` | Git ブランチ運用 |
| `workflows/pr-body-template.md` | PR テンプレート |
| `workflows/github/auto-progress.md` | `.github/workflows/` |
| `workflows/github/copilot-auto-fix.md` | `.github/workflows/` |
| `workflows/github/claude-code-actions.md` | `.github/workflows/` |

### agentic/

| 仕様書 | 対象 |
|---|---|
| `agentic/agents/*.md` | `.claude/agents/` |
| `agentic/skills/*.md` | `.claude/skills/` |
| `agentic/teams/*.md` | チーム運用パターン |
| `agentic/hooks/*.md` | `.claude/scripts/` |

## 関連ドキュメント

- [全体仕様概要](docs/specs/overview.md) — 機能一覧・技術スタック・DB 設計
- [仕様書スタイルガイド](docs/specs/style-guide.md) — 仕様書の分類・命名規則・記述ルール
- [CLAUDE.md](CLAUDE.md) — 開発ガイドライン
