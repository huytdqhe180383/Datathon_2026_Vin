BEGIN;

TRUNCATE TABLE
    core.load_issues,
    core.returns,
    core.reviews,
    core.order_item_promotions,
    core.shipments,
    core.payments,
    core.inventory_snapshots,
    core.order_items,
    core.orders,
    core.promotions,
    core.products,
    core.customers,
    core.geography
RESTART IDENTITY CASCADE;

INSERT INTO core.geography (zip_code, city, region, district)
SELECT DISTINCT
    zip::text AS zip_code,
    city,
    region,
    district
FROM stg.geography;

INSERT INTO core.customers (
    customer_id,
    zip_code,
    signup_date,
    gender,
    age_group,
    acquisition_channel
)
SELECT
    customer_id,
    zip::text AS zip_code,
    signup_date,
    gender,
    age_group,
    acquisition_channel
FROM stg.customers;

INSERT INTO core.products (
    product_id,
    product_name,
    category,
    segment,
    size,
    color,
    price,
    cogs
)
SELECT
    product_id,
    product_name,
    category,
    segment,
    size,
    color,
    price,
    cogs
FROM stg.products;

INSERT INTO core.promotions (
    promo_code,
    promo_name,
    promo_type,
    discount_value,
    start_date,
    end_date,
    applicable_category,
    promo_channel,
    stackable_flag,
    min_order_value
)
SELECT
    promo_id AS promo_code,
    promo_name,
    promo_type,
    discount_value,
    start_date,
    end_date,
    applicable_category,
    promo_channel,
    (stackable_flag <> 0) AS stackable_flag,
    min_order_value
FROM stg.promotions
ORDER BY promo_id;

INSERT INTO core.orders (
    order_id,
    order_date,
    customer_id,
    shipping_zip_code,
    order_status,
    device_type,
    order_source
)
SELECT
    order_id,
    order_date,
    customer_id,
    zip::text AS shipping_zip_code,
    order_status,
    device_type,
    order_source
FROM stg.orders;

INSERT INTO core.payments (
    order_id,
    payment_method,
    payment_value,
    installments
)
SELECT
    order_id,
    payment_method,
    payment_value,
    installments
FROM stg.payments
ORDER BY order_id;

INSERT INTO core.shipments (
    order_id,
    ship_date,
    delivery_date,
    shipping_fee
)
SELECT
    order_id,
    ship_date,
    delivery_date,
    shipping_fee
FROM stg.shipments
ORDER BY order_id;

CREATE TEMP TABLE tmp_order_item_map (
    stg_order_item_id integer PRIMARY KEY,
    order_item_id integer NOT NULL
) ON COMMIT DROP;

WITH prepared AS (
    SELECT
        oi.stg_order_item_id,
        oi.order_id,
        oi.product_id,
        row_number() OVER (
            PARTITION BY oi.order_id
            ORDER BY oi.stg_order_item_id
        ) AS line_number,
        oi.quantity,
        oi.unit_price,
        oi.discount_amount
    FROM stg.order_items AS oi
),
inserted AS (
    INSERT INTO core.order_items (
        order_id,
        product_id,
        line_number,
        quantity,
        unit_price,
        discount_amount
    )
    SELECT
        order_id,
        product_id,
        line_number,
        quantity,
        unit_price,
        discount_amount
    FROM prepared
    ORDER BY order_id, line_number
    RETURNING order_item_id, order_id, line_number
)
INSERT INTO tmp_order_item_map (stg_order_item_id, order_item_id)
SELECT
    p.stg_order_item_id,
    i.order_item_id
FROM prepared AS p
JOIN inserted AS i
  ON i.order_id = p.order_id
 AND i.line_number = p.line_number;

INSERT INTO core.order_item_promotions (
    order_item_id,
    promotion_id,
    promo_sequence
)
SELECT
    m.order_item_id,
    p.promotion_id,
    x.promo_sequence
FROM (
    SELECT stg_order_item_id, promo_id AS promo_code, 1::smallint AS promo_sequence
    FROM stg.order_items
    WHERE promo_id IS NOT NULL
    UNION ALL
    SELECT stg_order_item_id, promo_id_2 AS promo_code, 2::smallint AS promo_sequence
    FROM stg.order_items
    WHERE promo_id_2 IS NOT NULL
) AS x
JOIN tmp_order_item_map AS m
  ON m.stg_order_item_id = x.stg_order_item_id
JOIN core.promotions AS p
  ON p.promo_code = x.promo_code
ORDER BY m.order_item_id, x.promo_sequence;

WITH return_candidates AS (
    SELECT
        r.stg_return_row_id,
        r.return_id,
        r.order_id,
        r.product_id,
        r.return_date,
        r.return_reason,
        r.return_quantity,
        r.refund_amount,
        m.order_item_id,
        count(*) OVER (PARTITION BY r.stg_return_row_id) AS candidate_count
    FROM stg.returns AS r
    LEFT JOIN stg.order_items AS oi
      ON oi.order_id = r.order_id
     AND oi.product_id = r.product_id
    LEFT JOIN tmp_order_item_map AS m
      ON m.stg_order_item_id = oi.stg_order_item_id
),
return_unique AS (
    SELECT DISTINCT ON (stg_return_row_id)
        stg_return_row_id,
        return_id,
        return_date,
        return_reason,
        return_quantity,
        refund_amount,
        order_item_id,
        candidate_count
    FROM return_candidates
    ORDER BY stg_return_row_id, order_item_id
)
INSERT INTO core.returns (
    return_code,
    order_item_id,
    return_date,
    return_reason,
    return_quantity,
    refund_amount
)
SELECT
    return_id AS return_code,
    order_item_id,
    return_date,
    return_reason,
    return_quantity,
    refund_amount
