"""Slack mrkdwn形式対応のテスト (Issue #89).

仕様: docs/specs/features/slack-formatting.md
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.db.models import Base
from src.llm.base import LLMResponse
from src.services.chat import ChatService


@pytest.fixture
async def db_session_factory():  # type: ignore[no-untyped-def]
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def test_format_instruction_defined_in_config() -> None:
    """設定ファイルに format_instruction が定義されている."""
    from src.config.settings import load_assistant_config

    config = load_assistant_config()
    assert "format_instruction" in config
    assert config["format_instruction"].strip() != ""


async def test_format_instruction_prepended_to_system_prompt(db_session_factory) -> None:  # type: ignore[no-untyped-def]
    """format_instruction がシステムプロンプトの先頭に追加される."""
    llm = AsyncMock()
    llm.complete.return_value = LLMResponse(content="応答")

    personality = "テスト性格"
    slack_format = "【出力フォーマット】\nSlack mrkdwn形式で出力してください。"

    service = ChatService(
        llm=llm,
        session_factory=db_session_factory,
        system_prompt=personality,
        format_instruction=slack_format,
    )
    await service.respond(user_id="U1", text="hi", thread_ts="t1")

    messages = llm.complete.call_args[0][0]
    assert messages[0].role == "system"
    assert personality in messages[0].content
    assert slack_format in messages[0].content
    assert messages[0].content.startswith(slack_format)


async def test_empty_format_instruction_has_no_effect(db_session_factory) -> None:  # type: ignore[no-untyped-def]
    """format_instruction が空の場合、システムプロンプトに影響しない."""
    llm = AsyncMock()
    llm.complete.return_value = LLMResponse(content="応答")

    personality = "テスト性格"
    slack_format = ""

    service = ChatService(
        llm=llm,
        session_factory=db_session_factory,
        system_prompt=personality,
        format_instruction=slack_format,
    )
    await service.respond(user_id="U1", text="hi", thread_ts="t1")

    messages = llm.complete.call_args[0][0]
    assert messages[0].role == "system"
    assert messages[0].content == personality
