"""RAG MCPサーバーのテスト.

仕様: docs/specs/f9-rag.md
5つのRAGツール（rag_search, rag_add, rag_crawl, rag_delete, rag_stats）が
MCPサーバーとして公開されていることを検証する。
"""

from __future__ import annotations

from importlib import import_module

import pytest


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
