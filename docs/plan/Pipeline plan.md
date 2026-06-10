# Coding Agent Plan: Hybrid SQL-RAG Agent with LangGraph + LlamaIndex + MCP

## Goal

Build a PostgreSQL querying agent that can:

1. Understand a user’s natural-language question.
2. Retrieve relevant schema, table metadata, metric definitions, and example SQL.
3. Generate one or more candidate SQL queries.
4. Validate the SQL before execution.
5. Execute SQL through an MCP PostgreSQL tool.
6. Rank the candidate results.
7. Return a grounded natural-language answer with evidence, not just a raw value.

---

## Target Architecture

```text
User question
  ↓
LangGraph controller
  ↓
LlamaIndex schema / metadata retriever
  ↓
SQL candidate generator
  ↓
SQL validator
  ↓
MCP PostgreSQL execution tool
  ↓
Result validator and ranker
  ↓
Grounded final answer
```

---

## Technology Stack

Use the following components:

| Component                                  | Purpose                                                         |
| ------------------------------------------ | --------------------------------------------------------------- |
| PostgreSQL                                 | Source of truth for all loaded CSV data                         |
| MCP PostgreSQL tool                        | Controlled SQL execution layer                                  |
| LangGraph                                  | Agent workflow orchestration                                    |
| LlamaIndex                                 | Schema, metadata, metric, and example-query retrieval           |
| `sqlglot` or `pglast`                      | SQL parsing and validation                                      |
| LLM                                        | SQL generation, reasoning, ranking, and final answer generation |
| LangSmith / OpenTelemetry / custom logging | Tracing and observability                                       |
| Evaluation dataset                         | Regression testing for expected answers                         |

---

# Phase 1: Build the Minimal End-to-End Agent

## Objective

Create a working agent that can answer a user question by:

1. Inspecting PostgreSQL schema.
2. Generating one SQL query.
3. Executing it through MCP.
4. Returning a grounded sentence.

---

## Required LangGraph Nodes

Implement these initial nodes:

```text
understand_question
inspect_schema
generate_sql
validate_sql
execute_sql
compose_answer
```

---

## State Object

Create a shared state object for the graph.

```python
from typing import TypedDict, Any


class SQLAgentState(TypedDict):
    question: str
    question_analysis: dict[str, Any]
    schema_context: list[dict[str, Any]]
    selected_tables: list[str]
    candidate_sql: list[dict[str, Any]]
    validated_sql: list[dict[str, Any]]
    execution_results: list[dict[str, Any]]
    ranked_results: list[dict[str, Any]]
    final_answer: str
    confidence: float
    ground_truth: dict[str, Any]
    errors: list[dict[str, Any]]
```

---

## Node 1: `understand_question`

### Purpose

Parse the user question into a structured task.

### Output shape

```json
{
  "question_type": "aggregate | lookup | comparison | trend | ranking | count | filter",
  "expected_answer_type": "number | entity | table | sentence | ranked_list",
  "requires_time_filter": true,
  "requires_join": true,
  "requires_metric_definition": true,
  "ambiguities": []
}
```

### Requirements

The node should identify:

* whether the question requires aggregation
* whether it needs a date range
* whether it likely requires joins
* whether a business metric definition is needed
* whether the user’s wording is ambiguous

---

## Node 2: `inspect_schema`

### Purpose

Retrieve schema from PostgreSQL through MCP or a schema introspection helper.

### Required MCP-style operations

The coding agent should create or use tools equivalent to:

```text
list_tables
describe_table
get_foreign_keys
get_sample_rows
execute_sql
```

### Minimum schema metadata to collect

For each relevant table:

```json
{
  "table_name": "orders",
  "columns": [
    {
      "name": "order_id",
      "type": "uuid",
      "nullable": false,
      "description": null
    }
  ],
  "primary_keys": ["order_id"],
  "foreign_keys": [
    {
      "column": "customer_id",
      "references_table": "customers",
      "references_column": "customer_id"
    }
  ],
  "sample_rows": []
}
```

