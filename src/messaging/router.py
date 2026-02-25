"""メッセージルーター — キーワードルーティング + サービス層呼び出し.

仕様: docs/specs/features/cli-adapter.md
handlers.py の _process_message ロジックを移植したクラス。
"""

from __future__ import annotations

import asyncio
import csv
import io
import logging
import re
import socket
from datetime import datetime
from typing import TYPE_CHECKING, Literal
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import httpx

from src.mcp_bridge.client_manager import MCPToolNotFoundError
from src.messaging.port import IncomingMessage, MessagingPort
from src.services.chat import ChatService
from src.services.topic_recommender import TopicRecommender
from src.services.user_profiler import UserProfiler

if TYPE_CHECKING:
    from slack_sdk.web.async_client import AsyncWebClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from src.mcp_bridge.client_manager import MCPClientManager
    from src.services.feed_collector import FeedCollector

logger = logging.getLogger(__name__)

_PROFILE_KEYWORDS = ("プロファイル", "プロフィール", "profile")
_TOPIC_KEYWORDS = ("おすすめ", "トピック", "何を学ぶ", "何学ぶ", "学習提案", "recommend")
_DELIVER_KEYWORDS = ("deliver",)
_FEED_KEYWORDS = ("feed",)
_RAG_KEYWORDS = ("rag",)
_STATUS_KEYWORDS = ("status", "info")


def _parse_feed_command(text: str) -> tuple[str, list[str], str]:
    """feedコマンドを解析する."""
    tokens = text.split()
    if len(tokens) < 2:
        return ("", [], "")

    subcommand = tokens[1].lower()
    urls: list[str] = []
    category_tokens: list[str] = []

    for token in tokens[2:]:
        cleaned = token.strip("<>")
        if "|" in cleaned:
            cleaned = cleaned.split("|")[0]

        if cleaned.startswith("http://") or cleaned.startswith("https://"):
            parsed_url = urlparse(cleaned)
            if parsed_url.netloc:
                urls.append(cleaned)
        elif cleaned.startswith("--"):
            pass
        else:
            category_tokens.append(token)

    category = " ".join(category_tokens) if category_tokens else "一般"
    return (subcommand, urls, category)


def _format_uptime(seconds: float) -> str:
    """稼働時間を「N時間M分」形式にフォーマットする."""
    total_minutes = int(seconds) // 60
    hours = total_minutes // 60
    minutes = total_minutes % 60
    if hours > 0:
        return f"{hours}時間{minutes}分"
    return f"{minutes}分"


def _build_status_message(
    timezone: str, env_name: str, bot_start_time: datetime | None = None
) -> str:
    """ボットステータスメッセージを構築する (F7)."""
    hostname = socket.gethostname()
    now = datetime.now(tz=ZoneInfo(timezone))

    lines = ["\U0001f916 ボットステータス", f"ホスト: {hostname}"]

    if env_name:
        lines.append(f"環境: {env_name}")

    if bot_start_time is not None:
        start_str = bot_start_time.strftime("%Y-%m-%d %H:%M:%S %Z")
        uptime = now - bot_start_time
        uptime_str = _format_uptime(uptime.total_seconds())
        lines.append(f"起動: {start_str}（稼働 {uptime_str}）")

    return "\n".join(lines)


def _parse_rag_command(text: str) -> tuple[str, str, str, str]:
    """ragコマンドを解析する."""
    tokens = text.split()
    if len(tokens) < 2:
        return ("", "", "", "")

    subcommand = tokens[1].lower()
    url = ""
    pattern = ""
    raw_url_token = ""

    if len(tokens) >= 3:
        url_token = tokens[2].strip("<>")
        if "|" in url_token:
            url_token = url_token.split("|")[0]
        raw_url_token = url_token
        if url_token.startswith("http://") or url_token.startswith("https://"):
            url = url_token

    if len(tokens) >= 4:
        pattern = " ".join(tokens[3:])

    return (subcommand, url, pattern, raw_url_token)


# --- Feed ハンドラ群 ---


