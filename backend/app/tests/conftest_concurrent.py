"""Фикстуры PostgreSQL только для concurrent payment tests (подключается через pytest_plugins)."""

import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def _postgres_url_for_concurrent_tests() -> str | None:
    url = os.environ.get("DATABASE_URL", "")
    if url.startswith("postgresql"):
        return url
    if "sqlite" in url.lower():
        return None
    return "postgresql+asyncpg://postgres:postgres@localhost:5432/marketplace"


@pytest_asyncio.fixture
async def db_session():
    url = _postgres_url_for_concurrent_tests()
    if url is None:
        pytest.skip(
            "Конкурентные тесты: задайте DATABASE_URL=postgresql+asyncpg://... "
            "(например localhost при docker-compose up db)"
        )
    engine = create_async_engine(url, echo=False, pool_pre_ping=True)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1 FROM order_statuses LIMIT 1"))
    except Exception as exc:
        await engine.dispose()
        pytest.skip(
            "Нужен PostgreSQL со схемой маркетплейса: "
            f"docker-compose up -d db. ({exc})"
        )

    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield factory
    await engine.dispose()


@pytest_asyncio.fixture
async def test_order(db_session):
    user_id = uuid.uuid4()
    order_id = uuid.uuid4()
    email = f"concurrent_{uuid.uuid4().hex[:20]}@example.com"
    async with db_session() as session:
        await session.execute(
            text(
                "INSERT INTO users (id, email, name) "
                "VALUES (CAST(:id AS uuid), :email, 'concurrent test')"
            ),
            {"id": str(user_id), "email": email},
        )
        await session.execute(
            text(
                "INSERT INTO orders (id, user_id, status, total_amount) "
                "VALUES (CAST(:oid AS uuid), CAST(:uid AS uuid), 'created', 0)"
            ),
            {"oid": str(order_id), "uid": str(user_id)},
        )
        await session.execute(
            text(
                "INSERT INTO order_status_history (id, order_id, status, changed_at) "
                "VALUES (uuid_generate_v4(), CAST(:oid AS uuid), 'created', NOW())"
            ),
            {"oid": str(order_id)},
        )
        await session.commit()
    return order_id
