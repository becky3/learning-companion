"""ユーザー情報自動抽出サービス
仕様: docs/specs/features/user-profiling.md
"""

from __future__ import annotations

import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.db.models import UserProfile
from src.llm.base import LLMProvider, Message

logger = logging.getLogger(__name__)

_EXTRACTION_TEMPLATE = """\
以下の会話から、ユーザーの学習に関する情報を抽出してJSON形式で返してください。
該当する情報がない場合は空配列を返してください。

{{
  "interests": ["トピック1", "トピック2"],
  "skills": [{{"name": "スキル名", "level": "初心者|中級|上級"}}],
  "goals": ["目標1"]
}}

会話:
{message}"""


class UserProfiler:
    """ユーザー情報抽出・プロファイル管理サービス.

    仕様: docs/specs/features/user-profiling.md
    """

    def __init__(
        self,
        llm: LLMProvider,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._llm = llm
        self._session_factory = session_factory

    async def extract_profile(self, user_id: str, message: str) -> None:
        """会話からユーザー情報を抽出しDBに保存する (AC1, AC2, AC5)."""
        prompt = _EXTRACTION_TEMPLATE.format(message=message)
        response = await self._llm.complete([Message(role="user", content=prompt)])

        try:
            data = json.loads(response.content)
        except (json.JSONDecodeError, TypeError):
            logger.warning("Failed to parse LLM response as JSON: %s", response.content)
            return

        if not isinstance(data, dict):
            logger.warning("LLM response JSON is not an object: %r", data)
            return

        # 型バリデーション付きで抽出
        raw_interests = data.get("interests", [])
        interests: list[str] = (
            [v for v in raw_interests if isinstance(v, str)]
            if isinstance(raw_interests, list)
            else []
        )

        raw_skills = data.get("skills", [])
        skills: list[dict[str, str]] = []
        if isinstance(raw_skills, list):
            for item in raw_skills:
                if not isinstance(item, dict):
                    continue
                name = item.get("name")
                level = item.get("level")
                if isinstance(name, str) and isinstance(level, str):
                    skills.append({"name": name, "level": level})

        raw_goals = data.get("goals", [])
        goals: list[str] = (
            [v for v in raw_goals if isinstance(v, str)]
            if isinstance(raw_goals, list)
            else []
        )

        if not interests and not skills and not goals:
            return

        async with self._session_factory() as session:
            result = await session.execute(
                select(UserProfile).where(UserProfile.slack_user_id == user_id)
            )
            profile = result.scalar_one_or_none()

            if profile is None:
                profile = UserProfile(
                    slack_user_id=user_id,
                    interests=json.dumps(interests, ensure_ascii=False),
                    skills=json.dumps(skills, ensure_ascii=False),
                    goals=json.dumps(goals, ensure_ascii=False),
                )
                session.add(profile)
            else:
                profile.interests = json.dumps(
                    _merge_list(
                        json.loads(profile.interests) if profile.interests else [],
                        interests,
                    ),
                    ensure_ascii=False,
                )
                profile.skills = json.dumps(
                    _merge_skills(
                        json.loads(profile.skills) if profile.skills else [],
                        skills,
                    ),
                    ensure_ascii=False,
                )
                profile.goals = json.dumps(
                    _merge_list(
                        json.loads(profile.goals) if profile.goals else [],
                        goals,
                    ),
                    ensure_ascii=False,
                )

            await session.commit()

    async def get_profile(self, user_id: str) -> str | None:
        """ユーザーのプロファイルをSlackフォーマットで返す (AC4)."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(UserProfile).where(UserProfile.slack_user_id == user_id)
            )
            profile = result.scalar_one_or_none()

        if profile is None:
            return None

        interests: list[str] = json.loads(profile.interests) if profile.interests else []
        skills: list[dict[str, str]] = json.loads(profile.skills) if profile.skills else []
        goals: list[str] = json.loads(profile.goals) if profile.goals else []

        if not interests and not skills and not goals:
            return None

        interests_str = ", ".join(interests) if interests else "なし"
        skills_str = (
            ", ".join(f"{s['name']} ({s['level']})" for s in skills)
            if skills
            else "なし"
        )
        goals_str = "、".join(goals) if goals else "なし"

        return (
            ":bust_in_silhouette: あなたのプロファイル\n"
            "\n"
            f"【興味】{interests_str}\n"
            f"【スキル】{skills_str}\n"
            f"【目標】{goals_str}\n"
            "\n"
            ":pencil2: 修正したい場合は教えてね！"
        )


def _merge_list(existing: list[str], new: list[str]) -> list[str]:
    """既存リストに新規項目を追加し重複を除去する."""
    seen: set[str] = set(existing)
    merged = list(existing)
    for item in new:
        if item not in seen:
            seen.add(item)
            merged.append(item)
    return merged


def _merge_skills(
    existing: list[dict[str, str]], new: list[dict[str, str]]
) -> list[dict[str, str]]:
    """スキルリストをマージする。同名スキルはレベルを更新する."""
    by_name: dict[str, dict[str, str]] = {}
    for s in existing:
        name = s.get("name")
        if not name:
            continue
        by_name[name] = s
    for skill in new:
        name = skill.get("name")
        if not name:
            continue
        by_name[name] = skill
    return list(by_name.values())