async def _handle_feed_add(
    collector: FeedCollector, urls: list[str], category: str
) -> str:
    """フィード追加処理."""
    if not urls:
        return "エラー: URLを指定してください。\n例: `@bot feed add https://example.com/rss [カテゴリ]`"

    results: list[str] = []
    for url in urls:
        try:
            name = await collector.fetch_feed_title(url)
            feed = await collector.add_feed(url, name, category)
            results.append(f"✅ {feed.url} を追加しました（名前: {feed.name}、カテゴリ: {feed.category}）")
        except ValueError as e:
            results.append(f"❌ {url}: {e}")
        except Exception:
            logger.exception("Failed to add feed: %s", url)
            results.append(f"❌ {url}: 追加中にエラーが発生しました")

    return "\n".join(results)


async def _handle_feed_list(collector: FeedCollector) -> str:
    """フィード一覧表示処理."""
    enabled, disabled = await collector.list_feeds()

    if not enabled and not disabled:
        return "フィードが登録されていません"

    lines: list[str] = []
    if enabled:
        lines.append("*有効なフィード*")
        for feed in enabled:
            lines.append(f"• {feed.url} — {feed.name}")
    else:
        lines.append("有効なフィードはありません")

    if disabled:
        lines.append("\n*無効なフィード*")
        for feed in disabled:
            lines.append(f"• {feed.url} — {feed.name}")

    return "\n".join(lines)


async def _handle_feed_delete(collector: FeedCollector, urls: list[str]) -> str:
    """フィード削除処理."""
    if not urls:
        return "エラー: URLを指定してください。\n例: `@bot feed delete https://example.com/rss`"

    results: list[str] = []
    for url in urls:
        try:
            await collector.delete_feed(url)
            results.append(f"✅ {url} を削除しました")
        except ValueError as e:
            results.append(f"❌ {url}: {e}")
        except Exception:
            logger.exception("Failed to delete feed: %s", url)
            results.append(f"❌ {url}: 削除中にエラーが発生しました")

    return "\n".join(results)


async def _handle_feed_enable(collector: FeedCollector, urls: list[str]) -> str:
    """フィード有効化処理."""
    if not urls:
        return "エラー: URLを指定してください。\n例: `@bot feed enable https://example.com/rss`"

    results: list[str] = []
    for url in urls:
        try:
            await collector.enable_feed(url)
            results.append(f"✅ {url} を有効化しました")
        except ValueError as e:
            results.append(f"❌ {url}: {e}")
        except Exception:
            logger.exception("Failed to enable feed: %s", url)
            results.append(f"❌ {url}: 有効化中にエラーが発生しました")

    return "\n".join(results)


async def _handle_feed_disable(collector: FeedCollector, urls: list[str]) -> str:
    """フィード無効化処理."""
    if not urls:
        return "エラー: URLを指定してください。\n例: `@bot feed disable https://example.com/rss`"

    results: list[str] = []
    for url in urls:
        try:
            await collector.disable_feed(url)
            results.append(f"✅ {url} を無効化しました")
        except ValueError as e:
            results.append(f"❌ {url}: {e}")
        except Exception:
            logger.exception("Failed to disable feed: %s", url)
            results.append(f"❌ {url}: 無効化中にエラーが発生しました")

    return "\n".join(results)


