# PostgreSQL Local Schema Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local PostgreSQL setup for the ecommerce CSV domain using `staging`, `core`, and `mart` schemas, with normalized line-level relationships for returns and reviews.

**Architecture:** Raw CSVs load into `stg` tables that stay close to source shape. Deterministic transforms populate normalized `core` tables, including synthetic `order_item_id` and a bridge table for stacked promotions. Reporting-only daily datasets land in `mart`, while schema verification is handled by a dedicated SQL smoke test and a PowerShell runner.

**Tech Stack:** PostgreSQL 18, SQL DDL/DML, PowerShell, psql client

---

### Task 1: Scaffold Schema And Verification Files

**Files:**
- Create: `E:\AI Thuc Chien\VSF\datathon_2026\sql\05_verify_schema.sql`
- Create: `E:\AI Thuc Chien\VSF\datathon_2026\docs\postgres-local-setup.md`

- [ ] **Step 1: Write the failing schema verification first**

Create `sql/05_verify_schema.sql` with `DO` blocks that raise exceptions when required schemas and tables do not exist.

- [ ] **Step 2: Run verification against an empty temporary database to confirm RED**

Run a temporary PostgreSQL cluster and execute:

```powershell
& 'C:\Program Files\PostgreSQL\18\bin\psql.exe' -h 127.0.0.1 -p 55432 -U postgres -d datathon_2026 -v ON_ERROR_STOP=1 -f 'E:\AI Thuc Chien\VSF\datathon_2026\sql\05_verify_schema.sql'
```

Expected: FAIL with a missing schema/table exception before any DDL is applied.

- [ ] **Step 3: Document local setup expectations**

Write `docs/postgres-local-setup.md` describing:
- required PostgreSQL binary path
- `PGPASSWORD` usage for the existing service
- optional temporary trust-based cluster used only for smoke testing
- expected raw data location `E:\AI Thuc Chien\VSF\datathon_2026\data\raw`

### Task 2: Create Staging And Core DDL

**Files:**
- Create: `E:\AI Thuc Chien\VSF\datathon_2026\sql\01_create_schemas_and_staging.sql`
- Create: `E:\AI Thuc Chien\VSF\datathon_2026\sql\02_create_core_tables.sql`

- [ ] **Step 1: Create schemas and raw landing tables**

Add `stg`, `core`, and `mart` schemas plus `stg_*` tables with source-aligned columns and deterministic identity row ids for line-grain tables.

- [ ] **Step 2: Create normalized core tables**

Add `core` tables for:
- geography
- customers
- products
- promotions
- orders
- order_items
- order_item_promotions
- payments
- shipments
- returns
- reviews
- inventory_snapshots
- load_issues

- [ ] **Step 3: Re-run verification to confirm it still fails before all required objects exist**

Run:

```powershell
& 'C:\Program Files\PostgreSQL\18\bin\psql.exe' -h 127.0.0.1 -p 55432 -U postgres -d datathon_2026 -v ON_ERROR_STOP=1 -f 'E:\AI Thuc Chien\VSF\datathon_2026\sql\01_create_schemas_and_staging.sql'
& 'C:\Program Files\PostgreSQL\18\bin\psql.exe' -h 127.0.0.1 -p 55432 -U postgres -d datathon_2026 -v ON_ERROR_STOP=1 -f 'E:\AI Thuc Chien\VSF\datathon_2026\sql\05_verify_schema.sql'
```

Expected: FAIL because `core` tables are not all present yet.

### Task 3: Create Transforms, Marts, And Runner

**Files:**
- Create: `E:\AI Thuc Chien\VSF\datathon_2026\sql\03_transform_staging_to_core.sql`
- Create: `E:\AI Thuc Chien\VSF\datathon_2026\sql\04_create_marts.sql`
- Create: `E:\AI Thuc Chien\VSF\datathon_2026\scripts\setup_postgres_local.ps1`

- [ ] **Step 1: Write minimal deterministic transforms**

Implement transforms that:
- preserve source business codes as unique text columns
- generate `order_item_id`
- split promo columns into `order_item_promotions`
- map returns and reviews to `order_item_id`
- write ambiguous or unmatched rows to `core.load_issues`

- [ ] **Step 2: Create reporting tables in `mart`**

Add daily `sales_daily` and `web_traffic_daily` tables sourced from staging.

- [ ] **Step 3: Write PowerShell runner**

Add a runner that:
- targets either the existing local PostgreSQL service or a temporary smoke-test cluster
- creates the database if missing
- executes DDL in order
- optionally loads CSVs from `E:\AI Thuc Chien\VSF\datathon_2026\data\raw`
- runs verification SQL at the end

### Task 4: Verify Green

**Files:**
- Test: `E:\AI Thuc Chien\VSF\datathon_2026\sql\05_verify_schema.sql`

- [ ] **Step 1: Start isolated temporary PostgreSQL**

Run:

```powershell
& 'C:\Program Files\PostgreSQL\18\bin\initdb.exe' -D 'E:\AI Thuc Chien\VSF\datathon_2026\.tmp_pgdata' -U postgres -A trust
& 'C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe' -D 'E:\AI Thuc Chien\VSF\datathon_2026\.tmp_pgdata' -o "-p 55432" -l 'E:\AI Thuc Chien\VSF\datathon_2026\logs\postgres\tmp_pg.log' start
```

- [ ] **Step 2: Execute the setup runner in smoke-test mode**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File 'E:\AI Thuc Chien\VSF\datathon_2026\scripts\setup_postgres_local.ps1' -DbName datathon_2026 -DbUser postgres -Port 55432 -DbHost 127.0.0.1 -SkipLoad
```

Expected: PASS, with schemas/tables created and verification SQL succeeding.

- [ ] **Step 3: Stop the temporary server**

Run:

```powershell
& 'C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe' -D 'E:\AI Thuc Chien\VSF\datathon_2026\.tmp_pgdata' stop
```

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/plans/2026-06-01-postgres-local-schema.md docs/postgres-local-setup.md sql scripts
git commit -m "feat: add local postgres ecommerce schema setup"
```
