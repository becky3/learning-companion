"""パラメータスイープスクリプト.

Phase 1: vector_weight (α) を 0.0〜1.0 で 0.1 刻みにスイープ（threshold=None）
Phase 2: Phase 1 のベスト α で threshold を 0.4〜0.8 でスイープ
Phase 3: Phase 2 のベスト α/threshold で n_results を 3〜20 でスイープ

Usage:
    # テスト用ChromaDBの初期化（初回のみ）
    uv run python -m src.rag.cli init-test-db --persist-dir .tmp/rag-evaluation/chroma_db_test

    # 全Phase自動実行
    uv run python scripts/parameter_sweep.py \
      --chunk-size 200 --chunk-overlap 30

    # 個別Phase実行
    uv run python scripts/parameter_sweep.py --phase 1 \
      --chunk-size 200 --chunk-overlap 30
    uv run python scripts/parameter_sweep.py --phase 2 --best-alpha 0.6 \
      --chunk-size 200 --chunk-overlap 30
    uv run python scripts/parameter_sweep.py --phase 3 --best-alpha 0.6 --best-threshold none \
      --chunk-size 200 --chunk-overlap 30

    # 拡充データでスイープ実行
    uv run python scripts/parameter_sweep.py \
      --dataset tests/fixtures/rag_evaluation_extended/rag_evaluation_dataset_extended.json \
      --fixture tests/fixtures/rag_evaluation_extended/rag_test_documents_extended.json \
      --persist-dir .tmp/rag-evaluation-extended/chroma_db_test \
      --chunk-size 200 --chunk-overlap 30
"""

from __future__ import annotations

import argparse
import asyncio
import functools
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.rag.cli import (
    _build_bm25_index_from_fixture,
    create_rag_service,
)
from src.rag.evaluation import evaluate_retrieval

# 一時ファイル出力先
OUTPUT_DIR = Path(".tmp/rag-evaluation")
DEFAULT_PERSIST_DIR = str(OUTPUT_DIR / "chroma_db_test")

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


@dataclass
class SweepResult:
    """スイープ1回分の結果."""

    vector_weight: float
    threshold: float | None
    avg_f1: float
    avg_precision: float
    avg_recall: float
    avg_ndcg: float
    avg_mrr: float
    negative_violations: int
    category_f1: dict[str, float]
    n_results: int = 5


DEFAULT_DATASET = "tests/fixtures/rag_evaluation_dataset.json"
DEFAULT_FIXTURE = "tests/fixtures/rag_test_documents.json"


@functools.lru_cache(maxsize=4)
def load_query_categories(dataset_path: str) -> dict[str, str]:
    """評価データセットJSONからカテゴリマッピングを動的に読み取る."""
    with open(dataset_path, encoding="utf-8") as f:
        data = json.load(f)
    queries = data.get("queries", [])
    missing = [q.get("id", "<unknown>") for q in queries if "category" not in q]
    if missing:
        msg = f"クエリに category が設定されていません: ids={missing}"
        raise ValueError(msg)
    return {q["id"]: q["category"] for q in queries}


async def run_single_evaluation(
    vector_weight: float,
    threshold: float | None,
    dataset_path: str,
    fixture_path: str,
    chunk_size: int,
    chunk_overlap: int,
    n_results: int = 5,
    persist_dir: str | None = None,
) -> SweepResult:
    """単一パラメータセットで評価を実行."""
    bm25_index = _build_bm25_index_from_fixture(
        fixture_path, chunk_size=chunk_size, chunk_overlap=chunk_overlap,
    )
    rag_service = await create_rag_service(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        threshold=threshold,
        bm25_index=bm25_index,
        vector_weight=vector_weight,
        persist_dir=persist_dir,
    )

    report = await evaluate_retrieval(
        rag_service=rag_service,
        dataset_path=dataset_path,
        n_results=n_results,
    )

    # カテゴリ別F1を計算（JSONから動的に読み取ったカテゴリを使用）
    query_categories = load_query_categories(dataset_path)
    category_scores: dict[str, list[float]] = {}
    for qr in report.query_results:
        cat = query_categories.get(qr.query_id, "unknown")
        if cat not in category_scores:
            category_scores[cat] = []
        category_scores[cat].append(qr.f1)

    category_f1 = {
        cat: sum(scores) / len(scores) for cat, scores in category_scores.items()
    }

    return SweepResult(
        vector_weight=vector_weight,
        threshold=threshold,
        avg_f1=report.average_f1,
        avg_precision=report.average_precision,
        avg_recall=report.average_recall,
        avg_ndcg=report.average_ndcg,
        avg_mrr=report.average_mrr,
        negative_violations=len(report.negative_source_violations),
        category_f1=category_f1,
        n_results=n_results,
    )


