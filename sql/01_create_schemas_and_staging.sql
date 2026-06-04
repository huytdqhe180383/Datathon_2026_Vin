CREATE SCHEMA IF NOT EXISTS stg;
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS mart;

CREATE TABLE IF NOT EXISTS stg.customers (
    customer_id integer PRIMARY KEY,
    zip integer NOT NULL,
    city text NOT NULL,
    signup_date date NOT NULL,
    gender text NOT NULL,
    age_group text NOT NULL,
    acquisition_channel text NOT NULL
);

CREATE TABLE IF NOT EXISTS stg.geography (
    zip integer PRIMARY KEY,
    city text NOT NULL,
    region text NOT NULL,
    district text NOT NULL
);

CREATE TABLE IF NOT EXISTS stg.inventory (
    snapshot_date date NOT NULL,
    product_id integer NOT NULL,
    stock_on_hand integer NOT NULL,
    units_received integer NOT NULL,
    units_sold integer NOT NULL,
    stockout_days integer NOT NULL,
    days_of_supply numeric(12, 4) NOT NULL,
    fill_rate numeric(8, 4) NOT NULL,
    stockout_flag integer NOT NULL,
    overstock_flag integer NOT NULL,
    reorder_flag integer NOT NULL,
    sell_through_rate numeric(12, 4) NOT NULL,
    product_name text NOT NULL,
    category text NOT NULL,
    segment text NOT NULL,
    year integer NOT NULL,
    month integer NOT NULL
);

CREATE TABLE IF NOT EXISTS stg.orders (
    order_id integer PRIMARY KEY,
    order_date date NOT NULL,
    customer_id integer NOT NULL,
    zip integer NOT NULL,
    order_status text NOT NULL,
    payment_method text NOT NULL,
    device_type text NOT NULL,
    order_source text NOT NULL
);

CREATE TABLE IF NOT EXISTS stg.order_items (
    stg_order_item_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id integer NOT NULL,
    product_id integer NOT NULL,
    quantity integer NOT NULL,
    unit_price numeric(14, 2) NOT NULL,
    discount_amount numeric(14, 2) NOT NULL,
    promo_id text NULL,
    promo_id_2 text NULL
);

CREATE TABLE IF NOT EXISTS stg.payments (
    order_id integer PRIMARY KEY,
    payment_method text NOT NULL,
    payment_value numeric(14, 2) NOT NULL,
    installments integer NOT NULL
);

CREATE TABLE IF NOT EXISTS stg.products (
    product_id integer PRIMARY KEY,
    product_name text NOT NULL,
    category text NOT NULL,
    segment text NOT NULL,
    size text NOT NULL,
    color text NOT NULL,
    price numeric(14, 2) NOT NULL,
    cogs numeric(14, 2) NOT NULL
);

CREATE TABLE IF NOT EXISTS stg.promotions (
    promo_id text PRIMARY KEY,
    promo_name text NOT NULL,
    promo_type text NOT NULL,
    discount_value numeric(14, 2) NOT NULL,
    start_date date NOT NULL,
    end_date date NOT NULL,
    applicable_category text NULL,
    promo_channel text NOT NULL,
    stackable_flag integer NOT NULL,
    min_order_value numeric(14, 2) NOT NULL
);

CREATE TABLE IF NOT EXISTS stg.returns (
    stg_return_row_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    return_id text NOT NULL,
    order_id integer NOT NULL,
    product_id integer NOT NULL,
    return_date date NOT NULL,
    return_reason text NOT NULL,
    return_quantity integer NOT NULL,
    refund_amount numeric(14, 2) NOT NULL
);

CREATE TABLE IF NOT EXISTS stg.reviews (
    stg_review_row_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    review_id text NOT NULL,
    order_id integer NOT NULL,
    product_id integer NOT NULL,
    customer_id integer NOT NULL,
    review_date date NOT NULL,
    rating integer NOT NULL,
    review_title text NOT NULL
);

CREATE TABLE IF NOT EXISTS stg.sales (
    sales_date date PRIMARY KEY,
    revenue numeric(14, 2) NOT NULL,
    cogs numeric(14, 2) NOT NULL
);

CREATE TABLE IF NOT EXISTS stg.shipments (
    order_id integer PRIMARY KEY,
    ship_date date NOT NULL,
    delivery_date date NOT NULL,
    shipping_fee numeric(14, 2) NOT NULL
);

CREATE TABLE IF NOT EXISTS stg.web_traffic (
    traffic_date date PRIMARY KEY,
    sessions integer NOT NULL,
    unique_visitors integer NOT NULL,
    page_views integer NOT NULL,
    bounce_rate numeric(8, 4) NOT NULL,
    avg_session_duration_sec numeric(12, 2) NOT NULL,
    traffic_source text NOT NULL
);
