"""ハイブリッド検索のテスト

仕様: docs/specs/f9-rag-chunking-hybrid.md
"""

from src.rag.hybrid_search import HybridSearchResult, reciprocal_rank_fusion


class TestReciprocalRankFusion:
    """reciprocal_rank_fusion関数のテスト."""

    def test_ac8_single_ranking(self) -> None:
        """単一のランキングでRRFスコアが計算される."""
        rankings = [["doc1", "doc2", "doc3"]]
        scores = reciprocal_rank_fusion(rankings, k=60)

        # 順位が高いほどスコアが高い
        assert scores["doc1"] > scores["doc2"]
        assert scores["doc2"] > scores["doc3"]

    def test_ac8_multiple_rankings_merged(self) -> None:
        """複数のランキングがマージされる."""
        rankings = [
            ["doc1", "doc2", "doc3"],  # ランキング1
            ["doc2", "doc1", "doc3"],  # ランキング2
        ]
        scores = reciprocal_rank_fusion(rankings, k=60)

        # doc1とdoc2は両方で上位なので高スコア
        assert scores["doc1"] > scores["doc3"]
        assert scores["doc2"] > scores["doc3"]

    def test_ac8_document_in_one_ranking_only(self) -> None:
        """片方のランキングにのみ存在するドキュメント."""
        rankings = [
            ["doc1", "doc2"],
            ["doc3", "doc4"],
        ]
        scores = reciprocal_rank_fusion(rankings, k=60)

        # すべてのドキュメントがスコアを持つ
        assert "doc1" in scores
        assert "doc3" in scores

    def test_rrf_k_parameter_affects_scores(self) -> None:
        """kパラメータがスコアに影響する."""
        rankings = [["doc1", "doc2"]]

        scores_k60 = reciprocal_rank_fusion(rankings, k=60)
        scores_k10 = reciprocal_rank_fusion(rankings, k=10)

        # kが小さいほどスコアの差が大きくなる
        diff_k60 = scores_k60["doc1"] - scores_k60["doc2"]
        diff_k10 = scores_k10["doc1"] - scores_k10["doc2"]
        assert diff_k10 > diff_k60


class TestHybridSearchResult:
    """HybridSearchResultクラスのテスト."""

    def test_result_with_both_scores(self) -> None:
        """両方のスコアを持つ結果."""
        result = HybridSearchResult(
            doc_id="doc1",
            text="テスト",
            metadata={"source_url": "http://example.com"},
            vector_distance=0.3,
            bm25_score=5.0,
            rrf_score=0.1,
        )

        assert result.vector_distance == 0.3
        assert result.bm25_score == 5.0
        assert result.rrf_score == 0.1

    def test_result_with_vector_only(self) -> None:
        """ベクトル検索のみの結果."""
        result = HybridSearchResult(
            doc_id="doc1",
            text="テスト",
            metadata={},
            vector_distance=0.3,
            bm25_score=None,
            rrf_score=0.05,
        )

        assert result.vector_distance == 0.3
        assert result.bm25_score is None

    def test_result_with_bm25_only(self) -> None:
        """BM25検索のみの結果."""
        result = HybridSearchResult(
            doc_id="doc1",
            text="テスト",
            metadata={},
            vector_distance=None,
            bm25_score=5.0,
            rrf_score=0.05,
        )

        assert result.vector_distance is None
        assert result.bm25_score == 5.0


# Note: HybridSearchEngineの完全なテストはベクトルストアのモックが必要
# 実際の統合テストはRAGKnowledgeServiceのテストで実施
