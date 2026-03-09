# AI Assistant — 開発ガイドライン

## プロジェクト基盤情報

@README.md
@docs/specs/overview.md

## LLM使い分けルール

- **デフォルト**: 全サービスでローカルLLM（LM Studio）を使用
- **設定変更**: `.env` で各サービスごとにLLMを変更可能
  - `CHAT_LLM_PROVIDER` / `PROFILER_LLM_PROVIDER` / `TOPIC_LLM_PROVIDER` / `SUMMARIZER_LLM_PROVIDER`
  - 各設定は `"local"` または `"online"` を指定（デフォルト: `"local"`）
- `MCP_ENABLED` — MCP機能の有効/無効（デフォルト: `false`）。MCPサーバー（`mcp_servers/` 配下）は `src/` のモジュールを import しないこと
- `RAG_ENABLED` — RAG機能の有効/無効（デフォルト: `false`）。詳細は `docs/specs/infrastructure/rag-knowledge.md` 参照

## 自動進行ルール（auto-progress）

自動実装の詳細ルール・品質チェック手順・GA環境の制約は `.claude/CLAUDE-auto-progress.md` を参照。

## Claude Code 拡張機能

### 自律呼び出しルール（プロジェクト固有）

以下はプロジェクト固有のルール:

| ユーザー表現 | 呼び出し先 | 種別 |
|-------------|-----------|------|
| 「テスト実行して」「テスト通して」 | test-runner | エージェント |
| 「自動マージレビューチェックして」 | `/check-review-batch` | スキル |
