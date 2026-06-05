CREATE TABLE IF NOT EXISTS core.geography (
    zip_code varchar(12) PRIMARY KEY,
    city text NOT NULL,
    region text NOT NULL,
    district text NOT NULL
);

CREATE TABLE IF NOT EXISTS core.customers (
    customer_id integer PRIMARY KEY,
    zip_code varchar(12) NOT NULL REFERENCES core.geography (zip_code),
    signup_date date NOT NULL,
    gender text NOT NULL,
    age_group text NOT NULL,
    acquisition_channel text NOT NULL
);

CREATE TABLE IF NOT EXISTS core.products (
    product_id integer PRIMARY KEY,
    product_name text NOT NULL,
    category text NOT NULL,
    segment text NOT NULL,
    size text NOT NULL,
    color text NOT NULL,
    price numeric(14, 2) NOT NULL,
    cogs numeric(14, 2) NOT NULL
);

CREATE TABLE IF NOT EXISTS core.promotions (
    promotion_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    promo_code varchar(20) NOT NULL UNIQUE,
    promo_name text NOT NULL UNIQUE,
    promo_type text NOT NULL,
    discount_value numeric(14, 2) NOT NULL,
    start_date date NOT NULL,
    end_date date NOT NULL,
    applicable_category text NULL,
    promo_channel text NOT NULL,
    stackable_flag boolean NOT NULL,
    min_order_value numeric(14, 2) NOT NULL
);

CREATE TABLE IF NOT EXISTS core.orders (
    order_id integer PRIMARY KEY,
    order_date date NOT NULL,
    customer_id integer NOT NULL REFERENCES core.customers (customer_id),
    shipping_zip_code varchar(12) NOT NULL REFERENCES core.geography (zip_code),
    order_status text NOT NULL,
    device_type text NOT NULL,
    order_source text NOT NULL
);

CREATE TABLE IF NOT EXISTS core.order_items (
    order_item_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id integer NOT NULL REFERENCES core.orders (order_id) ON DELETE CASCADE,
    product_id integer NOT NULL REFERENCES core.products (product_id),
    line_number integer NOT NULL,
    quantity integer NOT NULL,
    unit_price numeric(14, 2) NOT NULL,
    discount_amount numeric(14, 2) NOT NULL,
    UNIQUE (order_id, line_number)
);

CREATE TABLE IF NOT EXISTS core.order_item_promotions (
    order_item_id integer NOT NULL REFERENCES core.order_items (order_item_id) ON DELETE CASCADE,
    promotion_id integer NOT NULL REFERENCES core.promotions (promotion_id),
    promo_sequence smallint NOT NULL,
    PRIMARY KEY (order_item_id, promo_sequence),
    UNIQUE (order_item_id, promotion_id)
);

CREATE TABLE IF NOT EXISTS core.payments (
    payment_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id integer NOT NULL UNIQUE REFERENCES core.orders (order_id) ON DELETE CASCADE,
    payment_method text NOT NULL,
    payment_value numeric(14, 2) NOT NULL,
    installments integer NOT NULL
);

CREATE TABLE IF NOT EXISTS core.shipments (
    shipment_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id integer NOT NULL UNIQUE REFERENCES core.orders (order_id) ON DELETE CASCADE,
    ship_date date NOT NULL,
    delivery_date date NOT NULL,
    shipping_fee numeric(14, 2) NOT NULL
);

CREATE TABLE IF NOT EXISTS core.returns (
    return_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    return_code varchar(20) NOT NULL UNIQUE,
    order_item_id integer NOT NULL REFERENCES core.order_items (order_item_id),
    return_date date NOT NULL,
    return_reason text NOT NULL,
    return_quantity integer NOT NULL,
    refund_amount numeric(14, 2) NOT NULL
);

CREATE TABLE IF NOT EXISTS core.reviews (
    review_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    review_code varchar(20) NOT NULL UNIQUE,
    order_item_id integer NOT NULL REFERENCES core.order_items (order_item_id),
    review_date date NOT NULL,
    rating integer NOT NULL,
    review_title text NOT NULL
);

CREATE TABLE IF NOT EXISTS core.inventory_snapshots (
    snapshot_date date NOT NULL,
    product_id integer NOT NULL REFERENCES core.products (product_id),
    stock_on_hand integer NOT NULL,
    units_received integer NOT NULL,
    units_sold integer NOT NULL,
    stockout_days integer NOT NULL,
    days_of_supply numeric(12, 4) NOT NULL,
    fill_rate numeric(8, 4) NOT NULL,
    stockout_flag boolean NOT NULL,
    overstock_flag boolean NOT NULL,
    reorder_flag boolean NOT NULL,
    sell_through_rate numeric(12, 4) NOT NULL,
    year integer NOT NULL,
    month integer NOT NULL,
    PRIMARY KEY (snapshot_date, product_id)
);

CREATE TABLE IF NOT EXISTS core.load_issues (
    load_issue_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    entity_name text NOT NULL,
    stage_table text NOT NULL,
    stage_row_id integer NULL,
    business_key text NULL,
    issue_type text NOT NULL,
    issue_details text NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_core_customers_zip_code
    ON core.customers (zip_code);

CREATE INDEX IF NOT EXISTS idx_core_orders_customer_id
    ON core.orders (customer_id);

CREATE INDEX IF NOT EXISTS idx_core_orders_shipping_zip_code
    ON core.orders (shipping_zip_code);

CREATE INDEX IF NOT EXISTS idx_core_orders_order_date
    ON core.orders (order_date);

CREATE INDEX IF NOT EXISTS idx_core_order_items_order_id
    ON core.order_items (order_id);

CREATE INDEX IF NOT EXISTS idx_core_order_items_product_id
    ON core.order_items (product_id);

CREATE INDEX IF NOT EXISTS idx_core_payments_order_id
    ON core.payments (order_id);

CREATE INDEX IF NOT EXISTS idx_core_shipments_order_id
    ON core.shipments (order_id);

CREATE INDEX IF NOT EXISTS idx_core_shipments_ship_date
    ON core.shipments (ship_date);

CREATE INDEX IF NOT EXISTS idx_core_returns_order_item_id
    ON core.returns (order_item_id);

CREATE INDEX IF NOT EXISTS idx_core_returns_return_date
    ON core.returns (return_date);

CREATE INDEX IF NOT EXISTS idx_core_reviews_order_item_id
    ON core.reviews (order_item_id);

CREATE INDEX IF NOT EXISTS idx_core_reviews_review_date
    ON core.reviews (review_date);

CREATE INDEX IF NOT EXISTS idx_core_inventory_product_id_snapshot_date
    ON core.inventory_snapshots (product_id, snapshot_date);

CREATE INDEX IF NOT EXISTS idx_core_load_issues_entity_name
    ON core.load_issues (entity_name);
