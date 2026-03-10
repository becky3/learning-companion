# RAG ナレッジ

## 概要

外部 Web ページから収集した知識をベクトル DB に蓄積し、
チャット応答時に関連情報を自動検索して活用する
RAG（Retrieval-Augmented Generation）基盤。

RAG 機能は独立リポジトリ（rag-knowledge）に移行済み。
MCP サーバーとして外部プロセスで動作し、HTTP トランスポート（Streamable HTTP）で接続する。

## 背景

- LLM の学習済み知識とリアルタイムの会話コンテキストのみでは、特定 Web サイトの情報に基づいた回答ができない
- 知識ベースの蓄積・検索を MCP サーバーとして独立させ、本体アプリケーションとの疎結合を維持したい
- 独立リポジトリ化により、RAG 固有の依存・テスト・設定を分離した

## 制約

- RAG の実装・設定・テストは rag-knowledge リポジトリで管理する
- ai-assistant からは MCP サーバー設定（`config/mcp_servers.json`）で RAG サーバーに HTTP 接続する
- RAG サーバーは別プロセスとして事前に起動しておく必要がある
- RAG の利用可否は MCP 基盤の有効化と MCP サーバー設定への登録で決まる

## インターフェース

### MCP ツール

RAG MCP サーバーが公開するツール。詳細は rag-knowledge リポジトリの仕様書を参照。

| ツール | 概要 |
| --- | --- |
| rag_search | ベクトル検索と BM25 の生結果を個別に返す |
| rag_add | 単一ページをクロールして取り込む |
| rag_crawl | リンク集ページから一括クロールして取り込む |
| rag_delete | ソース URL 指定でナレッジを削除する |
| rag_stats | 統計情報を返す |

### チャット統合

LLM がツールループ内で rag_search を呼ぶかどうかを自律的に判断する。
MCP サーバー設定の指示文により、ナレッジベース関連の質問時に検索を促す。

## 外部連携

| 連携先 | 用途 | 接続方式 |
| --- | --- | --- |
| rag-knowledge リポジトリ | RAG MCP サーバー | HTTP（Streamable HTTP） |

## 関連ドキュメント

- [MCP 統合](mcp-integration.md) --- MCP サーバーの接続管理・ツール呼び出し基盤
- [chat-response](../features/chat-response.md) --- チャット応答（ソース URL 付与）
