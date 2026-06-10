# WORKLOG

This file tracks the major work completed for the Datathon 2026 repository.

Last updated: 2026-06-09

## How To Use

- Add new entries at the top of the timeline.
- Keep entries outcome-focused.
- Include relevant commit hashes, docs, or implementation notes when helpful.

## Timeline

### 2026-06-08 To 2026-06-09 - Evaluation, Context Contracts, And Phase 3 Ranking

- Rechecked the SQL-RAG vs PandasAI benchmark in [results/summary.md](/E:/AI%20Thuc%20Chien/VSF/datathon_2026/results/summary.md): strict ordered SQL-RAG accuracy was `18/50 = 36%`, row-order-adjusted SQL-RAG accuracy was `24/50 = 48%`, and PandasAI was `41/50 = 82%`.
- Reviewed the 26 remaining adjusted mismatches in [results/mismatch_root_cause_summary.md](/E:/AI%20Thuc%20Chien/VSF/datathon_2026/results/mismatch_root_cause_summary.md). Main causes were semantic metric drift, missing output-shape contracts, row-limit truncation, categorical value casing, and promo/return-definition ambiguity.
- Reran the 26 adjusted mismatches with the stronger model and logged generated SQL alongside reference SQL in [results/mismatch_rerun_gpt-5.4-high_20260609T034001Z_merged.csv](/E:/AI%20Thuc%20Chien/VSF/datathon_2026/results/mismatch_rerun_gpt-5.4-high_20260609T034001Z_merged.csv). The rerun corrected `1/26` mismatches: `table-Q4`.
- Created rerun comparison folders with the same structure as the baseline comparisons:
  [results/table_output_mismatch_rerun_gpt-5.4-high_20260609T034001Z](/E:/AI%20Thuc%20Chien/VSF/datathon_2026/results/table_output_mismatch_rerun_gpt-5.4-high_20260609T034001Z)
  and [results/value_output_mismatch_rerun_gpt-5.4-high_20260609T034001Z](/E:/AI%20Thuc%20Chien/VSF/datathon_2026/results/value_output_mismatch_rerun_gpt-5.4-high_20260609T034001Z), each with `summary.json`, `summary.md`, `comparison.json`, `agent_output.csv`, and `reference_sql.csv` files.
- Added typed benchmark context documents for metric definitions, output contracts, schema translations, and few-shot examples in [docs/schema_context](/E:/AI%20Thuc%20Chien/VSF/datathon_2026/docs/schema_context).
- Implemented Phase 3 multi-candidate SQL generation and ranking. The new ranking stage scores candidates by execution success, retrieved metric-definition alignment, output-contract match, and SQL simplicity before answer composition.
- Increased table-question SQL execution row limits so larger benchmark table outputs are not capped at 100 rows.
- Added regression tests for typed context retrieval, Phase 3 ranking, table row limits, mismatch selection, rerun SQL logging, and rerun summary integrity.

### 2026-06-04 To 2026-06-05 - UI And Developer Workflow Improvements

- Added the table selector dropdown so users can explicitly choose which tables the agent is allowed to inspect and query.
- Improved the UI restart flow to handle occupied ports and relaunch the app cleanly.
- Added better README quickstart guidance covering environment setup, UI startup, and architecture.
- Switched Python environment management to `uv` and standardized local commands around `uv sync` and `uv run`.

### 2026-06-05 - Phase 2 SQL Agent: LlamaIndex Schema Context Enrichment

- Implemented Phase 2 of the SQL agent pipeline with LlamaIndex-based schema context retrieval.
- Added a new retrieval stage to the LangGraph flow:
  `understand_question -> retrieve_schema_context -> inspect_schema -> generate_sql -> validate_sql -> execute_sql -> compose_answer`
- Added semantic schema documents in [docs/schema_context/ecommerce_semantics.md](/E:/AI%20Thuc%20Chien/VSF/datathon_2026/docs/schema_context/ecommerce_semantics.md).
- Added retrieval code in [src/sql_rag_agent/retrieval/schema_context.py](/E:/AI%20Thuc%20Chien/VSF/datathon_2026/src/sql_rag_agent/retrieval/schema_context.py) and [src/sql_rag_agent/nodes/retrieve_schema_context.py](/E:/AI%20Thuc%20Chien/VSF/datathon_2026/src/sql_rag_agent/nodes/retrieve_schema_context.py).
- Preserved the UI table filter as a hard scope boundary so retrieval, schema inspection, and SQL generation only use selected tables.
- Added tests for retrieval normalization, fallback behavior, table filtering, and LLM context propagation.
- Added `uv` project management with [pyproject.toml](/E:/AI%20Thuc%20Chien/VSF/datathon_2026/pyproject.toml), `uv.lock`, and repo instructions in [AGENTS.md](/E:/AI%20Thuc%20Chien/VSF/datathon_2026/AGENTS.md).
- Updated the restart script to launch the UI via `uv run python -m sql_rag_agent.ui`.
- Updated [README.md](/E:/AI%20Thuc%20Chien/VSF/datathon_2026/README.md) with Phase 2 quickstart, architecture details, and the Mermaid-based agent diagram.
- Main commit: `88bb1dd feat: add llamaindex schema retrieval phase 2`

### 2026-06-05 - Repo Cleanup, Push, Merge, And Diagram

