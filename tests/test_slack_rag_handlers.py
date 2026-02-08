"""Slack ragコマンドハンドラのテスト."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.slack.handlers import (
    _handle_rag_add,
    _handle_rag_crawl,
    _handle_rag_delete,
    _handle_rag_status,
    _parse_rag_command,
)


class TestParseRagCommand:
    """_parse_rag_command関数のテスト."""

    def test_crawl_with_url(self) -> None:
        """ragコマンド解析: crawl URL."""
        subcommand, url, pattern, raw = _parse_rag_command(
            "rag crawl https://example.com/docs"
        )
        assert subcommand == "crawl"
        assert url == "https://example.com/docs"
        assert pattern == ""
        assert raw == "https://example.com/docs"

    def test_crawl_with_url_and_pattern(self) -> None:
        """ragコマンド解析: crawl URL パターン."""
        subcommand, url, pattern, raw = _parse_rag_command(
            "rag crawl https://example.com/docs /api/"
        )
        assert subcommand == "crawl"
        assert url == "https://example.com/docs"
        assert pattern == "/api/"
        assert raw == "https://example.com/docs"

    def test_crawl_with_url_and_pattern_with_spaces(self) -> None:
        """ragコマンド解析: crawl URL 複数トークンのパターン."""
        subcommand, url, pattern, raw = _parse_rag_command(
            "rag crawl https://example.com/docs /docs/.*/guide"
        )
        assert subcommand == "crawl"
        assert url == "https://example.com/docs"
        assert pattern == "/docs/.*/guide"

    def test_crawl_with_slack_url_format(self) -> None:
        """ragコマンド解析: SlackのURL形式 <https://...|label>."""
        subcommand, url, pattern, raw = _parse_rag_command(
            "rag crawl <https://example.com/docs|example.com>"
        )
        assert subcommand == "crawl"
        assert url == "https://example.com/docs"
        assert pattern == ""

    def test_crawl_with_slack_url_format_no_label(self) -> None:
        """ragコマンド解析: SlackのURL形式 <https://...> (ラベルなし)."""
        subcommand, url, pattern, raw = _parse_rag_command(
            "rag crawl <https://example.com/docs>"
        )
        assert subcommand == "crawl"
        assert url == "https://example.com/docs"
        assert pattern == ""

    def test_add_with_url(self) -> None:
        """ragコマンド解析: add URL."""
        subcommand, url, pattern, raw = _parse_rag_command(
            "rag add https://example.com/page"
        )
        assert subcommand == "add"
        assert url == "https://example.com/page"
        assert pattern == ""

    def test_status(self) -> None:
        """ragコマンド解析: status."""
        subcommand, url, pattern, raw = _parse_rag_command("rag status")
        assert subcommand == "status"
        assert url == ""
        assert pattern == ""
        assert raw == ""

    def test_delete_with_url(self) -> None:
        """ragコマンド解析: delete URL."""
        subcommand, url, pattern, raw = _parse_rag_command(
            "rag delete https://example.com/page"
        )
        assert subcommand == "delete"
        assert url == "https://example.com/page"
        assert pattern == ""

    def test_subcommand_case_insensitive(self) -> None:
        """ragコマンド解析: サブコマンドは小文字に正規化."""
        subcommand, url, pattern, raw = _parse_rag_command(
            "rag CRAWL https://example.com/docs"
        )
        assert subcommand == "crawl"

    def test_empty_command(self) -> None:
        """ragコマンド解析: 空コマンド."""
        subcommand, url, pattern, raw = _parse_rag_command("rag")
        assert subcommand == ""
        assert url == ""
        assert pattern == ""
        assert raw == ""

    def test_invalid_url_scheme(self) -> None:
        """ragコマンド解析: 無効なURLスキームはurlが空でraw_url_tokenに残る."""
        subcommand, url, pattern, raw = _parse_rag_command(
            "rag crawl ftp://example.com/docs"
        )
        assert subcommand == "crawl"
        assert url == ""  # http/https以外は空
        assert pattern == ""
        assert raw == "ftp://example.com/docs"  # 生のトークンは保持

    def test_http_url(self) -> None:
        """ragコマンド解析: http:// URLも受け付ける."""
        subcommand, url, pattern, raw = _parse_rag_command(
            "rag add http://example.com/page"
        )
        assert subcommand == "add"
        assert url == "http://example.com/page"
        assert pattern == ""


