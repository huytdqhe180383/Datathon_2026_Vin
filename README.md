# Datathon 2026

This repository contains two related workstreams for the Datathon 2026 ecommerce dataset:

- a normalized local PostgreSQL schema built from the raw CSV data
- a SQL question-answering agent with a simple Gradio UI

The SQL agent now uses an LLM to help generate SQL and compose grounded answers. Deterministic query patterns remain as fallback behavior for known phase-1 questions, and SQL validation still runs before any query reaches PostgreSQL.

## Quick Start: SQL Agent UI

Prerequisites:

- Python available as `python`
- PostgreSQL running locally
- database `datathon_2026` loaded with the `stg`, `core`, and `mart` schemas
- repo-root `.env` containing PostgreSQL and LLM connection values

Example `.env`:

```text
PGHOST=127.0.0.1
PGPORT=5432
PGDATABASE=datathon_2026
PGUSER=postgres
PGPASSWORD=your-password

OPENAI_API_KEY=your-api-key
OPENAI_API_BASE=https://api.openai.com/v1
SQL_AGENT_LLM_MODEL=gpt-4o-mini
SQL_AGENT_USE_LLM=true
```

`OPENAI_API_BASE` can point to any OpenAI-compatible endpoint. If `SQL_AGENT_LLM_MODEL` is not set, the agent falls back to `OPENAI_MODEL`, then `PANDASAI_MODEL`, then `gpt-4o-mini`.

Install the agent dependencies once:

```powershell
python -m pip install -r requirements-sql-rag-agent.txt
```

Start or restart the UI and open it in the browser:

```powershell
.\scripts\restart_sql_rag_agent_ui.cmd
```

The UI runs at:

```text
http://127.0.0.1:7860
```

Use another port if needed:

```powershell
.\scripts\restart_sql_rag_agent_ui.cmd 7861
```

The restart script stops any existing listener on the selected port, starts `python -m sql_rag_agent.ui`, waits briefly, and opens the UI URL. Server logs are written to:

```text
.tmp_sql_rag_agent_ui.out.log
.tmp_sql_rag_agent_ui.err.log
```

Agent trace logs are written to:

```text
logs/agent_traces/*.jsonl
```

Trace records include the question, selected tables, LLM SQL candidate, SQL validation result, execution result, LLM answer output, final answer, and errors. Secrets such as `PGPASSWORD` and `OPENAI_API_KEY` are not logged.

## Supported Questions

The LLM can attempt broader ecommerce questions using the selected schema context. These deterministic patterns are also supported as fallback:

- `How many customers are there?`
- `How many customers refunded in 17/7/2017 - 17/8/2017?`
- `Which product had the highest revenue last quarter?`

Unsupported prompts such as `hello` return a clear unsupported-question message instead of executing a misleading fallback query. Unsafe SQL is blocked before execution.

## SQL Agent Architecture

Source package:

```text
src/sql_rag_agent/
```

Main files:

- `ui.py`: Gradio UI with one question box and one answer box.
- `graph.py`: LangGraph controller that wires the six phase-1 nodes.
- `state.py`: shared `SQLAgentState` object passed between nodes.
- `config.py`: reads PostgreSQL settings from environment variables and repo-root `.env`.
- `llm.py`: OpenAI-compatible LLM provider used for SQL generation and answer composition.
- `tracing.py`: JSONL trace writer for agent runs.
- `tools/mcp_postgres.py`: MCP-style PostgreSQL wrapper for schema inspection and read-only query execution.
- `tools/sql_validator.py`: SQL safety checks before execution.

Phase-1 graph:

```text
understand_question
  -> inspect_schema
  -> generate_sql
  -> validate_sql
  -> execute_sql
  -> compose_answer
```

Node responsibilities:

- `understand_question.py`: classifies the question and flags broad requirements such as aggregation, joins, and date filters.
- `inspect_schema.py`: selects relevant tables and fetches schema metadata through the PostgreSQL wrapper.
- `generate_sql.py`: asks the LLM for one SQL candidate, then falls back to deterministic patterns when needed.
- `validate_sql.py`: rejects unsafe SQL and unsupported query shapes before execution.
- `execute_sql.py`: executes only validated SQL through PostgreSQL.
- `compose_answer.py`: asks the LLM to compose a grounded answer from result rows, then falls back to a deterministic answer if the LLM is unavailable.

## PostgreSQL Architecture

The database is split into three schemas:

- `stg`: raw landing tables close to CSV shape for auditability and reloads.
- `core`: normalized relational model for joins and analytics.
- `mart`: reporting-friendly aggregate tables.

Important SQL setup files:

```text
sql/01_create_schemas_and_staging.sql
sql/02_create_core_tables.sql
sql/03_transform_staging_to_core.sql
sql/04_create_marts.sql
sql/05_verify_schema.sql
scripts/setup_postgres_local.ps1
```

More detail:

```text
docs/postgres-local-setup.md
docs/schema-postgres-import-report.md
docs/Pipeline plan.md
```

## Load or Rebuild PostgreSQL

The setup runner expects raw CSV files in:

```text
data/raw
```

Run the loader:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_postgres_local.ps1
```

If your PostgreSQL service requires a password, either put `PGPASSWORD` in `.env` for the Python agent or set it in the shell for the PowerShell loader:

```powershell
$env:PGPASSWORD = 'your-password'
powershell -ExecutionPolicy Bypass -File .\scripts\setup_postgres_local.ps1
```

## Tests

Run the current agent and data-quality tests:

```powershell
pytest tests/test_sql_rag_agent_phase1.py tests/test_data_quality_pipeline.py -q
```

The SQL agent tests use a fake PostgreSQL tool for graph behavior and do not require a live database. Direct UI and manual question-answer checks do require the local PostgreSQL service.

## Current Limitations

- Phase 1 does not use LlamaIndex retrieval yet.
- Only one SQL candidate is generated.
- There is no SQL repair loop yet.
- The UI intentionally has no trace/log panel.
- Trace logs are file-based JSONL only.

These are planned later phases in `docs/Pipeline plan.md`.
