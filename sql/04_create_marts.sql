CREATE TABLE IF NOT EXISTS mart.sales_daily (
    sales_date date PRIMARY KEY,
    revenue numeric(14, 2) NOT NULL,
    cogs numeric(14, 2) NOT NULL
);

CREATE TABLE IF NOT EXISTS mart.web_traffic_daily (
    traffic_date date PRIMARY KEY,
    sessions integer NOT NULL,
    unique_visitors integer NOT NULL,
    page_views integer NOT NULL,
    bounce_rate numeric(8, 4) NOT NULL,
    avg_session_duration_sec numeric(12, 2) NOT NULL,
    traffic_source text NOT NULL
);

TRUNCATE TABLE mart.sales_daily, mart.web_traffic_daily;

INSERT INTO mart.sales_daily (sales_date, revenue, cogs)
SELECT
    sales_date,
    revenue,
    cogs
FROM stg.sales
ORDER BY sales_date;

INSERT INTO mart.web_traffic_daily (
    traffic_date,
    sessions,
    unique_visitors,
    page_views,
    bounce_rate,
    avg_session_duration_sec,
    traffic_source
)
SELECT
    traffic_date,
    sessions,
    unique_visitors,
    page_views,
    bounce_rate,
    avg_session_duration_sec,
    traffic_source
FROM stg.web_traffic
ORDER BY traffic_date;
