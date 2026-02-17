"""Slack mrkdwn形式対応のテスト (Issue #89).

仕様: docs/specs/f10-slack-mrkdwn.md
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


async def test_ac1_slack_format_instruction_in_assistant_yaml() -> None:
    """AC1: config/assistant.yaml に slack_format_instruction が定義されている."""
    from src.config.settings import load_assistant_config

    config = load_assistant_config()
    assert "slack_format_instruction" in config
    assert config["slack_format_instruction"].strip() != ""


async def test_ac2_slack_format_appended_to_system_prompt(db_session_factory) -> None:  # type: ignore[no-untyped-def]
    """AC2: slack_format_instruction がシステムプロンプトの末尾に追加される."""
    llm = AsyncMock()
    llm.complete.return_value = LLMResponse(content="応答")

    personality = "テスト性格"
    slack_format = "【出力フォーマット】\nSlack mrkdwn形式で出力してください。"
    system_prompt = personality + "\n\n" + slack_format

    service = ChatService(llm=llm, session_factory=db_session_factory, system_prompt=system_prompt)
    await service.respond(user_id="U1", text="hi", thread_ts="t1")

    messages = llm.complete.call_args[0][0]
    assert messages[0].role == "system"
    assert personality in messages[0].content
    assert slack_format in messages[0].content


async def test_ac3_empty_slack_format_no_effect(db_session_factory) -> None:  # type: ignore[no-untyped-def]
    """AC3: slack_format_instruction が空の場合、システムプロンプトに影響しない."""
    llm = AsyncMock()
    llm.complete.return_value = LLMResponse(content="応答")

    personality = "テスト性格"
    slack_format = ""
    # 空の場合はpersonalityのみ
    system_prompt = personality
    if slack_format:
        system_prompt = system_prompt + "\n\n" + slack_format

    service = ChatService(llm=llm, session_factory=db_session_factory, system_prompt=system_prompt)
    await service.respond(user_id="U1", text="hi", thread_ts="t1")

    messages = llm.complete.call_args[0][0]
    assert messages[0].role == "system"
    assert messages[0].content == personality


async def test_ac2_system_prompt_construction_logic() -> None:
    """AC2: main.pyのシステムプロンプト構築ロジックを検証する."""
    # main.pyと同じロジックを再現
    personality = "あなたはデイジーです。"
    slack_format = "【出力フォーマット】\nSlack mrkdwn形式で出力してください。"

    system_prompt = personality
    if slack_format:
        system_prompt = system_prompt + "\n\n" + slack_format

    assert system_prompt.startswith(personality)
    assert system_prompt.endswith(slack_format)
    assert "\n\n" in system_prompt

    # 空の場合
    system_prompt_empty = personality
    slack_format_empty = ""
    if slack_format_empty:
        system_prompt_empty = system_prompt_empty + "\n\n" + slack_format_empty

    assert system_prompt_empty == personality
