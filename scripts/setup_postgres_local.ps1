param(
    [string]$DbName = "datathon_2026",
    [string]$DbUser = "postgres",
    [string]$DbHost = "127.0.0.1",
    [int]$Port = 5432,
    [string]$AdminDb = "postgres",
    [string]$PgBin = "C:\Program Files\PostgreSQL\18\bin",
    [string]$RawDir = "E:\AI Thuc Chien\VSF\datathon_2026\data\raw",
    [switch]$SkipLoad
)

$ErrorActionPreference = "Stop"

function Get-PsqlPath {
    param([string]$BinaryRoot, [string]$Name)
    $path = Join-Path $BinaryRoot $Name
    if (-not (Test-Path $path)) {
        throw "Missing PostgreSQL binary: $path"
    }
    return $path
}

function Invoke-PsqlCommand {
    param(
        [string]$Database,
        [string]$Command
    )

    $psql = Get-PsqlPath -BinaryRoot $PgBin -Name "psql.exe"
    & $psql -h $DbHost -p $Port -U $DbUser -d $Database -v ON_ERROR_STOP=1 -c $Command
    if ($LASTEXITCODE -ne 0) {
        throw "psql command failed: $Command"
    }
}

function Invoke-PsqlFile {
    param([string]$Database, [string]$FilePath)

    $psql = Get-PsqlPath -BinaryRoot $PgBin -Name "psql.exe"
    & $psql -h $DbHost -p $Port -U $DbUser -d $Database -v ON_ERROR_STOP=1 -f $FilePath
    if ($LASTEXITCODE -ne 0) {
        throw "psql file failed: $FilePath"
    }
}

function Get-DbExists {
    $psql = Get-PsqlPath -BinaryRoot $PgBin -Name "psql.exe"
    $query = "select 1 from pg_database where datname = '$DbName';"
    $result = & $psql -h $DbHost -p $Port -U $DbUser -d $AdminDb -t -A -v ON_ERROR_STOP=1 -c $query
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to query database list from $AdminDb"
    }
    return ($result -match '^1$')
}

function Ensure-Database {
    if (-not (Get-DbExists)) {
        Invoke-PsqlCommand -Database $AdminDb -Command "create database $DbName;"
    }
}

function Reset-Staging {
    $truncate = @"
TRUNCATE TABLE
    stg.order_items,
    stg.returns,
    stg.reviews,
    stg.inventory,
    stg.payments,
    stg.shipments,
    stg.orders,
    stg.customers,
    stg.geography,
    stg.products,
    stg.promotions,
    stg.sales,
    stg.web_traffic
RESTART IDENTITY CASCADE;
"@
    Invoke-PsqlCommand -Database $DbName -Command $truncate
}

function Import-Csv {
    param(
        [string]$Table,
        [string]$Columns,
        [string]$FileName
    )

    $psql = Get-PsqlPath -BinaryRoot $PgBin -Name "psql.exe"
    $csvPath = Join-Path $RawDir $FileName
    if (-not (Test-Path $csvPath)) {
        throw "Missing CSV file: $csvPath"
    }

    $normalizedPath = $csvPath.Replace("\", "/")
    $copyCommand = "\copy $Table ($Columns) from '$normalizedPath' with (format csv, header true, null '')"
    & $psql -h $DbHost -p $Port -U $DbUser -d $DbName -v ON_ERROR_STOP=1 -c $copyCommand
    if ($LASTEXITCODE -ne 0) {
        throw "CSV import failed for $FileName"
    }
}

$root = Split-Path -Parent $PSScriptRoot
$sqlDir = Join-Path $root "sql"

Write-Host "Ensuring database $DbName exists on ${DbHost}:$Port"
Ensure-Database

Invoke-PsqlFile -Database $DbName -FilePath (Join-Path $sqlDir "01_create_schemas_and_staging.sql")

if (-not $SkipLoad) {
    Reset-Staging

    Import-Csv -Table "stg.customers" -Columns "customer_id, zip, city, signup_date, gender, age_group, acquisition_channel" -FileName "customers.csv"
    Import-Csv -Table "stg.geography" -Columns "zip, city, region, district" -FileName "geography.csv"
    Import-Csv -Table "stg.inventory" -Columns "snapshot_date, product_id, stock_on_hand, units_received, units_sold, stockout_days, days_of_supply, fill_rate, stockout_flag, overstock_flag, reorder_flag, sell_through_rate, product_name, category, segment, year, month" -FileName "inventory.csv"
    Import-Csv -Table "stg.orders" -Columns "order_id, order_date, customer_id, zip, order_status, payment_method, device_type, order_source" -FileName "orders.csv"
    Import-Csv -Table "stg.order_items" -Columns "order_id, product_id, quantity, unit_price, discount_amount, promo_id, promo_id_2" -FileName "order_items.csv"
    Import-Csv -Table "stg.payments" -Columns "order_id, payment_method, payment_value, installments" -FileName "payments.csv"
    Import-Csv -Table "stg.products" -Columns "product_id, product_name, category, segment, size, color, price, cogs" -FileName "products.csv"
    Import-Csv -Table "stg.promotions" -Columns "promo_id, promo_name, promo_type, discount_value, start_date, end_date, applicable_category, promo_channel, stackable_flag, min_order_value" -FileName "promotions.csv"
    Import-Csv -Table "stg.returns" -Columns "return_id, order_id, product_id, return_date, return_reason, return_quantity, refund_amount" -FileName "returns.csv"
    Import-Csv -Table "stg.reviews" -Columns "review_id, order_id, product_id, customer_id, review_date, rating, review_title" -FileName "reviews.csv"
    Import-Csv -Table "stg.sales" -Columns "sales_date, revenue, cogs" -FileName "sales.csv"
    Import-Csv -Table "stg.shipments" -Columns "order_id, ship_date, delivery_date, shipping_fee" -FileName "shipments.csv"
    Import-Csv -Table "stg.web_traffic" -Columns "traffic_date, sessions, unique_visitors, page_views, bounce_rate, avg_session_duration_sec, traffic_source" -FileName "web_traffic.csv"
}

Invoke-PsqlFile -Database $DbName -FilePath (Join-Path $sqlDir "02_create_core_tables.sql")
Invoke-PsqlFile -Database $DbName -FilePath (Join-Path $sqlDir "03_transform_staging_to_core.sql")
Invoke-PsqlFile -Database $DbName -FilePath (Join-Path $sqlDir "04_create_marts.sql")
Invoke-PsqlFile -Database $DbName -FilePath (Join-Path $sqlDir "05_verify_schema.sql")

Write-Host "PostgreSQL setup completed for database $DbName"