async def _download_and_parse_csv(
    files: list[dict[str, object]] | None,
    bot_token: str,
) -> tuple[list[dict[str, str]], str | None]:
    """CSV添付ファイルを検証・ダウンロード・パースする."""
    if not files:
        return ([], (
            "エラー: CSVファイルを添付してください。\n"
            "使用方法: `@bot feed import` または `@bot feed replace` にCSVファイルを添付\n"
            "CSV形式: `url,name,category`"
        ))

    csv_file = None
    for f in files:
        mimetype = str(f.get("mimetype", ""))
        name = str(f.get("name", ""))
        if mimetype == "text/csv" or name.endswith(".csv"):
            csv_file = f
            break

    if not csv_file:
        return ([], (
            "エラー: CSVファイルが見つかりません。\n"
            "CSV形式のファイル（.csv）を添付してください。"
        ))

    max_file_size = 1 * 1024 * 1024
    file_size = csv_file.get("size", 0)
    if isinstance(file_size, int) and file_size > max_file_size:
        return ([], f"エラー: ファイルサイズが大きすぎます（最大1MB、実際: {file_size // 1024}KB）")

    url_private = csv_file.get("url_private")
    if not url_private or not isinstance(url_private, str):
        return ([], "エラー: ファイルのダウンロードURLが取得できませんでした。")

    download_url = csv_file.get("url_private_download") or url_private
    if not isinstance(download_url, str):
        download_url = url_private

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                download_url,
                headers={"Authorization": f"Bearer {bot_token}"},
                follow_redirects=False,
            )
            if response.status_code == 302:
                logger.error("File download redirected - auth may have failed")
                return ([], "エラー: ファイルのダウンロードに失敗しました（認証エラー）。Bot権限を確認してください。")
            response.raise_for_status()
            content = response.text
    except httpx.HTTPError as e:
        logger.exception("Failed to download CSV file")
        return ([], f"エラー: ファイルのダウンロードに失敗しました: {e}")

    try:
        reader = csv.DictReader(io.StringIO(content))
        fieldnames = reader.fieldnames or []
        if "url" not in fieldnames or "name" not in fieldnames:
            return ([], (
                "エラー: CSVヘッダーが不正です。\n"
                "`url,name,category` の形式で記述してください。\n"
                f"検出されたヘッダー: {', '.join(fieldnames)}"
            ))

        rows = list(reader)
    except csv.Error as e:
        return ([], f"エラー: CSVのパースに失敗しました: {e}")

    if not rows:
        return ([], "エラー: CSVにデータがありません。")

    return (rows, None)


async def _import_feeds_from_rows(
    collector: FeedCollector,
    rows: list[dict[str, str]],
) -> tuple[int, list[str]]:
    """CSVの行リストからフィードを登録する."""
    success_count = 0
    errors: list[str] = []

    for line_number, row in enumerate(rows, start=2):
        url = (row.get("url") or "").strip()
        name = (row.get("name") or "").strip()
        category = (row.get("category") or "").strip() or "一般"

        if not url or not name:
            errors.append(f"行{line_number}: url または name が空です")
            continue

        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            errors.append(f"行{line_number}: 無効なURL形式です（{url}）")
            continue

        try:
            await collector.add_feed(url, name, category)
            success_count += 1
        except ValueError as e:
            errors.append(f"行{line_number}: {e}")
        except Exception:
            logger.exception("Failed to add feed: %s", url)
            errors.append(f"行{line_number}: 追加中にエラーが発生しました")

    return (success_count, errors)


def _format_error_details(errors: list[str]) -> list[str]:
    """エラー詳細をフォーマットする."""
    lines: list[str] = []
    if errors:
        lines.append("\n*エラー詳細:*")
        for error in errors[:10]:
            lines.append(f"  • {error}")
        if len(errors) > 10:
            lines.append(f"  ...他 {len(errors) - 10}件")
    return lines


async def _handle_feed_import(
    collector: FeedCollector,
    files: list[dict[str, object]] | None,
    bot_token: str,
) -> str:
    """CSVファイルからフィードを一括インポートする."""
    rows, error = await _download_and_parse_csv(files, bot_token)
    if error is not None:
        return error

    success_count, errors = await _import_feeds_from_rows(collector, rows)

    result_lines = [
        "*フィードインポート完了*",
        f"✅ 成功: {success_count}件",
        f"❌ 失敗: {len(errors)}件",
    ]
    result_lines.extend(_format_error_details(errors))

    return "\n".join(result_lines)


async def _handle_feed_replace(
    collector: FeedCollector,
    files: list[dict[str, object]] | None,
    bot_token: str,
) -> str:
    """CSVファイルで全フィードを置換する（全削除→再登録）."""
    rows, error = await _download_and_parse_csv(files, bot_token)
    if error is not None:
        return error

    try:
        deleted_count = await collector.delete_all_feeds()
    except Exception:
        logger.exception("Failed to delete all feeds in replace")
        return (
            "*フィード置換エラー*\n"
            "🗑️ 既存フィードの削除中に予期せぬエラーが発生しました。\n"
            "❌ フィードの置換を完了できませんでした。"
        )

    try:
        success_count, errors = await _import_feeds_from_rows(collector, rows)
    except Exception:
        logger.exception("Failed to import feeds after delete_all in replace")
        return (
            "*フィード置換エラー*\n"
            f"🗑️ 削除: {deleted_count}件（既存フィード）\n"
            "❌ インポート中に予期せぬエラーが発生しました。"
        )

    result_lines = [
        "*フィード置換完了*",
        f"🗑️ 削除: {deleted_count}件（既存フィード）",
        f"✅ 登録成功: {success_count}件",
        f"❌ 登録失敗: {len(errors)}件",
    ]
    result_lines.extend(_format_error_details(errors))

    return "\n".join(result_lines)


