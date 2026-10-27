from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

engine = create_async_engine(settings.DATABASE_URL)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    """Declarative base class for all models."""


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields an async database session."""
    async with async_session_factory() as session:
        yield session