class TestHandleRagCrawl:
    """_handle_rag_crawl関数のテスト."""

    @pytest.mark.asyncio
    async def test_success(self) -> None:
        """クロール成功時のレスポンス."""
        mock_rag = MagicMock()
        mock_rag.ingest_from_index = AsyncMock(
            return_value={"pages_crawled": 5, "chunks_stored": 20, "errors": 0}
        )

        result = await _handle_rag_crawl(
            mock_rag, "https://example.com/docs", "/api/"
        )

        assert "クロール完了" in result
        assert "5" in result
        assert "20" in result
        mock_rag.ingest_from_index.assert_called_once_with(
            "https://example.com/docs", "/api/"
        )

    @pytest.mark.asyncio
    async def test_no_url(self) -> None:
        """URL未指定時のエラーメッセージ."""
        mock_rag = MagicMock()

        result = await _handle_rag_crawl(mock_rag, "", "")

        assert "エラー" in result
        assert "URLを指定" in result

    @pytest.mark.asyncio
    async def test_invalid_scheme(self) -> None:
        """無効なURLスキーム時のエラーメッセージ."""
        mock_rag = MagicMock()

        result = await _handle_rag_crawl(mock_rag, "", "", "ftp://example.com")

        assert "エラー" in result
        assert "無効なURLスキーム" in result
        assert "ftp://example.com" in result

    @pytest.mark.asyncio
    async def test_value_error(self) -> None:
        """ValueError発生時のエラーメッセージ."""
        mock_rag = MagicMock()
        mock_rag.ingest_from_index = AsyncMock(
            side_effect=ValueError("ドメインが許可されていません")
        )

        result = await _handle_rag_crawl(
            mock_rag, "https://example.com/docs", ""
        )

        assert "エラー" in result
        assert "ドメインが許可されていません" in result


class TestHandleRagAdd:
    """_handle_rag_add関数のテスト."""

    @pytest.mark.asyncio
    async def test_success(self) -> None:
        """ページ追加成功時のレスポンス."""
        mock_rag = MagicMock()
        mock_rag.ingest_page = AsyncMock(return_value=5)

        result = await _handle_rag_add(mock_rag, "https://example.com/page")

        assert "取り込みました" in result
        assert "5チャンク" in result
        mock_rag.ingest_page.assert_called_once_with("https://example.com/page")

    @pytest.mark.asyncio
    async def test_no_chunks(self) -> None:
        """チャンク0の場合のエラーメッセージ."""
        mock_rag = MagicMock()
        mock_rag.ingest_page = AsyncMock(return_value=0)

        result = await _handle_rag_add(mock_rag, "https://example.com/page")

        assert "エラー" in result
        assert "失敗" in result

    @pytest.mark.asyncio
    async def test_no_url(self) -> None:
        """URL未指定時のエラーメッセージ."""
        mock_rag = MagicMock()

        result = await _handle_rag_add(mock_rag, "")

        assert "エラー" in result
        assert "URLを指定" in result

    @pytest.mark.asyncio
    async def test_invalid_scheme(self) -> None:
        """無効なURLスキーム時のエラーメッセージ."""
        mock_rag = MagicMock()

        result = await _handle_rag_add(mock_rag, "", "ftp://example.com")

        assert "エラー" in result
        assert "無効なURLスキーム" in result

    @pytest.mark.asyncio
    async def test_value_error(self) -> None:
        """ValueError発生時のエラーメッセージ."""
        mock_rag = MagicMock()
        mock_rag.ingest_page = AsyncMock(
            side_effect=ValueError("ドメインが許可されていません")
        )

        result = await _handle_rag_add(mock_rag, "https://example.com/page")

        assert "エラー" in result
        assert "ドメインが許可されていません" in result


class TestHandleRagStatus:
    """_handle_rag_status関数のテスト."""

    @pytest.mark.asyncio
    async def test_success(self) -> None:
        """ステータス取得成功時のレスポンス."""
        mock_rag = MagicMock()
        mock_rag.get_stats = AsyncMock(
            return_value={"total_chunks": 100, "source_count": 10}
        )

        result = await _handle_rag_status(mock_rag)

        assert "統計" in result
        assert "100" in result
        assert "10" in result

    @pytest.mark.asyncio
    async def test_exception(self) -> None:
        """例外発生時のエラーメッセージ."""
        mock_rag = MagicMock()
        mock_rag.get_stats = AsyncMock(side_effect=Exception("DB error"))

        result = await _handle_rag_status(mock_rag)

        assert "エラー" in result


class TestHandleRagDelete:
    """_handle_rag_delete関数のテスト."""

    @pytest.mark.asyncio
    async def test_success(self) -> None:
        """削除成功時のレスポンス."""
        mock_rag = MagicMock()
        mock_rag.delete_source = AsyncMock(return_value=5)

        result = await _handle_rag_delete(mock_rag, "https://example.com/page")

        assert "削除しました" in result
        assert "5チャンク" in result
        mock_rag.delete_source.assert_called_once_with("https://example.com/page")

    @pytest.mark.asyncio
    async def test_not_found(self) -> None:
        """該当なしの場合のメッセージ."""
        mock_rag = MagicMock()
        mock_rag.delete_source = AsyncMock(return_value=0)

        result = await _handle_rag_delete(mock_rag, "https://example.com/page")

        assert "見つかりませんでした" in result

    @pytest.mark.asyncio
    async def test_no_url(self) -> None:
        """URL未指定時のエラーメッセージ."""
        mock_rag = MagicMock()

        result = await _handle_rag_delete(mock_rag, "")

        assert "エラー" in result
        assert "URLを指定" in result

    @pytest.mark.asyncio
    async def test_invalid_scheme(self) -> None:
        """無効なURLスキーム時のエラーメッセージ."""
        mock_rag = MagicMock()

        result = await _handle_rag_delete(mock_rag, "", "ftp://example.com")

        assert "エラー" in result
        assert "無効なURLスキーム" in result