async def _handle_feed_export_via_port(
    collector: FeedCollector,
    messaging: MessagingPort,
    thread_id: str,
    channel: str,
) -> str:
    """全フィードをCSV形式でエクスポートする（MessagingPort経由）."""
    feeds = await collector.get_all_feeds()

    if not feeds:
        return "エクスポートするフィードがありません。"

    def _sanitize_csv_field(value: str) -> str:
        if value and value[0] in ("=", "+", "-", "@"):
            return f"'{value}"
        return value

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["url", "name", "category"])
    for feed in feeds:
        writer.writerow([
            feed.url,
            _sanitize_csv_field(feed.name),
            _sanitize_csv_field(feed.category),
        ])
    csv_content = output.getvalue()

    try:
        await messaging.upload_file(
            content=csv_content,
            filename="feeds.csv",
            thread_id=thread_id,
            channel=channel,
            comment=f"フィード一覧をエクスポートしました（{len(feeds)}件）",
        )
    except Exception as e:
        error_msg = str(e)
        if "missing_scope" in error_msg or "not_allowed_token_type" in error_msg:
            logger.error("File upload failed due to missing scope: %s", e)
            return (
                "エラー: ファイルのアップロードに失敗しました。\n"
                "Slack Appに `files:write` スコープの追加が必要です。"
            )
        logger.exception("Failed to upload CSV file")
        return f"エラー: ファイルのアップロードに失敗しました: {e}"

    return ""


async def _safe_extract_profile(
    profiler: UserProfiler, user_id: str, message: str
) -> None:
    """プロファイル抽出を安全に実行する（例外をログに記録）."""
    try:
        await profiler.extract_profile(user_id, message)
    except Exception:
        logger.exception("Failed to extract user profile for %s", user_id)


