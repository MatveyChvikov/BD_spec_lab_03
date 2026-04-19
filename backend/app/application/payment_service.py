"""Сервис для демонстрации конкурентных оплат."""

import asyncio
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions import OrderAlreadyPaidError, OrderNotFoundError


class PaymentService:
    """Сервис для обработки платежей с разными уровнями изоляции."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def pay_order_unsafe(self, order_id: uuid.UUID) -> dict:
        """
        НЕБЕЗОПАСНАЯ реализация: READ COMMITTED по умолчанию, без FOR UPDATE.
        Проверка статуса и обновление разнесены — при конкуренции возможны две
        записи об оплате в order_status_history.
        """
        oid = str(order_id)
        try:
            res = await self.session.execute(
                text("SELECT status FROM orders WHERE id = CAST(:order_id AS uuid)"),
                {"order_id": oid},
            )
            row = res.fetchone()
            if row is None:
                raise OrderNotFoundError(order_id)
            if row[0] != "created":
                raise OrderAlreadyPaidError(order_id)

            await self.session.execute(
                text("UPDATE orders SET status = 'paid' WHERE id = CAST(:order_id AS uuid)"),
                {"order_id": oid},
            )
            await self.session.execute(
                text(
                    """
                    INSERT INTO order_status_history (id, order_id, status, changed_at)
                    VALUES (uuid_generate_v4(), CAST(:order_id AS uuid), 'paid', NOW())
                    """
                ),
                {"order_id": oid},
            )
            await self.session.commit()
            return {"order_id": order_id, "status": "paid"}
        except Exception:
            await self.session.rollback()
            raise

    async def pay_order_safe(
        self,
        order_id: uuid.UUID,
        *,
        delay_after_row_lock_sec: float | None = None,
    ) -> dict:
        """
        БЕЗОПАСНАЯ реализация: REPEATABLE READ + SELECT ... FOR UPDATE.
        delay_after_row_lock_sec — только для демонстрации блокировок в тестах.
        """
        oid = str(order_id)
        try:
            await self.session.execute(
                text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            )
            res = await self.session.execute(
                text(
                    "SELECT status FROM orders WHERE id = CAST(:order_id AS uuid) FOR UPDATE"
                ),
                {"order_id": oid},
            )
            row = res.fetchone()
            if row is None:
                raise OrderNotFoundError(order_id)
            if row[0] != "created":
                raise OrderAlreadyPaidError(order_id)

            if delay_after_row_lock_sec:
                await asyncio.sleep(delay_after_row_lock_sec)

            upd = await self.session.execute(
                text(
                    """
                    UPDATE orders SET status = 'paid'
                    WHERE id = CAST(:order_id AS uuid) AND status = 'created'
                    """
                ),
                {"order_id": oid},
            )
            if upd.rowcount == 0:
                raise OrderAlreadyPaidError(order_id)

            await self.session.execute(
                text(
                    """
                    INSERT INTO order_status_history (id, order_id, status, changed_at)
                    VALUES (uuid_generate_v4(), CAST(:order_id AS uuid), 'paid', NOW())
                    """
                ),
                {"order_id": oid},
            )
            await self.session.commit()
            return {"order_id": order_id, "status": "paid"}
        except DBAPIError as e:
            await self.session.rollback()
            if "serialize" in str(e).lower():
                raise OrderAlreadyPaidError(order_id) from e
            raise
        except Exception:
            await self.session.rollback()
            raise

    async def get_payment_history(self, order_id: uuid.UUID) -> list[dict[str, Any]]:
        """Записи истории со статусом paid для заказа."""
        oid = str(order_id)
        res = await self.session.execute(
            text(
                """
                SELECT id, order_id, status, changed_at
                FROM order_status_history
                WHERE order_id = CAST(:order_id AS uuid) AND status = 'paid'
                ORDER BY changed_at
                """
            ),
            {"order_id": oid},
        )
        rows = res.fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            changed = row[3]
            if hasattr(changed, "isoformat"):
                changed_s = changed.isoformat()
            else:
                changed_s = str(changed)
            out.append(
                {
                    "id": str(row[0]),
                    "order_id": str(row[1]),
                    "status": row[2],
                    "changed_at": changed_s,
                }
            )
        return out
