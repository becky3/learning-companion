"""RAG MCPサーバーのテスト.

仕様: docs/specs/f9-rag.md
5つのRAGツール（rag_search, rag_add, rag_crawl, rag_delete, rag_stats）が
MCPサーバーとして公開されていることを検証する。
"""

from __future__ import annotations

from importlib import import_module
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_servers.rag.rag_knowledge import (
    BM25SearchItem,
    RawSearchResults,
    VectorSearchItem,
)


@pytest.mark.asyncio
async def test_ac20_rag_server_exposes_five_tools() -> None:
    """AC20: RAG MCPサーバーが5つのツールを公開すること."""
    mod = import_module("mcp_servers.rag.server")
    server = mod.mcp

    tools = await server.list_tools()
    tool_names = {t.name for t in tools}

    expected = {"rag_search", "rag_add", "rag_crawl", "rag_delete", "rag_stats"}
    assert tool_names == expected, f"Expected {expected}, got {tool_names}"


@pytest.mark.asyncio
async def test_ac20_rag_server_tool_count() -> None:
    """AC20: RAG MCPサーバーのツール数が正確に5であること."""
    mod = import_module("mcp_servers.rag.server")
    server = mod.mcp

    tools = await server.list_tools()
    assert len(tools) == 5


class TestRagSearchOutput:
    """rag_search ツールの出力フォーマットテスト（準Agentic Search, Issue #548）."""

    @pytest.fixture(autouse=True)
    def _patch_rag_service(self) -> None:
        """rag_search のテスト用に RAGKnowledgeService をモックする."""
        self.mock_service = AsyncMock()
        self.mock_settings = MagicMock()
        self.mock_settings.rag_retrieval_count = 3

    async def test_output_contains_vector_and_bm25_sections(self) -> None:
        """出力にベクトル検索結果とBM25検索結果のセクションが含まれること（#548）."""
        mod = import_module("mcp_servers.rag.server")

        self.mock_service.retrieve_raw_results = AsyncMock(
            return_value=RawSearchResults(
                vector_results=[
                    VectorSearchItem(
                        text="ベクトルの結果テキスト",
                        source_url="https://example.com/vec1",
                        distance=0.234,
                        chunk_index=0,
                    ),
                ],
                bm25_results=[
                    BM25SearchItem(
                        text="BM25の結果テキスト",
                        source_url="https://example.com/bm25_1",
                        score=4.521,
                        doc_id="doc1",
                    ),
                ],
            )
        )

        with (
            patch.object(mod, "_get_rag_service", return_value=self.mock_service),
            patch.object(mod, "get_settings", return_value=self.mock_settings),
        ):
            result = await mod.rag_search("テストクエリ")

        assert "## ベクトル検索結果 (意味的類似度)" in result
        assert "## BM25検索結果 (キーワード一致)" in result

    async def test_output_contains_source_urls(self) -> None:
        """出力に Source: URL 行が含まれること（#548）."""
        mod = import_module("mcp_servers.rag.server")

        self.mock_service.retrieve_raw_results = AsyncMock(
            return_value=RawSearchResults(
                vector_results=[
                    VectorSearchItem(
                        text="テキスト",
                        source_url="https://example.com/page1",
                        distance=0.1,
                        chunk_index=0,
                    ),
                ],
                bm25_results=[],
            )
        )

        with (
            patch.object(mod, "_get_rag_service", return_value=self.mock_service),
            patch.object(mod, "get_settings", return_value=self.mock_settings),
        ):
            result = await mod.rag_search("テスト")

        assert "Source: https://example.com/page1" in result

    async def test_output_contains_raw_scores(self) -> None:
        """出力に生スコアが含まれること（#548）."""
        mod = import_module("mcp_servers.rag.server")

        self.mock_service.retrieve_raw_results = AsyncMock(
            return_value=RawSearchResults(
                vector_results=[
                    VectorSearchItem(
                        text="テキスト",
                        source_url="https://example.com/v",
                        distance=0.567,
                        chunk_index=0,
                    ),
                ],
                bm25_results=[
                    BM25SearchItem(
                        text="テキスト",
                        source_url="https://example.com/b",
                        score=3.456,
                        doc_id="d1",
                    ),
                ],
            )
        )

        with (
            patch.object(mod, "_get_rag_service", return_value=self.mock_service),
            patch.object(mod, "get_settings", return_value=self.mock_settings),
        ):
            result = await mod.rag_search("テスト")

        assert "[distance=0.567]" in result
        assert "[score=3.456]" in result

    async def test_empty_results_returns_not_found_message(self) -> None:
        """0件時に「該当する情報が見つかりませんでした」が返ること."""
        mod = import_module("mcp_servers.rag.server")

        self.mock_service.retrieve_raw_results = AsyncMock(
            return_value=RawSearchResults(
                vector_results=[],
                bm25_results=[],
            )
        )

        with (
            patch.object(mod, "_get_rag_service", return_value=self.mock_service),
            patch.object(mod, "get_settings", return_value=self.mock_settings),
        ):
            result = await mod.rag_search("存在しないクエリ")

        assert result == "該当する情報が見つかりませんでした"