---

## Node 3: `generate_sql`

### Purpose

Generate a SQL query from:

* user question
* schema context
* known joins
* known metric definitions
* known date constraints

### Output shape

```json
{
  "candidate_id": "candidate_1",
  "sql": "SELECT ...",
  "reasoning_summary": "Uses completed orders and groups by product because the user asked for highest revenue product.",
  "expected_result_shape": ["product_name", "revenue"]
}
```

### Rules

Generated SQL must:

* be PostgreSQL-compatible
* be read-only
* use explicit table aliases
* use explicit date bounds when time is mentioned
* avoid `SELECT *`
* include `LIMIT` for exploratory queries
* use schema-qualified names if needed
* preserve business definitions from retrieved metadata

---

## Node 4: `validate_sql`

### Purpose

Reject unsafe or invalid SQL before execution.

### Required validation rules

Reject SQL if it contains:

```text
INSERT
UPDATE
DELETE
DROP
ALTER
TRUNCATE
CREATE
GRANT
REVOKE
COPY
CALL
DO
```

Also reject or repair if:

* referenced tables do not exist
* referenced columns do not exist
* joins use unknown relationships
* aggregation is missing `GROUP BY`
* time-bounded questions lack explicit date filters
* query uses `SELECT *`
* query has no `LIMIT` where result size could be large

### Recommended library

Use one of:

```text
sqlglot
pglast
```

---

## Node 5: `execute_sql`

### Purpose

Execute validated SQL through the MCP PostgreSQL tool.

### Output shape

```json
{
  "candidate_id": "candidate_1",
  "sql": "SELECT ...",
  "rows": [],
  "row_count": 0,
  "error": null,
  "execution_time_ms": 120
}
```

### Rules

* Never execute unvalidated SQL.
* Use a read-only PostgreSQL role.
* Set a statement timeout.
* Limit returned rows.
* Store SQL and result rows for auditability.

---

## Node 6: `compose_answer`

### Purpose

Return a normal natural-language answer with supporting evidence.

### Required answer format

The final answer should include:

1. Direct answer.
2. Value or entity.
3. Calculation basis.
4. Tables used.
5. Filters applied.
6. Caveat, if confidence is low.

### Example

```text
The highest-revenue product in Q1 2026 was Product A, with $128,400 in completed-order revenue. This was calculated from the orders and products tables by summing orders.total_amount where orders.status = 'completed' and order_date was between January 1 and March 31, 2026, then ranking products by total revenue.
```

---

# Phase 2: Add LlamaIndex Retrieval

## Objective

Use LlamaIndex to retrieve relevant context before SQL generation.

LlamaIndex should not own the full workflow. It should only retrieve useful context for LangGraph.

---

## Build a Schema and Metadata Index

Index the following document types:

```text
table schemas
column descriptions
foreign key relationships
business metric definitions
data dictionary entries
sample SQL queries
known caveats
example question-to-SQL pairs
```

---

## Example Indexed Documents

### Table schema document

```text
Table: orders

Columns:
- order_id: primary key
- customer_id: foreign key to customers.customer_id
- product_id: foreign key to products.product_id
- order_date: date when the order was placed
- status: pending, completed, cancelled
- total_amount: final order value

Business note:
Revenue should normally include only rows where status = 'completed'.
```

### Metric definition document

```text
Metric: revenue

Definition:
Revenue is calculated as SUM(orders.total_amount) for rows where orders.status = 'completed'.

Exclusions:
Cancelled, refunded, and pending orders should not be included unless the user explicitly asks for them.
```

### Example SQL document

```sql
-- Monthly completed-order revenue
SELECT
  date_trunc('month', order_date) AS month,
  SUM(total_amount) AS revenue
FROM orders
WHERE status = 'completed'
GROUP BY 1
ORDER BY 1;
```

---

## New LangGraph Node: `retrieve_schema_context`

Add this node after `understand_question`.

```text
understand_question
  ↓
retrieve_schema_context
  ↓
select_tables
  ↓
generate_sql
```

