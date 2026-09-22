-- AutoDBA Phase 1: Deterministic Seed Data
-- 1. Seed 500 Customers
INSERT INTO customers (id, name, email, created_at)
SELECT
    i,
    'Customer ' || i,
    'customer' || i || '@example.com',
    TIMESTAMPTZ '2025-01-01 00:00:00+00' + (i * INTERVAL '1 hour')
FROM generate_series(1, 500) AS i;

-- 2. Seed 100 Products across 10 deterministic categories
INSERT INTO products (id, name, category, price, stock, created_at)
SELECT
    i,
    'Product ' || i,
    (ARRAY['Electronics', 'Clothing', 'Books', 'Home & Kitchen', 'Sports', 'Toys', 'Automotive', 'Beauty', 'Health', 'Groceries'])[(i % 10) + 1],
    ROUND(((10 + (i * 7) % 500) + 0.99)::numeric, 2),
    ((i * 13) % 200) + 5,
    TIMESTAMPTZ '2025-01-01 00:00:00+00' + (i * INTERVAL '2 hours')
FROM generate_series(1, 100) AS i;

-- 3. Seed 5,000 Orders distributed deterministically across customers
-- Customer 42 will receive multiple orders for controlled indexing experiments
INSERT INTO orders (id, customer_id, order_date, total_amount, status)
SELECT
    i,
    ((i - 1) % 500) + 1,
    TIMESTAMPTZ '2025-02-01 00:00:00+00' + (i * INTERVAL '15 minutes'),
    ROUND((25.00 + ((i * 17) % 450) + 0.50)::numeric, 2),
    (ARRAY['completed', 'shipped', 'processing', 'pending', 'cancelled'])[(i % 5) + 1]
FROM generate_series(1, 5000) AS i;

-- 4. Seed 15,000 Order Items (3 items per order)
INSERT INTO order_items (id, order_id, product_id, quantity, unit_price)
SELECT
    j,
    ((j - 1) / 3) + 1,
    ((j * 7) % 100) + 1,
    (j % 5) + 1,
    ROUND((10.00 + ((j * 11) % 150) + 0.95)::numeric, 2)
FROM generate_series(1, 15000) AS j;

-- Synchronize serial primary key sequences with inserted IDs
SELECT setval('customers_id_seq', (SELECT MAX(id) FROM customers));
SELECT setval('products_id_seq', (SELECT MAX(id) FROM products));
SELECT setval('orders_id_seq', (SELECT MAX(id) FROM orders));
SELECT setval('order_items_id_seq', (SELECT MAX(id) FROM order_items));

-- Analyze tables to compute accurate query planner distribution statistics
ANALYZE customers;
ANALYZE products;
ANALYZE orders;
ANALYZE order_items;