def _format_category_cols(cat: dict[str, float]) -> str:
    """カテゴリ別F1のカラム文字列を生成."""
    return (
        f"{cat.get('normal', 0):>7.3f} | {cat.get('close_ranking', 0):>7.3f} | "
        f"{cat.get('method_mismatch', 0):>8.3f} | {cat.get('semantic_only', 0):>8.3f} | "
        f"{cat.get('noise_rejection', 0):>7.3f} | {cat.get('keyword_exact', 0):>7.3f}"
    )


CATEGORY_HEADER = (
    f"{'normal':>7} | {'close':>7} | {'mismatch':>8} | "
    f"{'semantic':>8} | {'noise':>7} | {'keyword':>7}"
)
METRIC_HEADER = f"{'F1':>6} | {'Prec':>6} | {'Rec':>6} | {'NDCG':>6} | {'MRR':>6} | {'NegV':>4}"


def print_results_table(results: list[SweepResult], phase: int) -> None:
    """結果テーブルを表示."""
    if phase == 1:
        print("\n" + "=" * 110)
        print("Phase 1: vector_weight (α) sweep  |  threshold = None")
        print("=" * 110)
        header = f"{'α':>6} | {METRIC_HEADER} | {CATEGORY_HEADER}"
    elif phase == 2:
        print("\n" + "=" * 110)
        print(f"Phase 2: threshold sweep  |  α = {results[0].vector_weight}")
        print("=" * 110)
        header = f"{'thresh':>6} | {METRIC_HEADER} | {CATEGORY_HEADER}"
    else:
        print("\n" + "=" * 110)
        print(
            f"Phase 3: n_results sweep  |  "
            f"α = {results[0].vector_weight}  |  "
            f"threshold = {results[0].threshold}",
        )
        print("=" * 110)
        header = f"{'n_res':>5} | {METRIC_HEADER} | {CATEGORY_HEADER}"

    print(header)
    print("-" * len(header))

    best_f1 = max(r.avg_f1 for r in results)

    for r in results:
        marker = " ***" if r.avg_f1 == best_f1 else ""
        if phase == 1:
            param = f"{r.vector_weight:>6.2f}"
        elif phase == 2:
            param = f"{r.threshold!s:>6}"
        else:
            param = f"{r.n_results:>5}"
        print(
            f"{param} | {r.avg_f1:>6.3f} | {r.avg_precision:>6.3f} | {r.avg_recall:>6.3f} | "
            f"{r.avg_ndcg:>6.3f} | {r.avg_mrr:>6.3f} | {r.negative_violations:>4} | "
            f"{_format_category_cols(r.category_f1)}{marker}"
        )


async def run_phase1(
    dataset_path: str, fixture_path: str,
    chunk_size: int, chunk_overlap: int,
    persist_dir: str | None = None,
    *,
    alpha_min: float = 0.0,
    alpha_max: float = 1.0,
    alpha_step: float = 0.1,
    n_results: int = 5,
) -> list[SweepResult]:
    """Phase 1: α スイープ."""
    alphas: list[float] = []
    val = alpha_min
    while val <= alpha_max + 1e-9:
        alphas.append(round(val, 2))
        val += alpha_step
    results: list[SweepResult] = []

    for alpha in alphas:
        logger.info("Phase 1: α=%.1f ...", alpha)
        result = await run_single_evaluation(
            vector_weight=alpha,
            threshold=None,
            dataset_path=dataset_path,
            fixture_path=fixture_path,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            n_results=n_results,
            persist_dir=persist_dir,
        )
        results.append(result)

    print_results_table(results, phase=1)

    best = max(results, key=lambda r: r.avg_f1)
    print(f"\n>>> Best α = {best.vector_weight} (F1 = {best.avg_f1:.3f})")
    return results