### Input

```json
{
  "question": "Which product had the highest revenue last quarter?"
}
```

### Output

```json
{
  "retrieved_context": [
    {
      "type": "table_schema",
      "name": "orders",
      "content": "...",
      "score": 0.91
    },
    {
      "type": "metric_definition",
      "name": "revenue",
      "content": "...",
      "score": 0.88
    }
  ]
}
```

---

# Phase 3: Add Multiple SQL Candidates

## Objective

Improve reliability by generating, validating, executing, and ranking multiple SQL candidates.

---

## Updated Graph

```text
understand_question
  ↓
retrieve_schema_context
  ↓
select_tables
  ↓
generate_sql_candidates
  ↓
validate_sql_candidates
  ↓
execute_sql_candidates
  ↓
rank_results
  ↓
compose_grounded_answer
```

---

## Node: `generate_sql_candidates`

Generate 2–3 candidates when:

* the question is ambiguous
* there are multiple possible metric definitions
* multiple tables could answer the question
* the first query might require joins
* the question asks for ranking, comparison, or aggregation

### Candidate output

```json
[
  {
    "candidate_id": "candidate_a",
    "sql": "SELECT ...",
    "assumptions": ["Revenue means completed-order revenue."],
    "expected_result_shape": ["product_name", "revenue"]
  },
  {
    "candidate_id": "candidate_b",
    "sql": "SELECT ...",
    "assumptions": ["Revenue means all non-cancelled orders."],
    "expected_result_shape": ["product_name", "revenue"]
  }
]
```

---

## Node: `rank_results`

Rank candidates using a scoring rubric.

| Criterion           | Weight |
| ------------------- | -----: |
| Schema match        |    25% |
| User intent match   |    25% |
| Business-rule match |    20% |
| SQL correctness     |    15% |
| Result usefulness   |    10% |
| Simplicity          |     5% |

### Ranking output

```json
{
  "winner": "candidate_a",
  "confidence": 0.86,
  "reason": "Candidate A uses the documented revenue definition, joins products for a readable product name, applies the correct date range, and returns a single top-ranked result."
}
```

---

# Phase 4: Add SQL Repair and Retry

## Objective

Allow the agent to recover from SQL errors safely.

---

## New Node: `repair_sql`

Trigger this node when:

* SQL references a missing column
* SQL references a missing table
* SQL has a syntax error
* result is empty but likely should not be
* date filter is malformed
* join path is invalid

---

## Repair Rules

The repair node may:

* inspect schema again
* retrieve more metadata
* generate a corrected query
* simplify the query
* ask for clarification only when the business definition is truly missing

The repair node must not:

* execute unsafe SQL
* guess unavailable metric definitions
* silently change the meaning of the user’s question
* retry indefinitely

Set a maximum retry count:

```python
MAX_RETRIES = 2
```

---

# Phase 5: Add Ground Truth Trace

## Objective

Every final answer should be backed by an internal trace.

---

## Ground Truth Object

Store this in the final state:

```json
{
  "question": "Which product had the highest revenue last quarter?",
  "selected_tables": ["orders", "products"],
  "metric_definitions": [
    {
      "metric": "revenue",
      "definition": "SUM(total_amount) where status = 'completed'"
    }
  ],
  "executed_sql": "SELECT ...",
  "result_rows": [
    {
      "product_name": "Product A",
      "revenue": 128400
    }
  ],
  "ranking_reason": "Candidate A matched the documented revenue definition.",
  "confidence": 0.86
}
```

---

## User-Facing Answer Requirements

The final answer must be a normal sentence or paragraph.

It should not be:

```text
Product A, 128400
```

It should be:

```text
Product A had the highest revenue last quarter, with $128,400 in completed-order revenue. This was calculated from the orders and products tables by summing total_amount for completed orders within the quarter and ranking products by total revenue.
```

---

# Phase 6: Add Evaluation Tests

## Objective

Create a benchmark suite to test agent reliability.

---

## Evaluation Dataset Format

