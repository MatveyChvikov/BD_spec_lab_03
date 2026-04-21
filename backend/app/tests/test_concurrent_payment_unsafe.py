"""
Тест для демонстрации ПРОБЛЕМЫ race condition.

Тест ПРОХОДИТ, подтверждая двойную оплату при pay_order_unsafe().
Окно гонки узкое: при необходимости делается несколько попыток с новым заказом.
"""

pytest_plugins = ("app.tests.conftest_concurrent",)

import asyncio
import uuid

import pytest
from sqlalchemy import text

from app.application.payment_service import PaymentService


async def _fresh_created_order(db_session):
    user_id = uuid.uuid4()
    order_id = uuid.uuid4()
    email = f"unsafe_retry_{uuid.uuid4().hex[:16]}@example.com"
    async with db_session() as session:
        await session.execute(
            text(
                "INSERT INTO users (id, email, name) "
                "VALUES (CAST(:id AS uuid), :email, 'retry')"
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
async def test_concurrent_payment_unsafe_demonstrates_race_condition(db_session):
    """Два параллельных pay_order_unsafe → в истории две записи paid (при удачном пересечении транзакций)."""
    last_results = None
    last_order_id = None
    last_history = None

    for _ in range(30):
        order_id = await _fresh_created_order(db_session)

        async def payment_attempt_1(oid=order_id):
            async with db_session() as session1:
                return await PaymentService(session1).pay_order_unsafe(oid)

        async def payment_attempt_2(oid=order_id):
            async with db_session() as session2:
                return await PaymentService(session2).pay_order_unsafe(oid)

        last_results = await asyncio.gather(
            payment_attempt_1(),
            payment_attempt_2(),
            return_exceptions=True,
        )
        last_order_id = order_id

        async with db_session() as session:
            service = PaymentService(session)
            last_history = await service.get_payment_history(order_id)

        if len(last_history) == 2:
            break
    else:
        pytest.fail(
            "За 30 попыток не поймана двойная оплата. Если БД из lab_01 с триггером "
            "против повторной оплаты — схема lab_02 без этого триггера обязательна. "
            f"Последние результаты: {last_results}, история: {last_history}"
        )

    for i, result in enumerate(last_results):
        if isinstance(result, Exception):
            print(f"Попытка {i + 1} завершилась ошибкой: {result}")
        else:
            print(f"Попытка {i + 1} успешна: {result}")

    assert len(last_history) == 2, "Ожидалось 2 записи об оплате (RACE CONDITION!)"

    print("⚠️ RACE CONDITION DETECTED!")
    print(f"Order {last_order_id} was paid TWICE:")
    for record in last_history:
        print(f"  - {record['changed_at']}: status = {record['status']}")
    print("✅ test PASSED (демонстрирует проблему)")


@pytest.mark.asyncio
async def test_concurrent_payment_unsafe_both_succeed(db_session):
    """Повторяем попытку: окно гонки узкое, но двойная оплата должна иногда воспроизводиться."""
    last_results = None
    for _ in range(30):
        order_id = await _fresh_created_order(db_session)

        async def payment_attempt_1(oid=order_id):
            async with db_session() as session1:
                return await PaymentService(session1).pay_order_unsafe(oid)

        async def payment_attempt_2(oid=order_id):
            async with db_session() as session2:
                return await PaymentService(session2).pay_order_unsafe(oid)

        last_results = await asyncio.gather(
            payment_attempt_1(),
            payment_attempt_2(),
            return_exceptions=True,
        )

        async with db_session() as session:
            history = await PaymentService(session).get_payment_history(order_id)

        if len(history) == 2:
            assert not any(isinstance(r, Exception) for r in last_results), last_results
            return

    pytest.fail(
        "За 30 попыток не удалось поймать двойную оплату; "
        f"последние результаты: {last_results}"
    )
