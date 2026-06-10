# PostgreSQL Local Setup

This workspace now contains a normalized PostgreSQL setup for the ecommerce CSV domain using three layers:

- `stg`: raw landing tables close to CSV shape
- `core`: normalized relational model
- `mart`: reporting-friendly daily aggregates

## What Changed

- `returns` now references `core.order_items.order_item_id`
- `reviews` now references `core.order_items.order_item_id`
- `core.reviews` intentionally does **not** keep `customer_id`
- stacked promotions are normalized into `core.order_item_promotions`
- source business codes like `PROMO-0001`, `RET-000001`, `REV-0000001` remain as unique text columns

## Files

- [01_create_schemas_and_staging.sql](E:\AI Thuc Chien\VSF\datathon_2026\sql\01_create_schemas_and_staging.sql)
- [02_create_core_tables.sql](E:\AI Thuc Chien\VSF\datathon_2026\sql\02_create_core_tables.sql)
- [03_transform_staging_to_core.sql](E:\AI Thuc Chien\VSF\datathon_2026\sql\03_transform_staging_to_core.sql)
- [04_create_marts.sql](E:\AI Thuc Chien\VSF\datathon_2026\sql\04_create_marts.sql)
- [05_verify_schema.sql](E:\AI Thuc Chien\VSF\datathon_2026\sql\05_verify_schema.sql)
- [setup_postgres_local.ps1](E:\AI Thuc Chien\VSF\datathon_2026\scripts\setup_postgres_local.ps1)

## Existing PostgreSQL Service

The machine already has PostgreSQL 18 installed at:

```text
C:\Program Files\PostgreSQL\18\bin
```

The current service is configured with `scram-sha-256`, so the runner needs a password when you target the existing instance.

Example:

```powershell
$env:PGPASSWORD = 'your-postgres-password'
powershell -ExecutionPolicy Bypass -File 'E:\AI Thuc Chien\VSF\datathon_2026\scripts\setup_postgres_local.ps1'
```

## Raw Data Location

The runner expects CSV files in:

```text
E:\AI Thuc Chien\VSF\datathon_2026\data\raw
```

If you store them elsewhere:

```powershell
$env:PGPASSWORD = 'your-postgres-password'
powershell -ExecutionPolicy Bypass -File 'E:\AI Thuc Chien\VSF\datathon_2026\scripts\setup_postgres_local.ps1' -RawDir 'D:\path\to\raw'
```

## Safe Smoke Test Mode

To validate the DDL without touching the existing password-protected service, use a temporary trust-based cluster on another port:

```powershell
& 'C:\Program Files\PostgreSQL\18\bin\initdb.exe' -D 'E:\AI Thuc Chien\VSF\datathon_2026\.tmp_pgdata' -U postgres -A trust
& 'C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe' -D 'E:\AI Thuc Chien\VSF\datathon_2026\.tmp_pgdata' -o "-p 55432" -l 'E:\AI Thuc Chien\VSF\datathon_2026\logs\postgres\tmp_pg.log' start
powershell -ExecutionPolicy Bypass -File 'E:\AI Thuc Chien\VSF\datathon_2026\scripts\setup_postgres_local.ps1' -DbName datathon_2026 -DbUser postgres -DbHost 127.0.0.1 -Port 55432 -SkipLoad
& 'C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe' -D 'E:\AI Thuc Chien\VSF\datathon_2026\.tmp_pgdata' stop
```

## Ambiguous Line-Level Mapping

`returns.csv` and `reviews.csv` only provide `order_id + product_id`. If one order contains the same product in multiple lines, there may be more than one possible `order_item_id`.

The transform handles this defensively:

- unique match: insert into `core.returns` or `core.reviews`
- zero matches: write a row to `core.load_issues`
- multiple matches: write a row to `core.load_issues`

That keeps the normalized model correct without silently assigning the wrong line item.