Create test cases like:

```json
{
  "id": "highest_revenue_product_q1",
  "question": "Which product had the highest revenue in Q1 2026?",
  "expected_tables": ["orders", "products"],
  "expected_columns": ["orders.total_amount", "orders.status", "orders.order_date", "products.name"],
  "expected_filters": ["orders.status = 'completed'", "Q1 2026 date bounds"],
  "expected_answer_shape": ["product_name", "revenue"],
  "must_include_in_answer": ["completed-order revenue", "Q1 2026"]
}
```

---

## Evaluation Checks

For each test case, verify:

* selected tables are correct
* SQL is read-only
* SQL uses expected filters
* result shape is correct
* final answer includes the value
* final answer includes the calculation basis
* final answer does not claim unsupported facts

---

# Implementation Checklist

## Core Agent

* [ ] Create LangGraph project structure.
* [ ] Define `SQLAgentState`.
* [ ] Implement `understand_question`.
* [ ] Implement `inspect_schema`.
* [ ] Implement `generate_sql`.
* [ ] Implement `validate_sql`.
* [ ] Implement `execute_sql` through MCP.
* [ ] Implement `compose_answer`.
* [ ] Add basic tracing.

## LlamaIndex Retrieval

* [ ] Export PostgreSQL schemas.
* [ ] Create schema documents.
* [ ] Add metric definition documents.
* [ ] Add example SQL documents.
* [ ] Build LlamaIndex vector index.
* [ ] Implement `retrieve_schema_context`.
* [ ] Feed retrieved context into SQL generation.

## Candidate Ranking

* [ ] Generate multiple SQL candidates.
* [ ] Validate each candidate.
* [ ] Execute valid candidates.
* [ ] Score each result.
* [ ] Select the winning candidate.
* [ ] Store ranking explanation.

## Safety

* [ ] Use read-only PostgreSQL role.
* [ ] Block non-`SELECT` SQL.
* [ ] Add statement timeout.
* [ ] Add row limit.
* [ ] Validate tables and columns.
* [ ] Block destructive statements.
* [ ] Log all executed SQL.

## Grounded Answering

* [ ] Include value.
* [ ] Include source tables.
* [ ] Include filters.
* [ ] Include calculation basis.
* [ ] Include caveats when needed.
* [ ] Avoid unsupported claims.

## Evaluation

* [ ] Create benchmark questions.
* [ ] Add expected SQL features.
* [ ] Add expected answer features.
* [ ] Run tests after prompt changes.
* [ ] Track failures by category.

---

# Suggested Repository Structure

```text
sql_rag_agent/
  app/
    graph.py
    state.py
    config.py

  app/nodes/
    understand_question.py
    retrieve_schema_context.py
    select_tables.py
    generate_sql_candidates.py
    validate_sql.py
    execute_sql.py
    repair_sql.py
    rank_results.py
    compose_answer.py

  app/tools/
    mcp_postgres.py
    schema_introspection.py
    sql_validator.py

  app/retrieval/
    build_schema_index.py
    llamaindex_retriever.py
    documents/
      schemas/
      metrics/
      examples/

  app/prompts/
    understand_question.md
    generate_sql.md
    rank_results.md
    compose_answer.md

  tests/
    test_sql_validation.py
    test_graph_flow.py
    test_eval_cases.py

  evals/
    cases.jsonl
    run_eval.py

  README.md
```

---

# Final Target Behavior

Given this user question:

```text
Which product had the highest revenue last quarter?
```

The agent should produce an answer like:

```text
Product A had the highest revenue last quarter, with $128,400 in completed-order revenue. This was calculated from the orders and products tables by summing orders.total_amount where orders.status = 'completed' and order_date was between January 1 and March 31, 2026, then ranking products by total revenue.
```

The internal trace should include:

```text
selected tables
retrieved metric definition
candidate SQL queries
executed SQL
returned rows
ranking reason
confidence score
```

The system should be optimized for **correctness, traceability, SQL safety, and grounded natural-language answers**.
