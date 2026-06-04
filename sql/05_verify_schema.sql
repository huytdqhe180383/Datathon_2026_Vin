DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'stg') THEN
        RAISE EXCEPTION 'Missing schema: stg';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'core') THEN
        RAISE EXCEPTION 'Missing schema: core';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'mart') THEN
        RAISE EXCEPTION 'Missing schema: mart';
    END IF;
END
$$;

DO $$
DECLARE
    required_tables text[] := ARRAY[
        'stg.customers',
        'stg.geography',
        'stg.inventory',
        'stg.orders',
        'stg.order_items',
        'stg.payments',
        'stg.products',
        'stg.promotions',
        'stg.returns',
        'stg.reviews',
        'stg.sales',
        'stg.shipments',
        'stg.web_traffic',
        'core.geography',
        'core.customers',
        'core.products',
        'core.promotions',
        'core.orders',
        'core.order_items',
        'core.order_item_promotions',
        'core.payments',
        'core.shipments',
        'core.returns',
        'core.reviews',
        'core.inventory_snapshots',
        'core.load_issues',
        'mart.sales_daily',
        'mart.web_traffic_daily'
    ];
    table_name text;
BEGIN
    FOREACH table_name IN ARRAY required_tables LOOP
        IF to_regclass(table_name) IS NULL THEN
            RAISE EXCEPTION 'Missing table: %', table_name;
        END IF;
    END LOOP;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'core'
          AND table_name = 'returns'
          AND column_name = 'order_item_id'
    ) THEN
        RAISE EXCEPTION 'core.returns must contain order_item_id';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'core'
          AND table_name = 'reviews'
          AND column_name = 'customer_id'
    ) THEN
        RAISE EXCEPTION 'core.reviews must not contain customer_id';
    END IF;
END
$$;