- Cleaned generated caches, temporary logs, trace files, and other ignored artifacts before finalizing Phase 2.
- Pushed the completed `prototype` branch to `origin/prototype`.
- Merged the prototype work back into `master`.
- Added the rendered architecture diagram image used by the README in [docs/images/sql_agent_architecture.png](/E:/AI%20Thuc%20Chien/VSF/datathon_2026/docs/images/sql_agent_architecture.png).
- Relevant commits:
  `ce1ee5c Merge pull request #5 from huytdqhe180383/prototype`
  `8a31113 diagram`

### 2026-06-04 - Phase 1 SQL Agent Prototype

- Built the initial six-node SQL agent pipeline with LangGraph.
- Added the core agent nodes:
  `understand_question`
  `inspect_schema`
  `generate_sql`
  `validate_sql`
  `execute_sql`
  `compose_answer`
- Added a simple Gradio UI with:
  one question box
  one answer output box
  no trace/log panel
- Added PostgreSQL access via the MCP-style wrapper in [src/sql_rag_agent/tools/mcp_postgres.py](/E:/AI%20Thuc%20Chien/VSF/datathon_2026/src/sql_rag_agent/tools/mcp_postgres.py).
- Added the first restart helper script for restarting the UI and opening it in the browser.
- Added tests for graph flow, Gradio handlers, schema inspection, and SQL execution behavior.
- Main commit: `af9ff20 feat: add sql rag agent prototype`

### 2026-06-04 - LLM Integration, Validation Rework, And Agent Reliability Fixes

- Added LLM-assisted SQL generation and answer composition to the minimum product.
- Added LLM-based question understanding with few-shot prompting instead of relying only on keyword detection.
- Split model usage into:
  stronger model for question understanding, SQL generation, and SQL repair
  weaker model for answer composition
- Tuned prompts and behavior around synonym ambiguity such as `refunded` vs `returned` and `canceled` vs `cancelled`.
- Simplified the SQL validator so it mainly blocks destructive or write-oriented queries.
- Added SQL execution retry and repair flow:
  if SQL execution fails, the error is sent back to the LLM for repair
  maximum of 3 retries
- Added structured trace logging for agent runs in `logs/agent_traces/`.
- Fixed issues where the UI returned repeated static answers or failed to use `.env` database credentials correctly.
- Relevant commits:
  `d4b521c 1st prototype with llm equipped, gradio UI`
  `a25221e chore: move postgres logs under logs`

### 2026-06-04 - Cleanup Of Generated Logs And Large Trace Files

- Investigated oversized trace and SQL-related artifacts.
- Removed large generated traces and value-mismatch artifacts that should not live in the repo history.
- Standardized local PostgreSQL log placement under `logs/`.
- Relevant commit:
  `395c6a9 chore: remove generated value mismatch traces`

### 2026-06-01 To 2026-06-04 - PostgreSQL Schema Design And Local Data Load Pipeline

- Defined the local PostgreSQL warehouse structure across:
  `stg`
  `core`
  `mart`
- Implemented normalized table creation and transformation SQL in:
  [sql/01_create_schemas_and_staging.sql](/E:/AI%20Thuc%20Chien/VSF/datathon_2026/sql/01_create_schemas_and_staging.sql)
  [sql/02_create_core_tables.sql](/E:/AI%20Thuc%20Chien/VSF/datathon_2026/sql/02_create_core_tables.sql)
  [sql/03_transform_staging_to_core.sql](/E:/AI%20Thuc%20Chien/VSF/datathon_2026/sql/03_transform_staging_to_core.sql)
  [sql/04_create_marts.sql](/E:/AI%20Thuc%20Chien/VSF/datathon_2026/sql/04_create_marts.sql)
  [sql/05_verify_schema.sql](/E:/AI%20Thuc%20Chien/VSF/datathon_2026/sql/05_verify_schema.sql)
- Added the local PostgreSQL setup script in [scripts/setup_postgres_local.ps1](/E:/AI%20Thuc%20Chien/VSF/datathon_2026/scripts/setup_postgres_local.ps1).
- Normalized the ecommerce model so returns and reviews resolve at the `order_item_id` grain where possible.
- Added verification and import reporting docs:
  [docs/postgres-local-setup.md](/E:/AI%20Thuc%20Chien/VSF/datathon_2026/docs/postgres-local-setup.md)
  [docs/schema-postgres-import-report.md](/E:/AI%20Thuc%20Chien/VSF/datathon_2026/docs/schema-postgres-import-report.md)
  [docs/superpowers/plans/2026-06-01-postgres-local-schema.md](/E:/AI%20Thuc%20Chien/VSF/datathon_2026/docs/superpowers/plans/2026-06-01-postgres-local-schema.md)

### 2026-05-26 To 2026-05-28 - Early Repository Baseline

- Initial README and storytelling/report work landed before the SQL-agent and PostgreSQL implementation phases.
- Relevant earlier commits:
  `abdf069 Add storytelling. Score: 900k`
  `1475a9a README`
  `1857709 language update`
  `ba1406a Update storytelling with demographic, clear goal`
  `139f117 Add report`

## Current State Summary

- PostgreSQL local warehouse is defined and documented.
- Phase 1 SQL agent is implemented and tested.
- Phase 2 semantic schema retrieval with LlamaIndex is implemented and tested.
- Phase 3 multi-candidate generation and contract-aware ranking are implemented with focused tests.
- Benchmark evaluation artifacts and mismatch rerun comparison folders are available under [results](/E:/AI%20Thuc%20Chien/VSF/datathon_2026/results).
- The Gradio UI is available with a question box, answer box, and table selector.
- Local Python environment management uses `uv`.
- The main architecture and quickstart are documented in [README.md](/E:/AI%20Thuc%20Chien/VSF/datathon_2026/README.md).
