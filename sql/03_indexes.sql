\timing on
\echo '=== APPLY INDEXES ==='

-- ============================================
-- Индексы под EXPLAIN из 02_explain_before.sql
-- Обоснование типов — в REPORT.md
-- ============================================

-- Q1: равенство по user_id + сортировка по created_at → составной BTREE
CREATE INDEX IF NOT EXISTS idx_orders_user_created_at
    ON orders (user_id, created_at DESC);

-- Q2: равенство по status + диапазон по created_at → BTREE (leading column status)
CREATE INDEX IF NOT EXISTS idx_orders_status_created_at
    ON orders (status, created_at);

-- Q3: соединение по order_id → BTREE на FK-столбце
CREATE INDEX IF NOT EXISTS idx_order_items_order_id
    ON order_items (order_id);

-- Q3: GROUP BY product_name → BTREE по текстовому ключу группировки
CREATE INDEX IF NOT EXISTS idx_order_items_product_name
    ON order_items (product_name);

-- Дополнительно: BRIN по created_at на большой append-only таблице заказов
-- (компактный индекс для сканов по широкому диапазону дат)
CREATE INDEX IF NOT EXISTS brin_orders_created_at
    ON orders USING brin (created_at);

ANALYZE orders;
ANALYZE order_items;
ANALYZE order_status_history;
ANALYZE users;
