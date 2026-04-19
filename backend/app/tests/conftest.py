"""Pytest configuration and fixtures."""

import asyncio
import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Один in-memory SQLite для conftest и для app.infrastructure.db (импорт после установки URL)
if "DATABASE_URL" not in os.environ:
    os.environ["DATABASE_URL"] = (
        "sqlite+aiosqlite:///file:pytest_lab02?mode=memory&cache=shared&uri=true"
    )

_SQLITE_DDL = [
    """
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        email TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        created_at TIMESTAMP NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS orders (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        status TEXT NOT NULL,
        total_amount REAL NOT NULL,
        created_at TIMESTAMP NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS order_items (
        id TEXT PRIMARY KEY,
        order_id TEXT NOT NULL,
        product_name TEXT NOT NULL,
        price REAL NOT NULL,
        quantity INTEGER NOT NULL,
        subtotal REAL NOT NULL,
        FOREIGN KEY (order_id) REFERENCES orders(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS order_status_history (
        id TEXT PRIMARY KEY,
        order_id TEXT NOT NULL,
        status TEXT NOT NULL,
        changed_at TIMESTAMP NOT NULL,
        FOREIGN KEY (order_id) REFERENCES orders(id)
    )
    """,
]


@pytest.fixture(scope="session", autouse=True)
def _init_sqlite_schema_for_app():
    """Создаёт таблицы на том же движке, что использует FastAPI (shared memory SQLite)."""
    if "sqlite" not in os.environ.get("DATABASE_URL", "").lower():
        return

    async def _run():
        from app.infrastructure import db

        async with db.engine.begin() as conn:
            for stmt in _SQLITE_DDL:
                await conn.execute(text(stmt))

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_run())
    finally:
        loop.close()


@pytest.fixture(scope="session")
def test_engine():
    from app.infrastructure import db

    return db.engine


@pytest.fixture(scope="session")
def test_session_factory(test_engine):
    return async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)


@pytest.fixture
async def sqlite_db_session(test_session_factory):
    async with test_session_factory() as session:
        yield session
        await session.rollback()


@pytest.fixture
def sample_user_id():
    return uuid.uuid4()


# --- PostgreSQL: concurrent payment tests (README lab 2) ---


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
