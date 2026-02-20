"""CLIエントリーポイント — REPL + ワンショットモード.

仕様: docs/specs/f11-cli-adapter.md

使用方法:
    # REPL モード
    uv run python -m src.cli

    # ワンショットモード
    uv run python -m src.cli --message "こんにちは"

    # user-id 指定
    uv run python -m src.cli --user-id alice
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from src.config.settings import get_settings, load_assistant_config
from src.db.session import get_session_factory, init_db
from src.embedding.factory import get_embedding_provider
from src.llm.factory import get_provider_for_service
from src.mcp_bridge.client_manager import MCPClientManager, MCPServerConfig
from src.messaging.cli_adapter import CliAdapter
from src.messaging.port import IncomingMessage
from src.messaging.router import MessageRouter
from src.rag.bm25_index import BM25Index
from src.rag.vector_store import VectorStore
from src.services.chat import ChatService
from src.services.feed_collector import FeedCollector
from src.services.ogp_extractor import OgpExtractor
from src.services.rag_knowledge import RAGKnowledgeService
from src.services.safe_browsing import create_safe_browsing_client
from src.services.summarizer import Summarizer
from src.services.topic_recommender import TopicRecommender
from src.services.user_profiler import UserProfiler
from src.services.web_crawler import WebCrawler

# ChromaDBテレメトリのエラーログを抑制
logging.getLogger("chromadb.telemetry.product.posthog").setLevel(logging.CRITICAL)

logger = logging.getLogger(__name__)


def _load_mcp_server_configs(config_path: str) -> list[MCPServerConfig]:
    """MCPサーバー設定ファイルを読み込む."""
    path = Path(config_path)
    if not path.exists():
        return []

    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError:
        return []

    configs: list[MCPServerConfig] = []
    for name, server_def in data.get("mcpServers", {}).items():
        configs.append(MCPServerConfig(
            name=name,
            transport=server_def.get("transport", "stdio"),
            command=server_def.get("command", ""),
            args=server_def.get("args", []),
            env=server_def.get("env", {}),
            url=server_def.get("url", ""),
            response_instruction=server_def.get("response_instruction", ""),
        ))
    return configs


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """コマンドライン引数をパースする."""
    parser = argparse.ArgumentParser(
        description="AI Assistant CLI — Slackなしで動作確認",
    )
    parser.add_argument(
        "--user-id",
        default="cli-user",
        help="ユーザーID（デフォルト: cli-user）",
    )
    parser.add_argument(
        "--message",
        default=None,
        help="ワンショットモード: 指定時は単発メッセージを処理して終了",
    )
    return parser.parse_args(argv)


async def _setup(
    user_id: str,
) -> tuple[MessageRouter, CliAdapter, MCPClientManager | None]:
    """サービス群を初期化してMessageRouterを返す."""
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)

    await init_db()

    assistant = load_assistant_config()
    system_prompt = assistant.get("personality", "")

    chat_llm = get_provider_for_service(settings, settings.chat_llm_provider)
    profiler_llm = get_provider_for_service(settings, settings.profiler_llm_provider)
    topic_llm = get_provider_for_service(settings, settings.topic_llm_provider)
    summarizer_llm = get_provider_for_service(settings, settings.summarizer_llm_provider)

    # MCP初期化（有効時のみ）
    mcp_manager: MCPClientManager | None = None
    if settings.mcp_enabled:
        mcp_manager = MCPClientManager()
        server_configs = _load_mcp_server_configs(settings.mcp_servers_config)
        await mcp_manager.initialize(server_configs)

    # RAG初期化（有効時のみ）
    rag_service: RAGKnowledgeService | None = None
    if settings.rag_enabled:
        embedding = get_embedding_provider(settings, settings.embedding_provider)
        vector_store = VectorStore(embedding, settings.chromadb_persist_dir)
        web_crawler = WebCrawler(
            max_pages=settings.rag_max_crawl_pages,
            crawl_delay=settings.rag_crawl_delay_sec,
            respect_robots_txt=settings.rag_respect_robots_txt,
            robots_txt_cache_ttl=settings.rag_robots_txt_cache_ttl,
        )
        safe_browsing_client = create_safe_browsing_client(settings)
        bm25_index: BM25Index | None = None
        if settings.rag_hybrid_search_enabled:
            bm25_index = BM25Index(
                k1=settings.rag_bm25_k1,
                b=settings.rag_bm25_b,
                persist_dir=settings.bm25_persist_dir,
            )
        rag_service = RAGKnowledgeService(
            vector_store,
            web_crawler,
            chunk_size=settings.rag_chunk_size,
            chunk_overlap=settings.rag_chunk_overlap,
            similarity_threshold=settings.rag_similarity_threshold,
            safe_browsing_client=safe_browsing_client,
            bm25_index=bm25_index,
            hybrid_search_enabled=settings.rag_hybrid_search_enabled,
            vector_weight=settings.rag_vector_weight,
            min_combined_score=settings.rag_min_combined_score,
            debug_log_enabled=settings.rag_debug_log_enabled,
        )

    cli_adapter = CliAdapter(user_id=user_id)

    session_factory = get_session_factory()
    chat_service = ChatService(
        llm=chat_llm,
        session_factory=session_factory,
        system_prompt=system_prompt,
        mcp_manager=mcp_manager,
        thread_history_fetcher=cli_adapter.fetch_thread_history,
        rag_service=rag_service,
        format_instruction=cli_adapter.get_format_instruction(),
    )

    user_profiler = UserProfiler(
        llm=profiler_llm,
        session_factory=session_factory,
    )

    topic_recommender = TopicRecommender(
        llm=topic_llm,
        session_factory=session_factory,
    )

    summarizer = Summarizer(llm=summarizer_llm)
    ogp_extractor = OgpExtractor()
    feed_collector = FeedCollector(
        session_factory=session_factory,
        summarizer=summarizer,
        ogp_extractor=ogp_extractor,
        summarize_timeout=settings.feed_summarize_timeout,
        collect_days=settings.feed_collect_days,
    )

    bot_start_time = datetime.now(tz=ZoneInfo(settings.timezone))

    router = MessageRouter(
        messaging=cli_adapter,
        chat_service=chat_service,
        user_profiler=user_profiler,
        topic_recommender=topic_recommender,
        collector=feed_collector,
        session_factory=session_factory,
        channel_id=settings.slack_news_channel_id or "cli",
        max_articles_per_feed=settings.feed_articles_per_feed,
        feed_card_layout=settings.feed_card_layout,
        timezone=settings.timezone,
        env_name=settings.env_name,
        rag_service=rag_service,
        rag_crawl_progress_interval=settings.rag_crawl_progress_interval,
        bot_start_time=bot_start_time,
    )

    return router, cli_adapter, mcp_manager


async def run_oneshot(router: MessageRouter, user_id: str, text: str) -> None:
    """ワンショットモードで1メッセージを処理する."""
    thread_id = f"cli-{uuid.uuid4()}"
    msg = IncomingMessage(
        user_id=user_id,
        text=text,
        thread_id=thread_id,
        channel="cli",
        is_in_thread=False,
        message_id=f"cli-msg-{uuid.uuid4()}",
    )
    await router.process_message(msg)


async def run_repl(router: MessageRouter, user_id: str) -> None:
    """REPLモードで対話セッションを実行する."""
    thread_id = f"cli-{uuid.uuid4()}"
    print("AI Assistant CLI (quit/exit で終了)")
    print(f"user-id: {user_id} | session: {thread_id}")
    print("-" * 40)

    while True:
        try:
            text = input("You> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nセッションを終了します。")
            break

        if not text:
            continue

        if text.lower() in ("quit", "exit"):
            print("セッションを終了します。")
            break

        msg = IncomingMessage(
            user_id=user_id,
            text=text,
            thread_id=thread_id,
            channel="cli",
            is_in_thread=False,
            message_id=f"cli-msg-{uuid.uuid4()}",
        )
        await router.process_message(msg)


async def async_main(argv: list[str] | None = None) -> None:
    """非同期メインエントリーポイント."""
    args = parse_args(argv)
    router, _adapter, mcp_manager = await _setup(args.user_id)

    try:
        if args.message is not None:
            await run_oneshot(router, args.user_id, args.message)
        else:
            await run_repl(router, args.user_id)
    finally:
        if mcp_manager:
            try:
                await mcp_manager.cleanup()
            except Exception:
                logger.warning("MCPクリーンアップ失敗", exc_info=True)


def main() -> None:
    """同期エントリーポイント."""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
