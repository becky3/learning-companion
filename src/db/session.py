"""DB接続・セッション管理
仕様: docs/specs/overview.md §5 DB設計
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from src.config.settings import get_settings
from src.db.models import Base

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(settings.database_url, echo=False)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(_get_engine(), expire_on_commit=False)
    return _session_factory


async def init_db() -> None:
    """テーブルを作成し、不足カラムがあれば追加する."""
    engine = _get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_migrate_add_missing_columns)


def _migrate_add_missing_columns(connection) -> None:  # type: ignore[no-untyped-def]
    """既存テーブルに不足カラムがあれば ALTER TABLE で追加する."""
    import sqlalchemy as sa

    inspector = sa.inspect(connection)
    for table_name, table in Base.metadata.tables.items():
        if not inspector.has_table(table_name):
            continue
        existing = {col["name"] for col in inspector.get_columns(table_name)}
        for col in table.columns:
            if col.name not in existing:
                col_type = col.type.compile(dialect=connection.dialect)
                connection.execute(
                    sa.text(f"ALTER TABLE {table_name} ADD COLUMN {col.name} {col_type}")
                )


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """非同期セッションを生成するジェネレータ."""
    factory = get_session_factory()
    async with factory() as session:
        yield session
