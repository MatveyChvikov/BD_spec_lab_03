"""Database connection and session management."""

import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@db:5432/marketplace"
)

_engine = None
_SessionLocal = None


def _session_factory():
    """Ленивая инициализация: движок привязывается к текущему event loop (важно для pytest+httpx)."""
    global _engine, _SessionLocal
    if _SessionLocal is None:
        # echo=True заливает CI логи (интеграционные тесты) и может замедлять шаги Actions
        _echo = os.getenv("SQLALCHEMY_ECHO", "").lower() in ("1", "true", "yes")
        _engine = create_async_engine(DATABASE_URL, echo=_echo)
        _SessionLocal = async_sessionmaker(
            _engine, expire_on_commit=False, class_=AsyncSession
        )
    return _SessionLocal


async def reset_engine_pool() -> None:
    """Сброс пула (между async-тестами с разными event loop)."""
    global _engine, _SessionLocal
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _SessionLocal = None


# Совместимость: payment_routes и тесты могут импортировать engine
def __getattr__(name: str):
    if name == "engine":
        _session_factory()
        return _engine
    if name == "SessionLocal":
        return _session_factory()
    raise AttributeError(name)


async def get_db() -> AsyncSession:
    """Dependency for getting database session."""
    SessionLocal = _session_factory()
    async with SessionLocal() as session:
        try:
            yield session
            if session.in_transaction():
                await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
