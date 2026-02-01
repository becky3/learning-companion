"""スケジューラ・配信フォーマットのテスト (Issue #8)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.db.models import Article, Base, Feed
from src.scheduler.jobs import (
    daily_collect_and_deliver,
    format_daily_digest,
    setup_scheduler,
)


def _make_article(feed_id: int, title: str, url: str, summary: str) -> Article:
    a = Article(feed_id=feed_id, title=title, url=url, summary=summary)
    return a


def test_ac5_format_daily_digest_categorized() -> None:
    """AC5: 専用チャンネルにカテゴリ別フォーマットで記事要約を投稿する."""
    feeds = {
        1: Feed(id=1, url="https://a.com/rss", name="A", category="Python"),
        2: Feed(id=2, url="https://b.com/rss", name="B", category="機械学習"),
    }
    articles = [
        _make_article(1, "asyncioの新機能", "https://a.com/1", "asyncio要約"),
        _make_article(2, "transformer効率化", "https://b.com/1", "transformer要約"),
    ]

    result = format_daily_digest(articles, feeds)

    assert "今日の学習ニュース" in result
    assert "【Python】" in result
    assert "【機械学習】" in result
    assert "asyncioの新機能" in result
    assert "transformer効率化" in result
    assert ":bulb:" in result


def test_ac5_format_empty_articles() -> None:
    """AC5: 記事がない場合は空文字を返す."""
    assert format_daily_digest([], {}) == ""


def test_ac5_format_empty_summary_shows_fallback() -> None:
    """AC5: 要約が空の場合は「要約なし」と表示する."""
    feeds = {1: Feed(id=1, url="https://a.com/rss", name="A", category="Python")}
    articles = [_make_article(1, "Title", "https://a.com/1", "")]

    result = format_daily_digest(articles, feeds)
    assert "要約なし" in result


def test_ac4_scheduler_registers_cron_job() -> None:
    """AC4: 毎朝指定時刻にスケジューラが収集・配信ジョブを実行する."""
    collector = MagicMock()
    session_factory = MagicMock()
    slack_client = MagicMock()

    scheduler = setup_scheduler(
        collector=collector,
        session_factory=session_factory,
        slack_client=slack_client,
        channel_id="C123",
        hour=7,
        minute=30,
        timezone="Asia/Tokyo",
    )

    jobs = scheduler.get_jobs()
    assert len(jobs) == 1
    assert jobs[0].id == "daily_feed_job"
    trigger = jobs[0].trigger
    # cron トリガーのフィールドを名前で検索して検証
    hour_field = next(f for f in trigger.fields if getattr(f, "name", None) == "hour")
    minute_field = next(f for f in trigger.fields if getattr(f, "name", None) == "minute")
    assert str(hour_field) == "7"
    assert str(minute_field) == "30"


@pytest.fixture
async def db_factory():  # type: ignore[no-untyped-def]
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        feed = Feed(url="https://example.com/rss", name="Test", category="Python")
        session.add(feed)
        await session.commit()
        session.add(Article(
            feed_id=feed.id,
            title="Recent",
            url="https://example.com/1",
            summary="summary",
            collected_at=datetime.now(tz=timezone.utc),
        ))
        await session.commit()
    yield factory
    await engine.dispose()


async def test_ac4_daily_collect_and_deliver_posts_to_slack(db_factory) -> None:  # type: ignore[no-untyped-def]
    """AC4: daily_collect_and_deliver がSlackにメッセージを投稿する."""
    collector = AsyncMock()
    collector.collect_all.return_value = []
    slack_client = AsyncMock()

    await daily_collect_and_deliver(
        collector=collector,
        session_factory=db_factory,
        slack_client=slack_client,
        channel_id="C123",
    )

    collector.collect_all.assert_called_once()
    slack_client.chat_postMessage.assert_called_once()
    call_kwargs = slack_client.chat_postMessage.call_args.kwargs
    assert call_kwargs["channel"] == "C123"
    assert "今日の学習ニュース" in call_kwargs["text"]


async def test_ac4_daily_collect_and_deliver_handles_error(db_factory) -> None:  # type: ignore[no-untyped-def]
    """AC4: ジョブ内でエラーが発生してもクラッシュしない."""
    collector = AsyncMock()
    collector.collect_all.side_effect = RuntimeError("DB error")
    slack_client = AsyncMock()

    # エラーが発生してもExceptionは外に伝播しない
    await daily_collect_and_deliver(
        collector=collector,
        session_factory=db_factory,
        slack_client=slack_client,
        channel_id="C123",
    )
    slack_client.chat_postMessage.assert_not_called()
