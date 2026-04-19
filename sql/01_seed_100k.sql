\timing on

-- ============================================
-- LAB 03: Готовый seed для студентов
-- ============================================
-- Требуется рабочая схема из предыдущих лабораторных:
-- users, orders, order_items, order_status_history

TRUNCATE TABLE order_status_history, order_items, orders, users RESTART IDENTITY CASCADE;

SELECT setseed(0.42);

-- 10k пользователей
INSERT INTO users (email, name, created_at)
SELECT
    'user' || lpad(gs::text, 5, '0') || '@example.com',
    format('User %s', gs),
    timestamp '2024-01-01' + random() * (timestamp '2026-01-01' - timestamp '2024-01-01')
FROM generate_series(1, 10000) AS gs;

-- 100k заказов
WITH user_pool AS (
    SELECT array_agg(id) AS ids
    FROM users
)
-- id задаём явно: на партиционированной таблице orders DEFAULT по uuid иногда не подставляется в INSERT…SELECT
INSERT INTO orders (id, user_id, status, total_amount, created_at)
SELECT
    uuid_generate_v4() AS id,
    user_pool.ids[1 + floor(random() * array_length(user_pool.ids, 1))::int] AS user_id,
    CASE
        WHEN random() < 0.50 THEN 'paid'
        WHEN random() < 0.75 THEN 'completed'
        WHEN random() < 0.88 THEN 'shipped'
        WHEN random() < 0.94 THEN 'cancelled'
        ELSE 'created'
    END AS status,
    0::DECIMAL(12, 2) AS total_amount,
    timestamp '2024-01-01' + random() * (timestamp '2026-01-01' - timestamp '2024-01-01') AS created_at
FROM generate_series(1, 100000) gs
CROSS JOIN user_pool;

-- 1..4 позиции на заказ (в среднем ~4); subtotal обязателен для схемы lab_02.
-- Триггер пересчёта total_amount на каждой строке делает bulk-insert неприемлемо медленным — отключаем на время загрузки.
ALTER TABLE order_items DISABLE TRIGGER trigger_order_items_refresh_total;

INSERT INTO order_items (order_id, product_name, price, quantity, subtotal)
SELECT
    o.id,
    'Product ' || (1 + floor(random() * 2000)::int) AS product_name,
    x.price,
    x.quantity,
    round((x.price * x.quantity)::numeric, 2) AS subtotal
FROM orders o
CROSS JOIN LATERAL generate_series(1, 1 + floor(random() * 4)::int) s
CROSS JOIN LATERAL (
    SELECT
        round((5 + random() * 995)::numeric, 2) AS price,
        (1 + floor(random() * 4)::int) AS quantity
) x;

ALTER TABLE order_items ENABLE TRIGGER trigger_order_items_refresh_total;

-- Пересчёт total_amount
UPDATE orders o
SET total_amount = totals.total_amount
FROM (
    SELECT
        order_id,
        round(sum(price * quantity)::numeric, 2) AS total_amount
    FROM order_items
    GROUP BY order_id
) totals
WHERE totals.order_id = o.id;

-- История: начальный статус
INSERT INTO order_status_history (order_id, status, changed_at)
SELECT
    id,
    'created',
    created_at
FROM orders;

-- История: текущий статус (если отличен от created)
INSERT INTO order_status_history (order_id, status, changed_at)
SELECT
    id,
    status,
    created_at + ((1 + floor(random() * 240)::int)::text || ' hours')::interval
FROM orders
WHERE status <> 'created';

ANALYZE;

-- Контрольные цифры
SELECT 'users' AS table_name, count(*) AS rows_count FROM users
UNION ALL
SELECT 'orders', count(*) FROM orders
UNION ALL
SELECT 'order_items', count(*) FROM order_items
UNION ALL
SELECT 'order_status_history', count(*) FROM order_status_history;
