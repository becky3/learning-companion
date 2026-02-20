"""MessageRouter のテスト (Issue #496)."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

from src.llm.base import Message
from src.messaging.port import IncomingMessage, MessagingPort
from src.messaging.router import MessageRouter, _build_status_message, _format_uptime


# --- MockAdapter ---


class MockAdapter(MessagingPort):
    """テスト用モックアダプター."""

    def __init__(self) -> None:
        self.sent_messages: list[tuple[str, str, str]] = []
        self.uploaded_files: list[tuple[str, str, str, str, str]] = []

    async def send_message(self, text: str, thread_id: str, channel: str) -> None:
        self.sent_messages.append((text, thread_id, channel))

    async def upload_file(
        self, content: str, filename: str,
        thread_id: str, channel: str, comment: str,
    ) -> None:
        self.uploaded_files.append((content, filename, thread_id, channel, comment))

    async def fetch_thread_history(
        self, channel: str, thread_id: str, current_message_id: str
    ) -> list[Message] | None:
        return None

    def get_format_instruction(self) -> str:
        return ""

    def get_bot_user_id(self) -> str:
        return "mock-bot"


def _make_msg(text: str, user_id: str = "U1", channel: str = "cli") -> IncomingMessage:
    return IncomingMessage(
        user_id=user_id,
        text=text,
        thread_id="t1",
        channel=channel,
        is_in_thread=False,
        message_id="m1",
    )


def _make_router(
    adapter: MockAdapter | None = None,
    chat_service: AsyncMock | None = None,
    user_profiler: AsyncMock | None = None,
    topic_recommender: AsyncMock | None = None,
    collector: AsyncMock | None = None,
    session_factory: AsyncMock | None = None,
    mcp_manager: AsyncMock | None = None,
    bot_start_time: datetime | None = None,
) -> tuple[MockAdapter, MessageRouter]:
    if adapter is None:
        adapter = MockAdapter()
    if chat_service is None:
        chat_service = AsyncMock()
        chat_service.respond.return_value = "チャット応答"

    router = MessageRouter(
        messaging=adapter,
        chat_service=chat_service,
        user_profiler=user_profiler,
        topic_recommender=topic_recommender,
        collector=collector,
        session_factory=session_factory,
        channel_id="C_TEST",
        timezone="Asia/Tokyo",
        env_name="test",
        mcp_manager=mcp_manager,
        bot_start_time=bot_start_time,
    )
    return adapter, router


# --- ユーティリティ関数テスト ---


def test_format_uptime_hours_and_minutes() -> None:
    """稼働時間のフォーマット（時間+分）."""
    assert _format_uptime(7500.0) == "2時間5分"


def test_format_uptime_minutes_only() -> None:
    """稼働時間のフォーマット（分のみ）."""
    assert _format_uptime(300.0) == "5分"


def test_format_uptime_zero() -> None:
    """稼働時間のフォーマット（0分）."""
    assert _format_uptime(0.0) == "0分"


def test_build_status_with_env_name() -> None:
    """ステータスメッセージに環境名が含まれる."""
    start_time = datetime(2026, 2, 5, 10, 30, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    now = start_time + timedelta(hours=2, minutes=15)

    with patch("src.messaging.router.datetime") as mock_dt:
        mock_dt.now.return_value = now
        mock_dt.side_effect = datetime
        result = _build_status_message("Asia/Tokyo", "production", start_time)

    assert "ボットステータス" in result
    assert "環境: production" in result
    assert "稼働 2時間15分" in result


def test_build_status_without_env_name() -> None:
    """環境名が未設定の場合は省略される."""
    start_time = datetime(2026, 2, 5, 10, 0, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    now = start_time + timedelta(minutes=30)

    with patch("src.messaging.router.datetime") as mock_dt:
        mock_dt.now.return_value = now
        mock_dt.side_effect = datetime
        result = _build_status_message("Asia/Tokyo", "", start_time)

    assert "ボットステータス" in result
    assert "環境:" not in result


# --- ルーティングテスト ---


async def test_status_command() -> None:
    """status コマンドでステータスが返される."""
    start = datetime.now(tz=ZoneInfo("Asia/Tokyo"))
    adapter, router = _make_router(bot_start_time=start)

    await router.process_message(_make_msg("status"))

    assert len(adapter.sent_messages) == 1
    text = adapter.sent_messages[0][0]
    assert "ボットステータス" in text


async def test_info_command() -> None:
    """info コマンドでもステータスが返される."""
    start = datetime.now(tz=ZoneInfo("Asia/Tokyo"))
    adapter, router = _make_router(bot_start_time=start)

    await router.process_message(_make_msg("info"))

    assert len(adapter.sent_messages) == 1
    assert "ボットステータス" in adapter.sent_messages[0][0]


async def test_status_case_insensitive() -> None:
    """ステータスコマンドは大文字小文字不問."""
    start = datetime.now(tz=ZoneInfo("Asia/Tokyo"))
    for text in ["STATUS", "Status", "INFO", "Info"]:
        adapter, router = _make_router(bot_start_time=start)
        await router.process_message(_make_msg(text))
        assert "ボットステータス" in adapter.sent_messages[0][0], f"Failed for: {text}"


async def test_profile_command() -> None:
    """プロファイルコマンドでプロファイルが返される."""
    profiler = AsyncMock()
    profiler.get_profile.return_value = "テストプロファイル"
    adapter, router = _make_router(user_profiler=profiler)

    await router.process_message(_make_msg("プロファイル"))

    assert len(adapter.sent_messages) == 1
    assert "テストプロファイル" in adapter.sent_messages[0][0]


async def test_profile_command_no_profile() -> None:
    """プロファイルがない場合のメッセージ."""
    profiler = AsyncMock()
    profiler.get_profile.return_value = None
    adapter, router = _make_router(user_profiler=profiler)

    await router.process_message(_make_msg("profile"))

    assert len(adapter.sent_messages) == 1
    assert "まだプロファイル情報がありません" in adapter.sent_messages[0][0]


async def test_topic_command() -> None:
    """トピック提案コマンド."""
    recommender = AsyncMock()
    recommender.recommend.return_value = "おすすめトピック一覧"
    adapter, router = _make_router(topic_recommender=recommender)

    await router.process_message(_make_msg("おすすめ"))

    assert len(adapter.sent_messages) == 1
    assert "おすすめトピック一覧" in adapter.sent_messages[0][0]


async def test_feed_list_command() -> None:
    """feed list コマンド."""
    collector = AsyncMock()
    collector.list_feeds.return_value = ([], [])
    adapter, router = _make_router(collector=collector)

    await router.process_message(_make_msg("feed list"))

    assert len(adapter.sent_messages) == 1
    assert "フィードが登録されていません" in adapter.sent_messages[0][0]


async def test_feed_unknown_subcommand() -> None:
    """feed の不明なサブコマンドでヘルプが表示される."""
    collector = AsyncMock()
    adapter, router = _make_router(collector=collector)

    await router.process_message(_make_msg("feed"))

    assert len(adapter.sent_messages) == 1
    assert "使用方法" in adapter.sent_messages[0][0]


async def test_default_chat_response() -> None:
    """キーワードに一致しない場合は ChatService で応答."""
    chat_service = AsyncMock()
    chat_service.respond.return_value = "こんにちは！"
    adapter, router = _make_router(chat_service=chat_service)

    await router.process_message(_make_msg("やあ"))

    assert len(adapter.sent_messages) == 1
    assert "こんにちは！" in adapter.sent_messages[0][0]
    chat_service.respond.assert_called_once()


async def test_chat_error_handling() -> None:
    """ChatService のエラーが適切にハンドリングされる."""
    chat_service = AsyncMock()
    chat_service.respond.side_effect = RuntimeError("API error")
    adapter, router = _make_router(chat_service=chat_service)

    await router.process_message(_make_msg("test"))

    assert len(adapter.sent_messages) == 1
    assert "エラー" in adapter.sent_messages[0][0]


async def test_rag_unknown_subcommand() -> None:
    """rag の不明なサブコマンドでヘルプが表示される."""
    from unittest.mock import MagicMock

    mcp_manager = MagicMock()
    adapter, router = _make_router(mcp_manager=mcp_manager)

    await router.process_message(_make_msg("rag"))

    assert len(adapter.sent_messages) == 1
    assert "使用方法" in adapter.sent_messages[0][0]


async def test_rag_status_command() -> None:
    """rag status コマンド."""
    from unittest.mock import MagicMock

    mcp_manager = MagicMock()
    mcp_manager.call_tool = AsyncMock(
        return_value="ナレッジベース統計:\n  総チャンク数: 100\n  ソースURL数: 5"
    )
    adapter, router = _make_router(mcp_manager=mcp_manager)

    await router.process_message(_make_msg("rag status"))

    assert len(adapter.sent_messages) == 1
    assert "100" in adapter.sent_messages[0][0]
    assert "5" in adapter.sent_messages[0][0]


async def test_feed_export_command() -> None:
    """feed export コマンドでファイルアップロードが呼ばれる."""
    collector = AsyncMock()
    feed_mock = AsyncMock()
    feed_mock.url = "http://example.com/rss"
    feed_mock.name = "Example"
    feed_mock.category = "Tech"
    collector.get_all_feeds.return_value = [feed_mock]
    adapter, router = _make_router(collector=collector)

    await router.process_message(_make_msg("feed export"))

    assert len(adapter.uploaded_files) == 1
    assert "feeds.csv" in adapter.uploaded_files[0][1]


async def test_topic_error_handling() -> None:
    """トピック提案のエラーが適切にハンドリングされる."""
    recommender = AsyncMock()
    recommender.recommend.side_effect = RuntimeError("fail")
    adapter, router = _make_router(topic_recommender=recommender)

    await router.process_message(_make_msg("おすすめ"))

    assert len(adapter.sent_messages) == 1
    assert "エラー" in adapter.sent_messages[0][0]
