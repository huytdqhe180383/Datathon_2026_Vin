# Benchmark Few-Shot SQL Examples

These examples show benchmark-style SQL patterns. Adapt them to the exact
question and selected tables.

## Delivered Net Revenue

Question: What is the delivered net revenue after discounts?

```sql
SELECT
  ROUND(SUM(oi.quantity * oi.unit_price - oi.discount_amount), 2) AS delivered_net_revenue
FROM core.orders AS o
JOIN core.order_items AS oi
  ON oi.order_id = o.order_id
WHERE o.order_status = 'delivered'
```

## Promo Revenue Share

Question: What share of total net revenue comes from orders that used at least
one promo code?

```sql
WITH order_promo_flags AS (
  SELECT oi.order_id, 1 AS has_promo
  FROM core.order_items AS oi
  JOIN core.order_item_promotions AS oip
    ON oip.order_item_id = oi.order_item_id
  GROUP BY oi.order_id
),
order_revenue AS (
  SELECT order_id, SUM(quantity * unit_price - discount_amount) AS order_net_revenue
  FROM core.order_items
  GROUP BY order_id
)
SELECT
  ROUND(
    100.0 * SUM(CASE WHEN p.has_promo = 1 THEN r.order_net_revenue ELSE 0 END)
    / NULLIF(SUM(r.order_net_revenue), 0),
    4
  ) AS promo_revenue_share_pct
FROM order_revenue AS r
LEFT JOIN order_promo_flags AS p
  ON p.order_id = r.order_id
```

## Monthly Delivered Revenue

Question: Return monthly delivered order counts and delivered net revenue.

```sql
SELECT
  TO_CHAR(DATE_TRUNC('month', o.order_date), 'YYYY-MM') AS order_month,
  COUNT(DISTINCT o.order_id) AS delivered_orders,
  ROUND(SUM(oi.quantity * oi.unit_price - oi.discount_amount), 2) AS delivered_net_revenue
FROM core.orders AS o
JOIN core.order_items AS oi
  ON oi.order_id = o.order_id
WHERE o.order_status = 'delivered'
GROUP BY 1
ORDER BY 1
```

## Return Rate

Question: Which payment method has the highest return rate?

```sql
SELECT
  p.payment_method,
  ROUND(100.0 * AVG(CASE WHEN o.order_status = 'returned' THEN 1.0 ELSE 0.0 END), 4) AS return_rate_pct
FROM core.orders AS o
JOIN core.payments AS p
  ON p.order_id = o.order_id
GROUP BY p.payment_method
ORDER BY return_rate_pct DESC, p.payment_method
LIMIT 1
```

## Order-Size Buckets

Question: Return a table of order-size buckets.

```sql
WITH order_units AS (
  SELECT
    o.order_id,
    SUM(oi.quantity) AS total_units,
    SUM(oi.quantity * oi.unit_price - oi.discount_amount) AS order_net_value
  FROM core.orders AS o
  JOIN core.order_items AS oi
    ON oi.order_id = o.order_id
  GROUP BY o.order_id
)
SELECT
  CASE
    WHEN total_units = 1 THEN '1'
    WHEN total_units BETWEEN 2 AND 3 THEN '2-3'
    WHEN total_units BETWEEN 4 AND 6 THEN '4-6'
    WHEN total_units BETWEEN 7 AND 10 THEN '7-10'
    ELSE '11+'
  END AS unit_bucket,
  COUNT(*) AS orders,
  ROUND(AVG(order_net_value), 2) AS avg_order_net_value,
  ROUND(SUM(order_net_value), 2) AS total_net_revenue
FROM order_units
GROUP BY 1
ORDER BY CASE unit_bucket WHEN '1' THEN 1 WHEN '2-3' THEN 2 WHEN '4-6' THEN 3 WHEN '7-10' THEN 4 ELSE 5 END
```
