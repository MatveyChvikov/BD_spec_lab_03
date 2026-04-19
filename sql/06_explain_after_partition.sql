\timing on
\echo '=== AFTER PARTITIONING ==='

SET max_parallel_workers_per_gather = 0;
SET work_mem = '32MB';

ANALYZE orders;
ANALYZE order_items;
ANALYZE order_status_history;

-- Те же запросы, что в 02 / 04

\echo '--- Q1: последние заказы пользователя ---'
EXPLAIN (ANALYZE, BUFFERS)
SELECT o.id, o.status, o.total_amount, o.created_at
FROM orders o
WHERE o.user_id = (SELECT id FROM users ORDER BY email LIMIT 1)
ORDER BY o.created_at DESC
LIMIT 100;

\echo '--- Q2: выручка по оплаченным заказам за год ---'
EXPLAIN (ANALYZE, BUFFERS)
SELECT count(*) AS orders_cnt, coalesce(sum(total_amount), 0) AS revenue
FROM orders
WHERE status = 'paid'
  AND created_at >= TIMESTAMPTZ '2024-06-01'
  AND created_at < TIMESTAMPTZ '2025-06-01';

\echo '--- Q3: топ товаров по выручке ---'
EXPLAIN (ANALYZE, BUFFERS)
SELECT oi.product_name,
       sum(oi.subtotal) AS revenue,
       count(*) AS line_count
FROM order_items oi
INNER JOIN orders o ON o.id = oi.order_id
WHERE o.created_at >= TIMESTAMPTZ '2024-01-01'
  AND o.created_at < TIMESTAMPTZ '2025-01-01'
GROUP BY oi.product_name
ORDER BY revenue DESC
LIMIT 25;

\echo '--- Q4: помесячная статистика ---'
EXPLAIN (ANALYZE, BUFFERS)
SELECT date_trunc('month', created_at) AS m,
       count(*) AS orders_cnt,
       avg(total_amount) AS avg_amount
FROM orders
GROUP BY 1
ORDER BY 1;

\echo '--- Проверка partition pruning (должны затрагиваться только нужные партиции) ---'
EXPLAIN (ANALYZE, BUFFERS)
SELECT count(*)
FROM orders
WHERE created_at >= TIMESTAMPTZ '2025-03-01'
  AND created_at < TIMESTAMPTZ '2025-04-01';
