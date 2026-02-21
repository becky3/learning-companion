# RAG評価データ収集・管理ガイド

## 概要

RAGハイブリッド検索のパラメータ最適化には、十分なドキュメント数とクエリ数が必要です。
このガイドでは、Wikipedia APIを使った評価データの収集手順と、評価クエリの設計方針を説明します。

## データ構成

### 既存データ（ユニットテスト用）

| ファイル | 内容 |
|---------|------|
| `tests/fixtures/rag_test_documents.json` | 15件のテストドキュメント（架空RPG「勇者の冒険」） |
| `tests/fixtures/rag_evaluation_dataset.json` | 18件の評価クエリ |

### 拡充データ（パラメータスイープ用）

| ファイル | 内容 |
|---------|------|
| `tests/fixtures/rag_evaluation_extended/rag_test_documents_extended.json` | 101件のドキュメント（Wikipedia） |
| `tests/fixtures/rag_evaluation_extended/rag_evaluation_dataset_extended.json` | 55件の評価クエリ |

## データ収集手順

### 1. トピック設定の確認

`scripts/eval_data_config.json` にテーマ別クラスタが定義されています。

```bash
# 収集対象の一覧を確認（実際には取得しない）
uv run python scripts/collect_evaluation_data.py --dry-run
```

### 2. データ収集の実行

```bash
# Wikipedia APIからドキュメントを収集
uv run python scripts/collect_evaluation_data.py --config scripts/eval_data_config.json
```

**注意事項:**

- Wikipedia API のレート制限に配慮し、リクエスト間隔はデフォルト1秒
- 各ドキュメントは先頭2000文字に制限（サイズ均一化）
- ライセンス: CC BY-SA 4.0

### 3. テスト用DBの初期化（ChromaDB + BM25）

```bash
uv run python -m mcp_servers.rag.cli init-test-db \
  --chunk-size 200 --chunk-overlap 30 \
  --persist-dir .tmp/rag-evaluation-extended/chroma_db_test \
  --bm25-persist-dir .tmp/rag-evaluation-extended/bm25_index_test \
  --fixture tests/fixtures/rag_evaluation_extended/rag_test_documents_extended.json
```

### 4. パラメータスイープの実行

```bash
uv run python scripts/parameter_sweep.py \
  --dataset tests/fixtures/rag_evaluation_extended/rag_evaluation_dataset_extended.json \
  --fixture tests/fixtures/rag_evaluation_extended/rag_test_documents_extended.json \
  --persist-dir .tmp/rag-evaluation-extended/chroma_db_test
```

## トピック設計の考え方

### テーマ別クラスタ

| クラスタ | 目的 | 例 |
|---------|------|-----|
| japanese_history | 日本史の人物・事件 | 織田信長、関ヶ原の戦い |
| japanese_food | 日本の食文化 | 寿司、ラーメン、天ぷら |
| technology | 情報技術・AI | 人工知能、機械学習 |
| japanese_geography | 日本の地理・都市 | 富士山、東京都、北海道 |
| science | 自然科学 | 量子力学、光合成、DNA |
| culture | 日本の伝統文化・武道 | 歌舞伎、柔道、茶道 |
| games | ゲーム関連 | 将棋、ドラゴンクエスト |
| noise_topics | ノイズ排除テスト用 | サッカー、バスケットボール |

### 言語比率

- 日本語: 約70%（BM25の日本語トークナイザ検証が主目的）
- 英語: 約30%（多言語対応のベースライン確認）

## 評価クエリ設計ガイドライン

### 6カテゴリ

| カテゴリ | 件数目安 | 設計方針 |
|---------|----------|---------|
| normal | 15-20 | 基本的な事実質問。正解ドキュメントが明確 |
| close_ranking | 8-10 | 類似トピック比較。2つ以上の関連ドキュメントを正しくランキング |
| method_mismatch | 8-10 | vector/BM25で異なるランキングになるケース |
| semantic_only | 8-10 | 抽象クエリ。BM25ではヒットしにくい |
| noise_rejection | 5-8 | 無関係クエリ。expected_sourcesは空 |
| keyword_exact | 5-8 | 固有名詞の完全一致。BM25が有利 |

### 設計時の注意

- `expected_sources`: Wikipedia URL で指定。ドキュメントの `source_url` と一致させる
- `negative_sources`: テーマ間の混同を検出するケースに設定
- `category`: 各クエリに必ず明示（`parameter_sweep.py` が動的に読み取る）

## 関連ドキュメント

- [RAGナレッジ機能仕様](../specs/f9-rag.md)
- [RAGシステム概要](rag-overview.md)