class MessageRouter:
    """キーワードルーティング + サービス層呼び出し.

    仕様: docs/specs/features/cli-adapter.md
    """

    def __init__(
        self,
        messaging: MessagingPort,
        chat_service: ChatService,
        user_profiler: UserProfiler | None = None,
        topic_recommender: TopicRecommender | None = None,
        collector: FeedCollector | None = None,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        channel_id: str | None = None,
        max_articles_per_feed: int = 10,
        feed_card_layout: Literal["vertical", "horizontal"] = "horizontal",
        bot_token: str | None = None,
        timezone: str = "Asia/Tokyo",
        env_name: str = "",
        mcp_manager: MCPClientManager | None = None,
        bot_start_time: datetime | None = None,
        slack_client: AsyncWebClient | None = None,
    ) -> None:
        self._messaging = messaging
        self._chat_service = chat_service
        self._user_profiler = user_profiler
        self._topic_recommender = topic_recommender
        self._collector = collector
        self._session_factory = session_factory
        self._channel_id = channel_id
        self._max_articles_per_feed = max_articles_per_feed
        self._feed_card_layout = feed_card_layout
        self._bot_token = bot_token
        self._timezone = timezone
        self._env_name = env_name
        self._mcp_manager = mcp_manager
        self._bot_start_time = bot_start_time
        self._slack_client = slack_client

    async def process_message(self, msg: IncomingMessage) -> None:
        """受信メッセージをキーワードルーティングし、適切なサービスに委譲する."""
        cleaned_text = msg.text
        user_id = msg.user_id
        thread_id = msg.thread_id
        channel = msg.channel

        # ステータスコマンド (F7)
        if cleaned_text.lower().strip() in _STATUS_KEYWORDS:
            response_text = _build_status_message(
                self._timezone, self._env_name, self._bot_start_time
            )
            await self._messaging.send_message(response_text, thread_id, channel)
            return

        # プロファイル確認キーワード (F3-AC4, F6-AC4)
        if self._user_profiler is not None and any(
            kw in cleaned_text.lower() for kw in _PROFILE_KEYWORDS
        ):
            profile_text = await self._user_profiler.get_profile(user_id)
            if profile_text:
                await self._messaging.send_message(profile_text, thread_id, channel)
            else:
                await self._messaging.send_message(
                    "まだプロファイル情報がありません。会話を続けると自動的に記録されます！",
                    thread_id, channel,
                )
            return

        # feedコマンド (F2-AC7, F6-AC4)
        lower_text = cleaned_text.lower().lstrip()
        if self._collector is not None and any(
            re.match(rf"^{re.escape(kw)}\b", lower_text) for kw in _FEED_KEYWORDS
        ):
            await self._handle_feed_command(msg, cleaned_text, lower_text)
            return

        # ragコマンド (F9)
        if self._mcp_manager is not None and any(
            re.match(rf"^{re.escape(kw)}\b", lower_text) for kw in _RAG_KEYWORDS
        ):
            await self._handle_rag_command(msg, cleaned_text)
            return

        # 配信テストキーワード (F2)
        if (
            self._collector is not None
            and self._session_factory is not None
            and self._channel_id is not None
            and any(kw in cleaned_text.lower() for kw in _DELIVER_KEYWORDS)
        ):
            await self._handle_deliver(msg)
            return

        # トピック提案キーワード (F4, F6-AC4)
        if self._topic_recommender is not None and any(
            kw in cleaned_text.lower() for kw in _TOPIC_KEYWORDS
        ):
            try:
                recommendation = await self._topic_recommender.recommend(user_id)
                await self._messaging.send_message(recommendation, thread_id, channel)
            except Exception:
                logger.exception("Failed to generate topic recommendation")
                await self._messaging.send_message(
                    "申し訳ありません、トピック提案の生成中にエラーが発生しました。",
                    thread_id, channel,
                )
            return

        # デフォルト: ChatService で応答
        try:
            response = await self._chat_service.respond(
                user_id=user_id,
                text=cleaned_text,
                thread_ts=thread_id,
                channel=channel,
                is_in_thread=msg.is_in_thread,
                current_ts=msg.message_id,
            )
            await self._messaging.send_message(response, thread_id, channel)

            if self._user_profiler is not None:
                asyncio.create_task(
                    _safe_extract_profile(self._user_profiler, user_id, cleaned_text)
                )
        except Exception:
            logger.exception("Failed to generate response")
            await self._messaging.send_message(
                "申し訳ありません、応答の生成中にエラーが発生しました。しばらくしてからもう一度お試しください。",
                thread_id, channel,
            )

    async def _handle_feed_command(
        self, msg: IncomingMessage, cleaned_text: str, lower_text: str
    ) -> None:
        """feedコマンドのルーティング."""
        assert self._collector is not None
        thread_id = msg.thread_id
        channel = msg.channel

        subcommand, urls, category = _parse_feed_command(cleaned_text)

        if subcommand == "add":
            response_text = await _handle_feed_add(self._collector, urls, category)
        elif subcommand == "list":
            response_text = await _handle_feed_list(self._collector)
        elif subcommand == "delete":
            response_text = await _handle_feed_delete(self._collector, urls)
        elif subcommand == "enable":
            response_text = await _handle_feed_enable(self._collector, urls)
        elif subcommand == "disable":
            response_text = await _handle_feed_disable(self._collector, urls)
        elif subcommand == "import":
            if not self._bot_token:
                response_text = "エラー: Bot Tokenが設定されていません。"
            else:
                response_text = await _handle_feed_import(
                    self._collector, msg.files, self._bot_token
                )
        elif subcommand == "replace":
            if not self._bot_token:
                response_text = "エラー: Bot Tokenが設定されていません。"
            else:
                response_text = await _handle_feed_replace(
                    self._collector, msg.files, self._bot_token
                )
        elif subcommand == "export":
            response_text = await _handle_feed_export_via_port(
                self._collector, self._messaging, thread_id, channel
            )
            if response_text:
                await self._messaging.send_message(response_text, thread_id, channel)
            return
        elif subcommand == "collect":
            await self._handle_feed_collect(msg, cleaned_text)
            return
        elif subcommand == "test":
            await self._handle_feed_test(msg)
            return
        else:
            response_text = (
                "使用方法:\n"
                "• `@bot feed add <URL> [カテゴリ]` — フィード追加\n"
                "• `@bot feed list` — フィード一覧\n"
                "• `@bot feed delete <URL>` — フィード削除\n"
                "• `@bot feed enable <URL>` — フィード有効化\n"
                "• `@bot feed disable <URL>` — フィード無効化\n"
                "• `@bot feed import` + CSV添付 — フィード一括インポート\n"
                "• `@bot feed replace` + CSV添付 — フィード一括置換\n"
                "• `@bot feed export` — フィード一覧をCSVエクスポート\n"
                "• `@bot feed collect --skip-summary` — 要約なし一括収集\n"
                "• `@bot feed test` — テスト配信（上位3フィード・各5件）\n"
                "※ URL・カテゴリは複数指定可能（スペース区切り）"
            )

        await self._messaging.send_message(response_text, thread_id, channel)

    async def _handle_feed_collect(
        self, msg: IncomingMessage, cleaned_text: str
    ) -> None:
        """feed collect コマンド処理."""
        thread_id = msg.thread_id
        channel = msg.channel

        if "--skip-summary" in cleaned_text.lower():
            if (
                self._collector is not None
                and self._session_factory is not None
                and self._channel_id is not None
                and self._slack_client is not None
            ):
                from src.scheduler.jobs import daily_collect_and_deliver

                try:
                    await self._messaging.send_message(
                        "要約スキップ収集を開始します...", thread_id, channel
                    )
                    feed_count, article_count = await daily_collect_and_deliver(
                        self._collector, self._session_factory,
                        self._slack_client, self._channel_id,
                        max_articles_per_feed=self._max_articles_per_feed,
                        layout=self._feed_card_layout,
                        skip_summary=True,
                    )
                    await self._messaging.send_message(
                        f"要約スキップ収集が完了しました\n収集フィード数: {feed_count}\n収集記事数: {article_count}",
                        thread_id, channel,
                    )
                except Exception:
                    logger.exception("Failed to collect feeds with skip-summary")
                    await self._messaging.send_message(
                        "要約スキップ収集中にエラーが発生しました。",
                        thread_id, channel,
                    )
            else:
                await self._messaging.send_message(
                    "エラー: 配信設定が不足しています。", thread_id, channel
                )
        else:
            response_text = (
                "使用方法:\n"
                "• `@bot feed collect --skip-summary` — 要約なし一括収集"
            )
            await self._messaging.send_message(response_text, thread_id, channel)

    async def _handle_feed_test(self, msg: IncomingMessage) -> None:
        """feed test コマンド処理."""
        thread_id = msg.thread_id
        channel = msg.channel

        if (
            self._session_factory is not None
            and self._channel_id is not None
            and self._slack_client is not None
        ):
            from src.scheduler.jobs import feed_test_deliver

            try:
                await self._messaging.send_message(
                    "テスト配信を開始します...", thread_id, channel
                )
                await feed_test_deliver(
                    session_factory=self._session_factory,
                    slack_client=self._slack_client,
                    channel_id=self._channel_id,
                    layout=self._feed_card_layout,
                )
                await self._messaging.send_message(
                    "テスト配信が完了しました", thread_id, channel
                )
            except Exception:
                logger.exception("Failed to run feed test delivery")
                await self._messaging.send_message(
                    "テスト配信中にエラーが発生しました。",
                    thread_id, channel,
                )
        else:
            await self._messaging.send_message(
                "エラー: 配信設定が不足しています（Slack接続が必要です）。",
                thread_id, channel,
            )

    async def _handle_deliver(self, msg: IncomingMessage) -> None:
        """deliver コマンド処理."""
        assert self._collector is not None
        assert self._session_factory is not None
        assert self._channel_id is not None
        thread_id = msg.thread_id
        channel = msg.channel

        if self._slack_client is None:
            await self._messaging.send_message(
                "エラー: deliver コマンドは Slack 接続時のみ使用できます。",
                thread_id, channel,
            )
            return

        from src.scheduler.jobs import daily_collect_and_deliver

        try:
            await self._messaging.send_message(
                "配信を開始します...", thread_id, channel
            )
            await daily_collect_and_deliver(
                self._collector, self._session_factory,
                self._slack_client, self._channel_id,
                max_articles_per_feed=self._max_articles_per_feed,
                layout=self._feed_card_layout,
            )
            await self._messaging.send_message(
                "配信が完了しました", thread_id, channel
            )
        except Exception:
            logger.exception("Failed to run manual delivery")
            await self._messaging.send_message(
                "配信中にエラーが発生しました。", thread_id, channel
            )

    async def _handle_rag_command(
        self, msg: IncomingMessage, cleaned_text: str
    ) -> None:
        """ragコマンドのルーティング（MCP経由）."""
        assert self._mcp_manager is not None
        thread_id = msg.thread_id
        channel = msg.channel

        subcommand, url, pattern, raw_url_token = _parse_rag_command(cleaned_text)

        if subcommand == "crawl":
            await self._handle_rag_crawl_mcp(
                url, pattern, raw_url_token, thread_id, channel,
            )
            return
        elif subcommand == "add":
            response_text = await self._call_rag_url_tool(
                "rag_add", url, raw_url_token,
                usage_hint="例: `@bot rag add https://example.com/page`",
            )
        elif subcommand == "status":
            try:
                response_text = await self._mcp_manager.call_tool("rag_stats", {})
            except MCPToolNotFoundError:
                response_text = "エラー: RAG統計ツールが利用できません。"
            except Exception:
                logger.exception("Failed to call rag_stats tool")
                response_text = "エラー: 統計情報の取得中にエラーが発生しました。"
        elif subcommand == "delete":
            response_text = await self._call_rag_url_tool(
                "rag_delete", url, raw_url_token,
                usage_hint="例: `@bot rag delete https://example.com/page`",
            )
        else:
            response_text = (
                "使用方法:\n"
                "• `@bot rag crawl <URL> [パターン]` — リンク集ページからクロール＆取り込み\n"
                "• `@bot rag add <URL>` — 単一ページ取り込み\n"
                "• `@bot rag status` — ナレッジベース統計表示\n"
                "• `@bot rag delete <URL>` — ソースURL指定で削除"
            )

        if response_text:
            await self._messaging.send_message(response_text, thread_id, channel)

    async def _handle_rag_crawl_mcp(
        self,
        url: str,
        pattern: str,
        raw_url_token: str,
        thread_id: str,
        channel: str,
    ) -> None:
        """RAGクロール処理（MCP経由）."""
        assert self._mcp_manager is not None
        if not url:
            if raw_url_token:
                error = f"エラー: 無効なURLスキームです: {raw_url_token}\nhttp:// または https:// で始まるURLを指定してください。"
            else:
                error = "エラー: URLを指定してください。\n例: `@bot rag crawl https://example.com/docs [パターン]`"
            await self._messaging.send_message(error, thread_id, channel)
            return

        # 開始メッセージ送信
        try:
            await self._messaging.send_message(
                "クロールを開始しました... (リンク収集中)",
                thread_id, channel,
            )
        except Exception:
            logger.debug("Failed to post start message", exc_info=True)

        # MCP ツール呼び出し
        try:
            result = await self._mcp_manager.call_tool(
                "rag_crawl", {"url": url, "pattern": pattern},
            )
            response_text = result if result.startswith("エラー:") else f"└─ {result}"
        except MCPToolNotFoundError:
            response_text = "エラー: RAGクロールツールが利用できません。"
        except Exception:
            logger.exception("Failed to call rag_crawl tool")
            response_text = "エラー: クロール中にエラーが発生しました。"

        await self._messaging.send_message(response_text, thread_id, channel)

    async def _call_rag_url_tool(
        self,
        tool_name: str,
        url: str,
        raw_url_token: str,
        usage_hint: str,
    ) -> str:
        """URL必須のRAGツールを呼び出す共通ヘルパー."""
        assert self._mcp_manager is not None
        if not url:
            if raw_url_token:
                return f"エラー: 無効なURLスキームです: {raw_url_token}\nhttp:// または https:// で始まるURLを指定してください。"
            return f"エラー: URLを指定してください。\n{usage_hint}"

        try:
            return await self._mcp_manager.call_tool(tool_name, {"url": url})
        except MCPToolNotFoundError:
            return f"エラー: ツール '{tool_name}' が利用できません。"
        except Exception:
            logger.exception("Failed to call %s tool", tool_name)
            return f"エラー: ツール '{tool_name}' の実行中にエラーが発生しました。"
