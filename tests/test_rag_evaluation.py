"""RAG評価メトリクスのテスト

仕様: docs/specs/f9-rag-knowledge.md (Phase 2評価機能)
"""

from __future__ import annotations

import pytest

from src.rag.evaluation import (
    PrecisionRecallResult,
    calculate_precision_recall,
    check_negative_sources,
)


class TestCalculatePrecisionRecall:
    """calculate_precision_recall() のテスト."""

    def test_perfect_match(self) -> None:
        """完全一致の場合、Precision=1.0, Recall=1.0, F1=1.0."""
        retrieved = ["https://a.com", "https://b.com"]
        expected = ["https://a.com", "https://b.com"]

        result = calculate_precision_recall(retrieved, expected)

        assert result.precision == 1.0
        assert result.recall == 1.0
        assert result.f1 == 1.0
        assert result.true_positives == 2
        assert result.false_positives == 0
        assert result.false_negatives == 0

    def test_partial_match(self) -> None:
        """部分一致の場合のPrecision/Recall計算."""
        # 3件取得、2件が正解
        retrieved = ["https://a.com", "https://b.com", "https://c.com"]
        # 正解は2件、うち1件のみ取得
        expected = ["https://a.com", "https://d.com"]

        result = calculate_precision_recall(retrieved, expected)

        # Precision = 1/3 (取得3件中、正解1件)
        assert result.precision == pytest.approx(1 / 3)
        # Recall = 1/2 (正解2件中、取得1件)
        assert result.recall == pytest.approx(1 / 2)
        # F1 = 2 * (1/3 * 1/2) / (1/3 + 1/2) = 2 * (1/6) / (5/6) = 2/5 = 0.4
        assert result.f1 == pytest.approx(0.4)
        assert result.true_positives == 1
        assert result.false_positives == 2
        assert result.false_negatives == 1

    def test_no_match(self) -> None:
        """一致なしの場合、Precision=0, Recall=0, F1=0."""
        retrieved = ["https://a.com", "https://b.com"]
        expected = ["https://c.com", "https://d.com"]

        result = calculate_precision_recall(retrieved, expected)

        assert result.precision == 0.0
        assert result.recall == 0.0
        assert result.f1 == 0.0
        assert result.true_positives == 0
        assert result.false_positives == 2
        assert result.false_negatives == 2

    def test_empty_retrieved(self) -> None:
        """取得結果が空の場合."""
        retrieved: list[str] = []
        expected = ["https://a.com"]

        result = calculate_precision_recall(retrieved, expected)

        # 何も取得しなかった場合、Precision=0（期待があるのに取得なし）
        assert result.precision == 0.0
        # Recall=0（正解1件中、取得0件）
        assert result.recall == 0.0
        assert result.f1 == 0.0
        assert result.true_positives == 0
        assert result.false_positives == 0
        assert result.false_negatives == 1

    def test_empty_expected(self) -> None:
        """期待結果が空の場合（何も期待しない）."""
        retrieved = ["https://a.com"]
        expected: list[str] = []

        result = calculate_precision_recall(retrieved, expected)

        # 期待がないのに取得してしまった場合、Precision=0
        assert result.precision == 0.0
        # 期待がないのに取得した場合、Recall=0（本来不要なものを取得）
        assert result.recall == 0.0
        assert result.f1 == 0.0
        assert result.true_positives == 0
        assert result.false_positives == 1
        assert result.false_negatives == 0

    def test_both_empty(self) -> None:
        """両方空の場合（完璧）."""
        retrieved: list[str] = []
        expected: list[str] = []

        result = calculate_precision_recall(retrieved, expected)

        # 何も期待せず、何も取得しなかった = 完璧
        assert result.precision == 1.0
        assert result.recall == 1.0
        assert result.f1 == 1.0
        assert result.true_positives == 0
        assert result.false_positives == 0
        assert result.false_negatives == 0

    def test_duplicates_are_ignored(self) -> None:
        """重複URLは1件としてカウントされること."""
        # 重複を含むリスト
        retrieved = ["https://a.com", "https://a.com", "https://b.com"]
        expected = ["https://a.com", "https://b.com", "https://b.com"]

        result = calculate_precision_recall(retrieved, expected)

        # 重複を除いた実質: retrieved={a, b}, expected={a, b}
        assert result.precision == 1.0
        assert result.recall == 1.0
        assert result.f1 == 1.0
        assert result.true_positives == 2

    def test_high_precision_low_recall(self) -> None:
        """高Precision・低Recallのケース（慎重な検索）."""
        # 1件だけ取得し、それは正解
        retrieved = ["https://a.com"]
        # 正解は3件
        expected = ["https://a.com", "https://b.com", "https://c.com"]

        result = calculate_precision_recall(retrieved, expected)

        # Precision = 1/1 = 1.0
        assert result.precision == 1.0
        # Recall = 1/3
        assert result.recall == pytest.approx(1 / 3)
        # F1 = 2 * (1 * 1/3) / (1 + 1/3) = 2/3 / (4/3) = 0.5
        assert result.f1 == pytest.approx(0.5)

    def test_low_precision_high_recall(self) -> None:
        """低Precision・高Recallのケース（積極的な検索）."""
        # 5件取得し、期待の2件はすべて含む
        retrieved = [
            "https://a.com",
            "https://b.com",
            "https://c.com",
            "https://d.com",
            "https://e.com",
        ]
        expected = ["https://a.com", "https://b.com"]

        result = calculate_precision_recall(retrieved, expected)

        # Precision = 2/5 = 0.4
        assert result.precision == pytest.approx(0.4)
        # Recall = 2/2 = 1.0
        assert result.recall == 1.0
        # F1 = 2 * (0.4 * 1.0) / (0.4 + 1.0) = 0.8 / 1.4
        assert result.f1 == pytest.approx(0.8 / 1.4)


