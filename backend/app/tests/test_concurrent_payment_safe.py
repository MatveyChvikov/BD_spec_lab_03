"""
Тест для демонстрации РЕШЕНИЯ race condition (REPEATABLE READ + FOR UPDATE).
"""

pytest_plugins = ("app.tests.conftest_concurrent",)

import asyncio
import time
import uuid

import pytest
from sqlalchemy import text

from app.application.payment_service import PaymentService
from app.domain.exceptions import OrderAlreadyPaidError


async def _create_created_order(db_session):
    """Вспомогательно: пользователь + заказ created + история created."""
    user_id = uuid.uuid4()
    order_id = uuid.uuid4()
    email = f"safe_{uuid.uuid4().hex[:20]}@example.com"
    async with db_session() as session:
        await session.execute(
            text(
                "INSERT INTO users (id, email, name) "
                "VALUES (CAST(:id AS uuid), :email, 'safe test')"
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


@pytest.mark.asyncio
async def test_concurrent_payment_safe_prevents_race_condition(db_session, test_order):
    """Два параллельных pay_order_safe → одна успешная оплата, вторая — ошибка."""
    order_id = test_order

    async def payment_attempt_1():
        async with db_session() as session1:
            service1 = PaymentService(session1)
            return await service1.pay_order_safe(order_id)

    async def payment_attempt_2():
        async with db_session() as session2:
            service2 = PaymentService(session2)
            return await service2.pay_order_safe(order_id)

    results = await asyncio.gather(
        payment_attempt_1(),
        payment_attempt_2(),
        return_exceptions=True,
    )

    success_count = sum(1 for r in results if not isinstance(r, Exception))
    error_count = sum(1 for r in results if isinstance(r, Exception))

    assert success_count == 1, "Ожидалась одна успешная оплата"
    assert error_count == 1, "Ожидалась одна неудачная попытка"

    rejected = next(r for r in results if isinstance(r, Exception))
    assert isinstance(rejected, OrderAlreadyPaidError), (
        f"Ожидался OrderAlreadyPaidError (в т.ч. после serialization conflict), получено: {rejected!r}"
    )

    async with db_session() as session:
        service = PaymentService(session)
        history = await service.get_payment_history(order_id)

    assert len(history) == 1, "Ожидалась 1 запись об оплате (БЕЗ RACE CONDITION!)"

    print("✅ RACE CONDITION PREVENTED!")
    print(f"Order {order_id} was paid only ONCE:")
    print(f"  - {history[0]['changed_at']}: status = {history[0]['status']}")
    print(f"Second attempt was rejected: {rejected!r}")
    print("✅ test PASSED (проблема решена)")


@pytest.mark.asyncio
async def test_concurrent_payment_safe_with_explicit_timing(db_session):
    """FOR UPDATE: вторая транзакция ждёт задержку первой (>= 1 с)."""
    order_id = await _create_created_order(db_session)

    async def first():
        async with db_session() as s:
            return await PaymentService(s).pay_order_safe(
                order_id, delay_after_row_lock_sec=1.0
            )

    async def second():
        await asyncio.sleep(0.1)
        async with db_session() as s:
            return await PaymentService(s).pay_order_safe(order_id)

    t0 = time.perf_counter()
    results = await asyncio.gather(first(), second(), return_exceptions=True)
    elapsed = time.perf_counter() - t0

    assert elapsed >= 1.0, "Вторая оплата должна ждать освобождения блокировки"
    assert sum(1 for r in results if not isinstance(r, Exception)) == 1
    assert sum(1 for r in results if isinstance(r, Exception)) == 1

    async with db_session() as s:
        history = await PaymentService(s).get_payment_history(order_id)
    assert len(history) == 1


@pytest.mark.asyncio
async def test_concurrent_payment_safe_multiple_orders(db_session):
    """FOR UPDATE блокирует только строку заказа — разные заказы платятся параллельно."""
    o1 = await _create_created_order(db_session)
    o2 = await _create_created_order(db_session)

    async def pay1():
        async with db_session() as s:
            return await PaymentService(s).pay_order_safe(o1)

    async def pay2():
        async with db_session() as s:
            return await PaymentService(s).pay_order_safe(o2)

    results = await asyncio.gather(pay1(), pay2(), return_exceptions=True)
    assert all(not isinstance(r, Exception) for r in results)

    async with db_session() as s:
        svc = PaymentService(s)
        assert len(await svc.get_payment_history(o1)) == 1
        assert len(await svc.get_payment_history(o2)) == 1