async def run_phase2(
    best_alpha: float, dataset_path: str, fixture_path: str,
    chunk_size: int, chunk_overlap: int,
    persist_dir: str | None = None,
    *,
    n_results: int = 5,
) -> list[SweepResult]:
    """Phase 2: threshold スイープ."""
    thresholds: list[float | None] = [None, 0.4, 0.5, 0.6, 0.7, 0.8]
    results: list[SweepResult] = []

    for thresh in thresholds:
        logger.info("Phase 2: threshold=%s, α=%.1f ...", thresh, best_alpha)
        result = await run_single_evaluation(
            vector_weight=best_alpha,
            threshold=thresh,
            dataset_path=dataset_path,
            fixture_path=fixture_path,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            n_results=n_results,
            persist_dir=persist_dir,
        )
        results.append(result)

    print_results_table(results, phase=2)

    best = max(results, key=lambda r: r.avg_f1)
    print(f"\n>>> Best threshold = {best.threshold} (F1 = {best.avg_f1:.3f})")
    return results


def _sweep_result_to_dict(r: SweepResult) -> dict[str, object]:
    """SweepResult を JSON 出力用の辞書に変換."""
    return {
        "vector_weight": r.vector_weight,
        "threshold": r.threshold,
        "n_results": r.n_results,
        "avg_f1": r.avg_f1,
        "avg_precision": r.avg_precision,
        "avg_recall": r.avg_recall,
        "avg_ndcg": r.avg_ndcg,
        "avg_mrr": r.avg_mrr,
        "negative_violations": r.negative_violations,
        "category_f1": r.category_f1,
    }


def _build_json_output(
    phase1_results: list[SweepResult],
    phase2_results: list[SweepResult],
    phase3_results: list[SweepResult],
    best1: SweepResult,
    best2: SweepResult,
    best3: SweepResult,
) -> dict[str, object]:
    """全Phase結果のJSON出力を構築."""
    return {
        "phase1": [_sweep_result_to_dict(r) for r in phase1_results],
        "phase2": [_sweep_result_to_dict(r) for r in phase2_results],
        "phase3": [_sweep_result_to_dict(r) for r in phase3_results],
        "recommendation": {
            "vector_weight": best1.vector_weight,
            "threshold": best2.threshold,
            "n_results": best3.n_results,
            "expected_f1": best3.avg_f1,
        },
    }


async def run_phase3(
    best_alpha: float, best_threshold: float | None,
    dataset_path: str, fixture_path: str,
    chunk_size: int, chunk_overlap: int,
    persist_dir: str | None = None,
) -> list[SweepResult]:
    """Phase 3: n_results スイープ."""
    n_results_values = [3, 5, 7, 10, 15, 20]
    results: list[SweepResult] = []

    for n_res in n_results_values:
        logger.info(
            "Phase 3: n_results=%d, α=%.1f, threshold=%s ...",
            n_res, best_alpha, best_threshold,
        )
        result = await run_single_evaluation(
            vector_weight=best_alpha,
            threshold=best_threshold,
            dataset_path=dataset_path,
            fixture_path=fixture_path,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            n_results=n_res,
            persist_dir=persist_dir,
        )
        results.append(result)

    print_results_table(results, phase=3)

    best = max(results, key=lambda r: r.avg_f1)
    print(f"\n>>> Best n_results = {best.n_results} (F1 = {best.avg_f1:.3f})")
    return results


