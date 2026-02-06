"""APScheduler 毎朝の収集・配信ジョブ
仕様: docs/specs/f2-feed-collection.md
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore[import-untyped]
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.db.models import Article, Feed
from src.services.feed_collector import FeedCollector

logger = logging.getLogger(__name__)

DEFAULT_TZ = ZoneInfo("Asia/Tokyo")


def _format_article_datetime(article: Article, tz: ZoneInfo = DEFAULT_TZ) -> str:
    """記事の更新日時をフォーマットする.

    published_at を優先し、None の場合は collected_at にフォールバック。
    """
    dt = article.published_at or article.collected_at
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    local_dt = dt.astimezone(tz)
    return local_dt.strftime("%Y-%m-%d %H:%M")


def _build_article_blocks(
    article: Article,
    layout: Literal["vertical", "horizontal"] = "horizontal",
    tz: ZoneInfo = DEFAULT_TZ,
) -> list[dict[str, Any]]:
    """1記事分のBlock Kitブロックを構築する（スレッド内1投稿分）."""
    if layout not in ("vertical", "horizontal"):
        msg = f"Invalid layout: {layout!r}. Must be 'vertical' or 'horizontal'."
        raise ValueError(msg)

    blocks: list[dict[str, Any]] = []

    # 更新日時の表示
    dt_str = _format_article_datetime(article, tz)
    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"───────────────────\n:clock1: {dt_str}\n───────────────────",
        },
    })

    summary = (article.summary or "").strip()
    if not summary:
        summary = "要約なし"

    if layout == "horizontal":
        title_part = f":newspaper: *<{article.url}|{article.title}>*\n\n"
        max_summary = 3000 - len(title_part) - 10
        if len(summary) > max_summary:
            summary = summary[:max_summary] + "..."
        section: dict[str, Any] = {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"{title_part}{summary}",
            },
        }
        if article.image_url:
            section["accessory"] = {
                "type": "image",
                "image_url": article.image_url,
                "alt_text": article.title,
            }
        blocks.append(section)
    else:
        # 縦長形式
        if len(summary) > 2900:
            summary = summary[:2900] + "..."
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f":newspaper: *<{article.url}|{article.title}>*",
            },
        })
        if article.image_url:
            blocks.append({
                "type": "image",
                "image_url": article.image_url,
                "alt_text": article.title,
            })
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": summary,
            },
        })

    return blocks


def _build_parent_message(feed_name: str, article_count: int) -> list[dict[str, Any]]:
    """フィードの親メッセージBlock Kitブロックを構築する."""
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f":mega: *{feed_name}* — {article_count}件の新着記事",
            },
        },
    ]


def format_daily_digest(
    articles: list[Article],
    feeds: dict[int, Feed],
    max_articles_per_feed: int = 10,
    layout: Literal["vertical", "horizontal"] = "horizontal",
) -> dict[int, tuple[list[dict[str, Any]], list[list[dict[str, Any]]]]]:
    """フィード別にBlock Kitブロックを生成する.

    Returns:
        feed_id をキーとし、(親メッセージblocks, [記事blocksリスト]) タプルを値とする辞書。
        記事blocksリストは1記事ごとのBlock Kitブロックリスト。
        記事がない場合は空辞書。
    """
    if not articles:
        return {}

    by_feed: dict[int, list[Article]] = {}
    for article in articles:
        by_feed.setdefault(article.feed_id, []).append(article)

    result: dict[int, tuple[list[dict[str, Any]], list[list[dict[str, Any]]]]] = {}
    for feed_id, feed_articles in by_feed.items():
        feed = feeds.get(feed_id)
        feed_name = feed.name if feed else "不明なフィード"

        display_articles = feed_articles[:max_articles_per_feed]
        parent_blocks = _build_parent_message(feed_name, len(display_articles))

        article_blocks_list: list[list[dict[str, Any]]] = []
        for article in display_articles:
            article_blocks_list.append(_build_article_blocks(article, layout=layout))

        result[feed_id] = (parent_blocks, article_blocks_list)

    return result


async def _post_article_to_thread(
    slack_client: object,
    channel_id: str,
    thread_ts: str,
    blocks: list[dict[str, Any]],
) -> None:
    """1記事分のブロックをスレッドに投稿する（画像エラー時リトライ付き）."""
    try:
        await slack_client.chat_postMessage(  # type: ignore[attr-defined]
            channel=channel_id,
            text="記事",
            blocks=blocks,
            thread_ts=thread_ts,
            unfurl_links=False,
            unfurl_media=False,
        )
    except Exception as exc:
        error_msg = str(exc)
        if "invalid_blocks" in error_msg or "downloading image" in error_msg:
            blocks_without_images = []
            for b in blocks:
                if b.get("type") == "image":
                    continue
                if "accessory" in b:
                    b = {k: v for k, v in b.items() if k != "accessory"}
                blocks_without_images.append(b)
            logger.warning(
                "Failed to post article with images, retrying without: %s",
                error_msg,
            )
            await slack_client.chat_postMessage(  # type: ignore[attr-defined]
                channel=channel_id,
                text="記事",
                blocks=blocks_without_images,
                thread_ts=thread_ts,
                unfurl_links=False,
                unfurl_media=False,
            )
        else:
            raise


async def daily_collect_and_deliver(
    collector: FeedCollector,
    session_factory: async_sessionmaker[AsyncSession],
    slack_client: object,
    channel_id: str,
    max_articles_per_feed: int = 10,
    layout: Literal["vertical", "horizontal"] = "horizontal",
) -> None:
    """毎朝の収集・配信ジョブ."""
    logger.info("Starting daily feed collection and delivery")

    try:
        await collector.collect_all()

        async with session_factory() as session:
            result = await session.execute(
                select(Article).where(Article.delivered == False)  # noqa: E712
            )
            undelivered_articles = list(result.scalars().all())

            feed_result = await session.execute(select(Feed))
            feeds = {f.id: f for f in feed_result.scalars().all()}

        if not undelivered_articles:
            logger.info("No new articles to deliver")
            return

        today = datetime.now(tz=DEFAULT_TZ).strftime("%Y-%m-%d")
        digest = format_daily_digest(
            undelivered_articles, feeds,
            max_articles_per_feed=max_articles_per_feed,
            layout=layout,
        )
        if not digest:
            return

        # ヘッダーメッセージ
        await slack_client.chat_postMessage(  # type: ignore[attr-defined]
            channel=channel_id,
            text=f":newspaper: 今日の学習ニュース ({today})",
            blocks=[
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f":newspaper: 今日の学習ニュース ({today})",
                    },
                },
            ],
        )

        # フィードごとに親メッセージ + スレッド内に1記事1投稿（逐次型）
        for feed_id, (parent_blocks, article_blocks_list) in digest.items():
            feed = feeds.get(feed_id)
            feed_name = feed.name if feed else "不明なフィード"
            parent_result = await slack_client.chat_postMessage(  # type: ignore[attr-defined]
                channel=channel_id,
                text=f"📰 {feed_name}",
                blocks=parent_blocks,
                unfurl_links=False,
                unfurl_media=False,
            )
            parent_ts = parent_result["ts"]

            # 1記事ずつスレッドに投稿（逐次型）
            for article_blocks in article_blocks_list:
                await _post_article_to_thread(
                    slack_client, channel_id, parent_ts, article_blocks,
                )

        # フッターメッセージ
        await slack_client.chat_postMessage(  # type: ignore[attr-defined]
            channel=channel_id,
            text=":bulb: 気になる記事があれば、スレッドで聞いてね！",
            blocks=[
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": ":bulb: 気になる記事があれば、スレッドで聞いてね！",
                    },
                },
            ],
        )

        # 配信完了後、配信済みフラグを更新
        async with session_factory() as session:
            await session.execute(
                update(Article)
                .where(Article.id.in_([a.id for a in undelivered_articles]))
                .values(delivered=True)
            )
            await session.commit()

        logger.info("Delivered %d articles to %s", len(undelivered_articles), channel_id)
    except Exception:
        logger.exception("Error in daily_collect_and_deliver job")


async def feed_test_deliver(
    session_factory: async_sessionmaker[AsyncSession],
    slack_client: object,
    channel_id: str,
    layout: Literal["vertical", "horizontal"] = "horizontal",
    max_feeds: int = 5,
    max_articles_per_feed: int = 10,
) -> None:
    """feed test 用配信（要約スキップ・配信済み含む・上限5フィード）.

    仕様: docs/specs/f2-feed-collection.md (AC15)
    """
    async with session_factory() as session:
        # 有効フィードをID昇順で最大 max_feeds 件取得
        feed_result = await session.execute(
            select(Feed)
            .where(Feed.enabled == True)  # noqa: E712
            .order_by(Feed.id.asc())
            .limit(max_feeds)
        )
        test_feeds = list(feed_result.scalars().all())

        if not test_feeds:
            logger.info("No enabled feeds for test delivery")
            return

        feeds = {f.id: f for f in test_feeds}
        feed_ids = [f.id for f in test_feeds]

        # 各フィードの全記事を取得（delivered 問わず）
        article_result = await session.execute(
            select(Article).where(Article.feed_id.in_(feed_ids))
        )
        all_articles = list(article_result.scalars().all())

    if not all_articles:
        logger.info("No articles found for test delivery")
        return

    digest = format_daily_digest(
        all_articles, feeds,
        max_articles_per_feed=max_articles_per_feed,
        layout=layout,
    )
    if not digest:
        return

    # テストヘッダー
    await slack_client.chat_postMessage(  # type: ignore[attr-defined]
        channel=channel_id,
        text=":test_tube: フィードテスト配信",
        blocks=[
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": ":test_tube: フィードテスト配信",
                },
            },
        ],
    )

    # フィードごとに親メッセージ + スレッド内に1記事1投稿（逐次型）
    for feed_id, (parent_blocks, article_blocks_list) in digest.items():
        feed = feeds.get(feed_id)
        feed_name = feed.name if feed else "不明なフィード"
        parent_result = await slack_client.chat_postMessage(  # type: ignore[attr-defined]
            channel=channel_id,
            text=f"📰 {feed_name}",
            blocks=parent_blocks,
            unfurl_links=False,
            unfurl_media=False,
        )
        parent_ts = parent_result["ts"]

        for article_blocks in article_blocks_list:
            await _post_article_to_thread(
                slack_client, channel_id, parent_ts, article_blocks,
            )

    # delivered フラグは更新しない（テストなので副作用なし）
    logger.info("Test delivery completed for %d feeds", len(test_feeds))


def setup_scheduler(
    collector: FeedCollector,
    session_factory: async_sessionmaker[AsyncSession],
    slack_client: object,
    channel_id: str,
    hour: int = 7,
    minute: int = 0,
    tz: str = "Asia/Tokyo",
    max_articles_per_feed: int = 10,
    layout: Literal["vertical", "horizontal"] = "horizontal",
) -> AsyncIOScheduler:
    """スケジューラを設定して返す."""
    scheduler = AsyncIOScheduler(timezone=tz)
    scheduler.add_job(
        daily_collect_and_deliver,
        "cron",
        hour=hour,
        minute=minute,
        kwargs={
            "collector": collector,
            "session_factory": session_factory,
            "slack_client": slack_client,
            "channel_id": channel_id,
            "max_articles_per_feed": max_articles_per_feed,
            "layout": layout,
        },
        id="daily_feed_job",
    )
    return scheduler
