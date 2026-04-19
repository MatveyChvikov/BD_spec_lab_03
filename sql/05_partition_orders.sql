\timing on
\set ON_ERROR_STOP on
\echo '=== PARTITION ORDERS BY DATE (RANGE monthly) ==='

-- Остаток неудачного прогона (если был)
DROP TABLE IF EXISTS orders_old CASCADE;

-- Повторный запуск на уже партиционированной таблице ломает RENAME/CREATE (конфликт имён дочерних партиций)
DO $guard$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND c.relname = 'orders'
          AND c.relkind = 'p'
    ) THEN
        RAISE EXCEPTION 'Таблица public.orders уже партиционирована. Повторный запуск 05 не нужен. Чистый цикл: docker compose down -v, затем up и шаги 01–06 по порядку.';
    END IF;
END
$guard$;

-- Стратегия: RANGE(created_at) по месяцам + DEFAULT-партиция.
-- Для FK на партиционированную таблицу в PostgreSQL нужен составной ключ (id, created_at);
-- добавляем order_created_at в дочерние таблицы и триггеры, чтобы приложение могло
-- вставлять строки без явной передачи created_at заказа.

BEGIN;

-- ---------------------------------------------------------------------------
-- Шаг 1: денормализация created_at заказа в дочерние строки
-- ---------------------------------------------------------------------------
ALTER TABLE order_items ADD COLUMN IF NOT EXISTS order_created_at TIMESTAMPTZ;

UPDATE order_items oi
SET order_created_at = s.created_at
FROM (
    SELECT DISTINCT ON (o.id) o.id AS order_id, o.created_at
    FROM orders o
    ORDER BY o.id, o.created_at
) s
WHERE oi.order_id = s.order_id
  AND (oi.order_created_at IS DISTINCT FROM s.created_at OR oi.order_created_at IS NULL);

ALTER TABLE order_status_history ADD COLUMN IF NOT EXISTS order_created_at TIMESTAMPTZ;

UPDATE order_status_history h
SET order_created_at = s.created_at
FROM (
    SELECT DISTINCT ON (o.id) o.id AS order_id, o.created_at
    FROM orders o
    ORDER BY o.id, o.created_at
) s
WHERE h.order_id = s.order_id
  AND (h.order_created_at IS DISTINCT FROM s.created_at OR h.order_created_at IS NULL);

ALTER TABLE order_items ALTER COLUMN order_created_at SET NOT NULL;
ALTER TABLE order_status_history ALTER COLUMN order_created_at SET NOT NULL;

CREATE OR REPLACE FUNCTION trg_set_order_created_at_from_orders()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.order_created_at IS NULL THEN
        SELECT o.created_at
        INTO STRICT NEW.order_created_at
        FROM orders o
        WHERE o.id = NEW.order_id
        ORDER BY o.created_at
        LIMIT 1;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_order_items_set_oct ON order_items;
CREATE TRIGGER trg_order_items_set_oct
    BEFORE INSERT ON order_items
    FOR EACH ROW
    EXECUTE FUNCTION trg_set_order_created_at_from_orders();

DROP TRIGGER IF EXISTS trg_osh_set_oct ON order_status_history;
CREATE TRIGGER trg_osh_set_oct
    BEFORE INSERT ON order_status_history
    FOR EACH ROW
    EXECUTE FUNCTION trg_set_order_created_at_from_orders();

-- ---------------------------------------------------------------------------
-- Шаг 2: отвязать FK к orders, заменить таблицу на партиционированную
-- ---------------------------------------------------------------------------
ALTER TABLE order_items DROP CONSTRAINT IF EXISTS order_items_order_id_fkey;
ALTER TABLE order_status_history DROP CONSTRAINT IF EXISTS order_status_history_order_id_fkey;

ALTER TABLE orders RENAME TO orders_old;

CREATE TABLE orders (
    id UUID NOT NULL,
    user_id UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    status TEXT NOT NULL REFERENCES order_statuses (status),
    total_amount NUMERIC(18, 2) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT orders_total_nonnegative CHECK (total_amount >= 0),
    PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);

-- Месячные партиции (покрывают seed 2024–2026 и запас)
DO $$
DECLARE
    d_start date := date '2023-12-01';
    d_end   date;
    pname   text;
BEGIN
    WHILE d_start < date '2027-04-01' LOOP
        d_end := (d_start + interval '1 month')::date;
        pname := 'orders_p_' || to_char(d_start, 'YYYY') || lpad(extract(month FROM d_start)::text, 2, '0');
        EXECUTE format(
            'CREATE TABLE %I PARTITION OF orders FOR VALUES FROM (%L::timestamptz) TO (%L::timestamptz)',
            pname,
            d_start::text,
            d_end::text
        );
        d_start := d_end;
    END LOOP;
END $$;

CREATE TABLE orders_default PARTITION OF orders DEFAULT;

INSERT INTO orders (id, user_id, status, total_amount, created_at)
SELECT id, user_id, status, total_amount, created_at
FROM orders_old;

DROP TABLE orders_old;

ALTER TABLE order_items
    ADD CONSTRAINT order_items_orders_fk
    FOREIGN KEY (order_id, order_created_at)
    REFERENCES orders (id, created_at)
    ON DELETE CASCADE;

ALTER TABLE order_status_history
    ADD CONSTRAINT order_status_history_orders_fk
    FOREIGN KEY (order_id, order_created_at)
    REFERENCES orders (id, created_at)
    ON DELETE CASCADE;

-- ---------------------------------------------------------------------------
-- Шаг 3: индексы (повторно после пересоздания orders)
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_orders_id ON orders (id);
CREATE INDEX IF NOT EXISTS idx_orders_user_created_at ON orders (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_orders_status_created_at ON orders (status, created_at);
CREATE INDEX IF NOT EXISTS brin_orders_created_at ON orders USING brin (created_at);

ANALYZE orders;
ANALYZE order_items;
ANALYZE order_status_history;

COMMIT;

\echo '=== Partitioning done. Row counts: ==='
SELECT 'orders' AS t, count(*) FROM orders
UNION ALL SELECT 'order_items', count(*) FROM order_items
UNION ALL SELECT 'order_status_history', count(*) FROM order_status_history;