async def main_async(args: argparse.Namespace) -> None:
    """メイン処理."""
    dataset_path = args.dataset
    fixture_path = args.fixture
    persist_dir = args.persist_dir
    chunk_size = args.chunk_size
    chunk_overlap = args.chunk_overlap

    n_results = args.n_results

    if args.phase in (1, 0):
        phase1_results = await run_phase1(
            dataset_path, fixture_path,
            chunk_size=chunk_size, chunk_overlap=chunk_overlap,
            persist_dir=persist_dir,
            alpha_min=args.alpha_min,
            alpha_max=args.alpha_max,
            alpha_step=args.alpha_step,
            n_results=n_results,
        )

        if args.phase == 0:
            # 全自動: Phase 1 → 2 → 3 をチェーン
            best_alpha = max(phase1_results, key=lambda r: r.avg_f1).vector_weight
            phase2_results = await run_phase2(
                best_alpha, dataset_path, fixture_path,
                chunk_size=chunk_size, chunk_overlap=chunk_overlap,
                persist_dir=persist_dir,
                n_results=n_results,
            )

            best2 = max(phase2_results, key=lambda r: r.avg_f1)
            phase3_results = await run_phase3(
                best_alpha, best2.threshold,
                dataset_path, fixture_path,
                chunk_size=chunk_size, chunk_overlap=chunk_overlap,
                persist_dir=persist_dir,
            )

            # サマリー出力
            best1 = max(phase1_results, key=lambda r: r.avg_f1)
            best3 = max(phase3_results, key=lambda r: r.avg_f1)
            print("\n" + "=" * 60)
            print("FINAL SUMMARY")
            print("=" * 60)
            print(f"Phase 1 best: α={best1.vector_weight}, F1={best1.avg_f1:.3f}")
            print(f"Phase 2 best: threshold={best2.threshold}, F1={best2.avg_f1:.3f}")
            print(f"Phase 3 best: n_results={best3.n_results}, F1={best3.avg_f1:.3f}")

            # JSON出力
            output = _build_json_output(
                phase1_results, phase2_results, phase3_results,
                best1, best2, best3,
            )
            output_path = OUTPUT_DIR / "sweep_results.json"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(output, f, ensure_ascii=False, indent=2)
            print(f"\nResults saved to: {output_path}")

    elif args.phase == 2:
        if args.best_alpha is None:
            print("ERROR: --best-alpha is required for Phase 2")
            sys.exit(1)
        await run_phase2(
            args.best_alpha, dataset_path, fixture_path,
            chunk_size=chunk_size, chunk_overlap=chunk_overlap,
            persist_dir=persist_dir,
            n_results=n_results,
        )

    elif args.phase == 3:
        if args.best_alpha is None:
            print("ERROR: --best-alpha is required for Phase 3")
            sys.exit(1)
        await run_phase3(
            args.best_alpha, args.best_threshold,
            dataset_path, fixture_path,
            chunk_size=chunk_size, chunk_overlap=chunk_overlap,
            persist_dir=persist_dir,
        )


def _parse_threshold(value: str) -> float | None:
    """CLI引数の threshold をパース. 'none' → None, 数値 → float."""
    if value.lower() == "none":
        return None
    return float(value)


def main() -> None:
    """エントリポイント."""
    parser = argparse.ArgumentParser(description="RAG Parameter Sweep")
    parser.add_argument(
        "--phase",
        type=int,
        default=0,
        choices=[0, 1, 2, 3],
        help="Phase to run: 0=all (default), 1=α only, 2=threshold only, 3=n_results only",
    )
    parser.add_argument(
        "--best-alpha",
        type=float,
        help="Best α from Phase 1 (required for --phase 2/3)",
    )
    parser.add_argument(
        "--best-threshold",
        type=_parse_threshold,
        help="Best threshold from Phase 2 (for --phase 3). Use 'none' for None",
    )
    parser.add_argument(
        "--alpha-min",
        type=float,
        default=0.0,
        help="Phase 1 α sweep minimum (default: 0.0)",
    )
    parser.add_argument(
        "--alpha-max",
        type=float,
        default=1.0,
        help="Phase 1 α sweep maximum (default: 1.0)",
    )
    parser.add_argument(
        "--alpha-step",
        type=float,
        default=0.1,
        help="Phase 1 α sweep step size (default: 0.1)",
    )
    parser.add_argument(
        "--n-results",
        type=int,
        default=5,
        help="各クエリで取得する結果数 (default: 5)",
    )
    parser.add_argument(
        "--dataset",
        type=str,
        default=DEFAULT_DATASET,
        help=f"評価データセットのパス（デフォルト: {DEFAULT_DATASET}）",
    )
    parser.add_argument(
        "--fixture",
        type=str,
        default=DEFAULT_FIXTURE,
        help=f"テストドキュメントフィクスチャのパス（デフォルト: {DEFAULT_FIXTURE}）",
    )
    parser.add_argument(
        "--persist-dir",
        type=str,
        default=DEFAULT_PERSIST_DIR,
        help=f"ChromaDB永続化ディレクトリ（デフォルト: {DEFAULT_PERSIST_DIR}）",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        required=True,
        help="チャンクサイズ",
    )
    parser.add_argument(
        "--chunk-overlap",
        type=int,
        required=True,
        help="チャンクオーバーラップ",
    )
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