FROM return_unique
WHERE candidate_count = 1
  AND order_item_id IS NOT NULL
ORDER BY stg_return_row_id;

WITH return_candidates AS (
    SELECT
        r.stg_return_row_id,
        r.return_id,
        count(m.order_item_id) AS candidate_count
    FROM stg.returns AS r
    LEFT JOIN stg.order_items AS oi
      ON oi.order_id = r.order_id
     AND oi.product_id = r.product_id
    LEFT JOIN tmp_order_item_map AS m
      ON m.stg_order_item_id = oi.stg_order_item_id
    GROUP BY r.stg_return_row_id, r.return_id
)
INSERT INTO core.load_issues (
    entity_name,
    stage_table,
    stage_row_id,
    business_key,
    issue_type,
    issue_details
)
SELECT
    'returns' AS entity_name,
    'stg.returns' AS stage_table,
    stg_return_row_id,
    return_id AS business_key,
    CASE
        WHEN candidate_count = 0 THEN 'unmatched_order_item'
        ELSE 'ambiguous_order_item'
    END AS issue_type,
    CASE
        WHEN candidate_count = 0 THEN 'No order_items row matched return order_id + product_id'
        ELSE 'Multiple order_items rows matched return order_id + product_id'
    END AS issue_details
FROM return_candidates
WHERE candidate_count <> 1;

WITH review_candidates AS (
    SELECT
        r.stg_review_row_id,
        r.review_id,
        r.order_id,
        r.product_id,
        r.review_date,
        r.rating,
        r.review_title,
        m.order_item_id,
        count(*) OVER (PARTITION BY r.stg_review_row_id) AS candidate_count
    FROM stg.reviews AS r
    LEFT JOIN stg.order_items AS oi
      ON oi.order_id = r.order_id
     AND oi.product_id = r.product_id
    LEFT JOIN tmp_order_item_map AS m
      ON m.stg_order_item_id = oi.stg_order_item_id
),
review_unique AS (
    SELECT DISTINCT ON (stg_review_row_id)
        stg_review_row_id,
        review_id,
        review_date,
        rating,
        review_title,
        order_item_id,
        candidate_count
    FROM review_candidates
    ORDER BY stg_review_row_id, order_item_id
)
INSERT INTO core.reviews (
    review_code,
    order_item_id,
    review_date,
    rating,
    review_title
)
SELECT
    review_id AS review_code,
    order_item_id,
    review_date,
    rating,
    review_title
FROM review_unique
WHERE candidate_count = 1
  AND order_item_id IS NOT NULL
ORDER BY stg_review_row_id;

WITH review_candidates AS (
    SELECT
        r.stg_review_row_id,
        r.review_id,
        count(m.order_item_id) AS candidate_count
    FROM stg.reviews AS r
    LEFT JOIN stg.order_items AS oi
      ON oi.order_id = r.order_id
     AND oi.product_id = r.product_id
    LEFT JOIN tmp_order_item_map AS m
      ON m.stg_order_item_id = oi.stg_order_item_id
    GROUP BY r.stg_review_row_id, r.review_id
)
INSERT INTO core.load_issues (
    entity_name,
    stage_table,
    stage_row_id,
    business_key,
    issue_type,
    issue_details
)
SELECT
    'reviews' AS entity_name,
    'stg.reviews' AS stage_table,
    stg_review_row_id,
    review_id AS business_key,
    CASE
        WHEN candidate_count = 0 THEN 'unmatched_order_item'
        ELSE 'ambiguous_order_item'
    END AS issue_type,
    CASE
        WHEN candidate_count = 0 THEN 'No order_items row matched review order_id + product_id'
        ELSE 'Multiple order_items rows matched review order_id + product_id'
    END AS issue_details
FROM review_candidates
WHERE candidate_count <> 1;

INSERT INTO core.inventory_snapshots (
    snapshot_date,
    product_id,
    stock_on_hand,
    units_received,
    units_sold,
    stockout_days,
    days_of_supply,
    fill_rate,
    stockout_flag,
    overstock_flag,
    reorder_flag,
    sell_through_rate,
    year,
    month
)
SELECT
    snapshot_date,
    product_id,
    stock_on_hand,
    units_received,
    units_sold,
    stockout_days,
    days_of_supply,
    fill_rate,
    (stockout_flag <> 0) AS stockout_flag,
    (overstock_flag <> 0) AS overstock_flag,
    (reorder_flag <> 0) AS reorder_flag,
    sell_through_rate,
    year,
    month
FROM stg.inventory
ORDER BY snapshot_date, product_id;

COMMIT;
