"""SQLAlchemy モデル定義
仕様: docs/specs/overview.md §5 DB設計
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Feed(Base):
    __tablename__ = "feeds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(String(2048), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    category: Mapped[str] = mapped_column(String(128), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    articles: Mapped[list[Article]] = relationship(back_populates="feed", cascade="all, delete-orphan")


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    feed_id: Mapped[int] = mapped_column(ForeignKey("feeds.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="")
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    delivered: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")

    feed: Mapped[Feed] = relationship(back_populates="articles")


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slack_user_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    interests: Mapped[str] = mapped_column(Text, default="")
    skills: Mapped[str] = mapped_column(Text, default="")
    goals: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slack_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    thread_ts: Mapped[str] = mapped_column(String(64), default="")
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class LearningTopic(Base):
    """学びトピック（自動抽出 + 記事化トラッキング）

    仕様: docs/specs/topic-skill.md
    """

    __tablename__ = "learning_topics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # トピック情報（自動抽出）
    topic: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)
    source: Mapped[str] = mapped_column(
        String(512), nullable=False
    )  # "docs/retro/f2.md#RSS日付問題"
    priority: Mapped[int] = mapped_column(Integer, default=1)  # 抽出時の優先度

    # 記事化ステータス
    article_status: Mapped[str] = mapped_column(String(32), default="pending")
    # pending: 未着手, draft: 下書き中, published: 公開済み

    article_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # メタ情報
    scanned_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
