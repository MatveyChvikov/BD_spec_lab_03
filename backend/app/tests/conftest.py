"""Pytest configuration and fixtures (для только test_domain: ``-p no:anyio`` — см. CI)."""

import asyncio
import os

import pytest
from sqlalchemy import text

# Один in-memory SQLite для conftest и для app.infrastructure.db (импорт после установки URL)
if "DATABASE_URL" not in os.environ:
    os.environ["DATABASE_URL"] = (
        "sqlite+aiosqlite:///file:pytest_lab02?mode=memory&cache=shared&uri=true"
    )

# True, если в сессии есть app/tests/test_integration.py — нужен общий SQLite-движок приложения.
_session_has_integration_tests = False


def pytest_collection_modifyitems(config, items):
    global _session_has_integration_tests
    _session_has_integration_tests = any(
        "test_integration" in item.nodeid for item in items
    )


def pytest_sessionfinish(session, exitstatus):
    """Закрыть глобальный async engine после сессии (интеграционные тесты на SQLite)."""
    if not _session_has_integration_tests:
        return
    from app.infrastructure.db import reset_engine_pool

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(reset_engine_pool())
    finally:
        loop.close()

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
    """DDL в shared SQLite только когда в прогоне есть интеграционные тесты.

    Доменные тесты БД не используют — поднятие aiosqlite здесь оставляло процесс pytest
    открытым десятки секунд после «28 passed».
    """
    if not _session_has_integration_tests:
        return
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
