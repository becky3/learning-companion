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
    async def test_success_without_say(self) -> None:
        """クロール成功時のレスポンス（say関数なし、従来の動作）."""
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
        # progress_callbackが渡されることを確認（関数オブジェクトなのでany()でチェック）
        mock_rag.ingest_from_index.assert_called_once()
        call_args = mock_rag.ingest_from_index.call_args
        assert call_args[0] == ("https://example.com/docs", "/api/")
        assert "progress_callback" in call_args[1]

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


class TestHandleRagCrawlProgressFeedback:
    """_handle_rag_crawl 進捗フィードバック機能のテスト (AC42-AC45)."""

    @pytest.mark.asyncio
    async def test_ac42_rag_crawl_posts_start_message(self) -> None:
        """AC42: rag crawl実行時、即座に開始メッセージがスレッド内に投稿されること."""
        mock_rag = MagicMock()
        mock_rag.ingest_from_index = AsyncMock(
            return_value={"pages_crawled": 5, "chunks_stored": 20, "errors": 0}
        )
        mock_say = AsyncMock()

        await _handle_rag_crawl(
            mock_rag,
            "https://example.com/docs",
            "",
            say=mock_say,
            thread_ts="1234567890.123456",
        )

        # 開始メッセージが投稿されたことを確認
        calls = mock_say.call_args_list
        assert len(calls) >= 1
        first_call = calls[0]
        assert first_call.kwargs.get("thread_ts") == "1234567890.123456"
        assert "クロールを開始しました" in first_call.kwargs.get("text", "")
        assert "リンク収集中" in first_call.kwargs.get("text", "")

    @pytest.mark.asyncio
    async def test_ac43_rag_crawl_posts_progress_messages(self) -> None:
        """AC43: クロール中、progress_intervalページごとに進捗メッセージが投稿されること."""
        mock_rag = MagicMock()

        # ingest_from_indexがprogress_callbackを呼び出すようにする
        async def mock_ingest(url: str, pattern: str, progress_callback: object = None) -> dict[str, int]:
            if progress_callback:
                # 10ページ分の進捗を報告（interval=5なので5, 10で2回投稿される）
                for i in range(1, 11):
                    await progress_callback(i, 10)  # type: ignore[misc]
            return {"pages_crawled": 10, "chunks_stored": 50, "errors": 0}

        mock_rag.ingest_from_index = mock_ingest
        mock_say = AsyncMock()

        await _handle_rag_crawl(
            mock_rag,
            "https://example.com/docs",
            "",
            say=mock_say,
            thread_ts="1234567890.123456",
            progress_interval=5,  # 5ページごとに報告
        )

        # 全ての呼び出しを取得
        calls = mock_say.call_args_list
        # 開始メッセージ + 進捗メッセージ(5, 10) + 完了メッセージ = 4回
        assert len(calls) >= 3  # 最低でも開始 + 進捗 + 完了

        # 進捗メッセージの内容を確認（開始と完了以外）
        progress_calls = [
            c for c in calls
            if "ページ取得中" in c.kwargs.get("text", "")
        ]
        assert len(progress_calls) == 2  # 5ページ目と10ページ目
        for call in progress_calls:
            assert call.kwargs.get("thread_ts") == "1234567890.123456"

    @pytest.mark.asyncio
    async def test_ac44_rag_crawl_posts_completion_summary(self) -> None:
        """AC44: クロール完了時、結果サマリーがスレッド内に投稿されること."""
        mock_rag = MagicMock()
        mock_rag.ingest_from_index = AsyncMock(
            return_value={"pages_crawled": 15, "chunks_stored": 128, "errors": 2}
        )
        mock_say = AsyncMock()

        await _handle_rag_crawl(
            mock_rag,
            "https://example.com/docs",
            "",
            say=mock_say,
            thread_ts="1234567890.123456",
        )

        # 完了メッセージが投稿されたことを確認
        calls = mock_say.call_args_list
        # 最後の呼び出しが完了メッセージ
        last_call = calls[-1]
        assert last_call.kwargs.get("thread_ts") == "1234567890.123456"
        completion_text = last_call.kwargs.get("text", "")
        assert "完了" in completion_text
        assert "15ページ" in completion_text
        assert "128チャンク" in completion_text
        assert "エラー: 2件" in completion_text

    @pytest.mark.asyncio
    async def test_ac45_progress_messages_in_thread_only(self) -> None:
        """AC45: 進捗メッセージはスレッド内のみに投稿され、チャンネルへの通知は発生しないこと."""
        mock_rag = MagicMock()

        async def mock_ingest(url: str, pattern: str, progress_callback: object = None) -> dict[str, int]:
            if progress_callback:
                await progress_callback(5, 10)  # type: ignore[misc]
            return {"pages_crawled": 10, "chunks_stored": 50, "errors": 0}

        mock_rag.ingest_from_index = mock_ingest
        mock_say = AsyncMock()

        await _handle_rag_crawl(
            mock_rag,
            "https://example.com/docs",
            "",
            say=mock_say,
            thread_ts="1234567890.123456",
            progress_interval=5,
        )

        # 全ての呼び出しでthread_tsが指定されていることを確認
        for call in mock_say.call_args_list:
            # thread_tsが指定されている = スレッド内投稿
            assert call.kwargs.get("thread_ts") == "1234567890.123456", (
                f"thread_tsが指定されていない呼び出しがあります: {call}"
            )
            # reply_broadcast=True が指定されていないことを確認
            # (指定されるとチャンネルにも通知される)
            assert call.kwargs.get("reply_broadcast") is not True, (
                f"reply_broadcast=Trueが指定されています: {call}"
            )


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