class TestCheckNegativeSources:
    """check_negative_sources() のテスト."""

    def test_no_negative_found(self) -> None:
        """禁止ソースが含まれていない場合、空リストを返す."""
        retrieved = ["https://safe1.com", "https://safe2.com"]
        negative = ["https://bad.com"]

        result = check_negative_sources(retrieved, negative)

        assert result == []

    def test_negative_found(self) -> None:
        """禁止ソースが含まれている場合、そのリストを返す."""
        retrieved = ["https://safe.com", "https://bad1.com", "https://bad2.com"]
        negative = ["https://bad1.com", "https://bad2.com", "https://bad3.com"]

        result = check_negative_sources(retrieved, negative)

        assert set(result) == {"https://bad1.com", "https://bad2.com"}

    def test_empty_retrieved(self) -> None:
        """取得結果が空の場合、空リストを返す."""
        retrieved: list[str] = []
        negative = ["https://bad.com"]

        result = check_negative_sources(retrieved, negative)

        assert result == []

    def test_empty_negative(self) -> None:
        """禁止リストが空の場合、空リストを返す."""
        retrieved = ["https://any.com"]
        negative: list[str] = []

        result = check_negative_sources(retrieved, negative)

        assert result == []

    def test_issue_176_scenario(self) -> None:
        """Issue #176のシナリオ: しれんのしろ検索で別ゲームのデータが混入."""
        # 「しれんのしろ アイテム」で検索した結果
        retrieved = [
            "https://example.com/dq3/dungeon/shirennoshiro.html",  # 正解
            "https://example.com/ff1/dungeon/trial.html",  # FF1のデータ（混入）
            "https://example.com/dq6/dungeon/trial.html",  # DQ6のデータ（混入）
        ]
        # 含まれてはいけないソース
        negative = [
            "https://example.com/ff1/dungeon/trial.html",
            "https://example.com/dq6/dungeon/trial.html",
        ]

        result = check_negative_sources(retrieved, negative)

        # 2件の禁止ソースが検出される
        assert len(result) == 2
        assert "https://example.com/ff1/dungeon/trial.html" in result
        assert "https://example.com/dq6/dungeon/trial.html" in result


class TestPrecisionRecallResult:
    """PrecisionRecallResult データクラスのテスト."""

    def test_dataclass_fields(self) -> None:
        """データクラスのフィールドが正しく設定されること."""
        result = PrecisionRecallResult(
            precision=0.8,
            recall=0.6,
            f1=0.685,
            true_positives=3,
            false_positives=1,
            false_negatives=2,
        )

        assert result.precision == 0.8
        assert result.recall == 0.6
        assert result.f1 == 0.685
        assert result.true_positives == 3
        assert result.false_positives == 1
        assert result.false_negatives == 2
