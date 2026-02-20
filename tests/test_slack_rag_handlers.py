"""Slack ragコマンドハンドラのテスト（MCP経由）."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.mcp_bridge.client_manager import MCPToolNotFoundError
from src.messaging.port import IncomingMessage, MessagingPort
from src.messaging.router import MessageRouter, _parse_rag_command


# --- テストヘルパー ---


class _MockAdapter(MessagingPort):
    """テスト用モックアダプター."""

    def __init__(self) -> None:
        self.sent_messages: list[tuple[str, str, str]] = []

    async def send_message(self, text: str, thread_id: str, channel: str) -> None:
        self.sent_messages.append((text, thread_id, channel))

    async def upload_file(
        self, content: str, filename: str,
        thread_id: str, channel: str, comment: str,
    ) -> None:
        pass

    async def fetch_thread_history(
        self, channel: str, thread_id: str, current_message_id: str
    ) -> list[object] | None:
        return None

    def get_format_instruction(self) -> str:
        return ""

    def get_bot_user_id(self) -> str:
        return "mock-bot"


def _make_router(
    mcp_manager: MagicMock | None = None,
) -> tuple[_MockAdapter, MessageRouter]:
    adapter = _MockAdapter()
    chat_service = AsyncMock()
    chat_service.respond.return_value = "チャット応答"
    router = MessageRouter(
        messaging=adapter,
        chat_service=chat_service,
        mcp_manager=mcp_manager,
        timezone="Asia/Tokyo",
    )
    return adapter, router


def _make_msg(text: str) -> IncomingMessage:
    return IncomingMessage(
        user_id="U1",
        text=text,
        thread_id="t1",
        channel="C123",
        is_in_thread=False,
        message_id="m1",
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


class TestRagCrawlViaMcp:
    """rag crawl コマンドのテスト（MCP経由）."""

    @pytest.mark.asyncio
    async def test_ac42_rag_crawl_posts_start_message(self) -> None:
        """AC42: rag crawl実行時、即座に開始メッセージが投稿されること."""
        mcp = MagicMock()
        mcp.call_tool = AsyncMock(
            return_value="完了: 5ページ / 20チャンク / エラー: 0件"
        )
        adapter, router = _make_router(mcp_manager=mcp)

        await router.process_message(
            _make_msg("rag crawl https://example.com/docs")
        )

        # 開始メッセージ + 完了メッセージ = 2回
        assert len(adapter.sent_messages) == 2
        assert "クロールを開始しました" in adapter.sent_messages[0][0]

    @pytest.mark.asyncio
    async def test_ac44_rag_crawl_posts_completion_summary(self) -> None:
        """AC44: クロール完了時、結果サマリーが投稿されること."""
        mcp = MagicMock()
        mcp.call_tool = AsyncMock(
            return_value="完了: 15ページ / 128チャンク / エラー: 2件"
        )
        adapter, router = _make_router(mcp_manager=mcp)

        await router.process_message(
            _make_msg("rag crawl https://example.com/docs")
        )

        # 完了メッセージの内容を確認
        last_text = adapter.sent_messages[-1][0]
        assert "完了" in last_text
        assert "15ページ" in last_text
        assert "128チャンク" in last_text
        assert "エラー: 2件" in last_text

    @pytest.mark.asyncio
    async def test_ac45_all_messages_use_consistent_thread(self) -> None:
        """AC45: 全メッセージが同一のthread_idとchannelを使用すること."""
        mcp = MagicMock()
        mcp.call_tool = AsyncMock(
            return_value="完了: 10ページ / 50チャンク / エラー: 0件"
        )
        adapter, router = _make_router(mcp_manager=mcp)

        await router.process_message(
            _make_msg("rag crawl https://example.com/docs")
        )

        for text, thread_id, channel in adapter.sent_messages:
            assert thread_id == "t1"
            assert channel == "C123"

    @pytest.mark.asyncio
    async def test_ac23_crawl_with_pattern(self) -> None:
        """rag_crawl MCPツールにURL+パターンが渡されること."""
        mcp = MagicMock()
        mcp.call_tool = AsyncMock(
            return_value="完了: 5ページ / 20チャンク / エラー: 0件"
        )
        adapter, router = _make_router(mcp_manager=mcp)

        await router.process_message(
            _make_msg("rag crawl https://example.com/docs /api/")
        )

        mcp.call_tool.assert_called_once_with(
            "rag_crawl", {"url": "https://example.com/docs", "pattern": "/api/"},
        )

    @pytest.mark.asyncio
    async def test_ac23_crawl_no_url_error(self) -> None:
        """AC23: URL未指定時のエラーメッセージ."""
        mcp = MagicMock()
        adapter, router = _make_router(mcp_manager=mcp)

        await router.process_message(_make_msg("rag crawl"))

        assert len(adapter.sent_messages) == 1
        assert "エラー" in adapter.sent_messages[0][0]
        assert "URLを指定" in adapter.sent_messages[0][0]

    @pytest.mark.asyncio
    async def test_ac31_crawl_invalid_scheme_error(self) -> None:
        """AC31: 無効なURLスキーム時のエラーメッセージ."""
        mcp = MagicMock()
        adapter, router = _make_router(mcp_manager=mcp)

        await router.process_message(
            _make_msg("rag crawl ftp://example.com/docs")
        )

        assert len(adapter.sent_messages) == 1
        assert "無効なURLスキーム" in adapter.sent_messages[0][0]

    @pytest.mark.asyncio
    async def test_ac22_crawl_tool_not_found_error(self) -> None:
        """AC22: MCPToolNotFoundError時のエラーメッセージ."""
        mcp = MagicMock()
        mcp.call_tool = AsyncMock(side_effect=MCPToolNotFoundError("not found"))
        adapter, router = _make_router(mcp_manager=mcp)

        await router.process_message(
            _make_msg("rag crawl https://example.com/docs")
        )

        # 開始メッセージ + エラーメッセージ
        last_text = adapter.sent_messages[-1][0]
        assert "エラー" in last_text
        assert "利用できません" in last_text


class TestRagAddViaMcp:
    """rag add コマンドのテスト（MCP経由）."""

    @pytest.mark.asyncio
    async def test_ac24_add_page_success(self) -> None:
        """AC24: ページ追加成功時のレスポンス."""
        mcp = MagicMock()
        mcp.call_tool = AsyncMock(
            return_value="ページを取り込みました: https://example.com/page (5チャンク)"
        )
        adapter, router = _make_router(mcp_manager=mcp)

        await router.process_message(
            _make_msg("rag add https://example.com/page")
        )

        mcp.call_tool.assert_called_once_with(
            "rag_add", {"url": "https://example.com/page"},
        )
        assert "取り込みました" in adapter.sent_messages[0][0]

    @pytest.mark.asyncio
    async def test_ac24_add_no_url_error(self) -> None:
        """AC24: URL未指定時のエラーメッセージ."""
        mcp = MagicMock()
        adapter, router = _make_router(mcp_manager=mcp)

        await router.process_message(_make_msg("rag add"))

        assert "エラー" in adapter.sent_messages[0][0]
        assert "URLを指定" in adapter.sent_messages[0][0]

    @pytest.mark.asyncio
    async def test_ac31_add_invalid_scheme_error(self) -> None:
        """AC31: 無効なURLスキーム時のエラーメッセージ."""
        mcp = MagicMock()
        adapter, router = _make_router(mcp_manager=mcp)

        await router.process_message(
            _make_msg("rag add ftp://example.com/page")
        )

        assert "無効なURLスキーム" in adapter.sent_messages[0][0]

    @pytest.mark.asyncio
    async def test_ac22_add_tool_not_found_error(self) -> None:
        """AC22: MCPToolNotFoundError時のエラーメッセージ."""
        mcp = MagicMock()
        mcp.call_tool = AsyncMock(side_effect=MCPToolNotFoundError("not found"))
        adapter, router = _make_router(mcp_manager=mcp)

        await router.process_message(
            _make_msg("rag add https://example.com/page")
        )

        assert "エラー" in adapter.sent_messages[0][0]
        assert "利用できません" in adapter.sent_messages[0][0]


class TestRagStatusViaMcp:
    """rag status コマンドのテスト（MCP経由）."""

    @pytest.mark.asyncio
    async def test_ac25_status_success(self) -> None:
        """AC25: ステータス取得成功時のレスポンス."""
        mcp = MagicMock()
        mcp.call_tool = AsyncMock(
            return_value="ナレッジベース統計:\n  総チャンク数: 100\n  ソースURL数: 10"
        )
        adapter, router = _make_router(mcp_manager=mcp)

        await router.process_message(_make_msg("rag status"))

        mcp.call_tool.assert_called_once_with("rag_stats", {})
        assert "100" in adapter.sent_messages[0][0]
        assert "10" in adapter.sent_messages[0][0]

    @pytest.mark.asyncio
    async def test_ac25_status_exception_error(self) -> None:
        """AC25: 例外発生時のエラーメッセージ."""
        mcp = MagicMock()
        mcp.call_tool = AsyncMock(side_effect=Exception("connection error"))
        adapter, router = _make_router(mcp_manager=mcp)

        await router.process_message(_make_msg("rag status"))

        assert "エラー" in adapter.sent_messages[0][0]


class TestRagDeleteViaMcp:
    """rag delete コマンドのテスト（MCP経由）."""

    @pytest.mark.asyncio
    async def test_ac26_delete_success(self) -> None:
        """AC26: 削除成功時のレスポンス."""
        mcp = MagicMock()
        mcp.call_tool = AsyncMock(
            return_value="削除しました: https://example.com/page (5チャンク)"
        )
        adapter, router = _make_router(mcp_manager=mcp)

        await router.process_message(
            _make_msg("rag delete https://example.com/page")
        )

        mcp.call_tool.assert_called_once_with(
            "rag_delete", {"url": "https://example.com/page"},
        )
        assert "削除しました" in adapter.sent_messages[0][0]

    @pytest.mark.asyncio
    async def test_ac26_delete_no_url_error(self) -> None:
        """AC26: URL未指定時のエラーメッセージ."""
        mcp = MagicMock()
        adapter, router = _make_router(mcp_manager=mcp)

        await router.process_message(_make_msg("rag delete"))

        assert "エラー" in adapter.sent_messages[0][0]
        assert "URLを指定" in adapter.sent_messages[0][0]

    @pytest.mark.asyncio
    async def test_ac31_delete_invalid_scheme_error(self) -> None:
        """AC31: 無効なURLスキーム時のエラーメッセージ."""
        mcp = MagicMock()
        adapter, router = _make_router(mcp_manager=mcp)

        await router.process_message(
            _make_msg("rag delete ftp://example.com/page")
        )

        assert "無効なURLスキーム" in adapter.sent_messages[0][0]

    @pytest.mark.asyncio
    async def test_ac22_delete_tool_not_found_error(self) -> None:
        """AC22: MCPToolNotFoundError時のエラーメッセージ."""
        mcp = MagicMock()
        mcp.call_tool = AsyncMock(side_effect=MCPToolNotFoundError("not found"))
        adapter, router = _make_router(mcp_manager=mcp)

        await router.process_message(
            _make_msg("rag delete https://example.com/page")
        )

        assert "エラー" in adapter.sent_messages[0][0]
        assert "利用できません" in adapter.sent_messages[0][0]
