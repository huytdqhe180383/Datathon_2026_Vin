from __future__ import annotations

from time import perf_counter

from sql_rag_agent.config import DEFAULT_ROW_LIMIT, DEFAULT_STATEMENT_TIMEOUT_MS
from sql_rag_agent.state import SQLAgentState
from sql_rag_agent.tools.mcp_postgres import PostgresMCPTool, PostgresMCPToolProtocol
from sql_rag_agent.tracing import TraceWriter


def execute_sql(
    state: SQLAgentState,
    mcp_tool: PostgresMCPToolProtocol | None = None,
    trace_writer: TraceWriter | None = None,
) -> SQLAgentState:
    tool = mcp_tool or PostgresMCPTool()
    execution_results = []
    errors = list(state.get("errors", []))

    for candidate in state.get("validated_sql", []):
        started = perf_counter()
        try:
            rows = tool.execute_sql(
                candidate["sql"],
                limit=DEFAULT_ROW_LIMIT,
                statement_timeout_ms=DEFAULT_STATEMENT_TIMEOUT_MS,
            )
            execution_results.append(
                {
                    "candidate_id": candidate["candidate_id"],
                    "sql": candidate["sql"],
                    "rows": rows,
                    "row_count": len(rows),
                    "error": None,
                    "execution_time_ms": round((perf_counter() - started) * 1000, 2),
                }
            )
        except Exception as exc:
            message = str(exc)
            errors.append(
                {
                    "node": "execute_sql",
                    "candidate_id": candidate["candidate_id"],
                    "message": message,
                }
            )
            execution_results.append(
                {
                    "candidate_id": candidate["candidate_id"],
                    "sql": candidate["sql"],
                    "rows": [],
                    "row_count": 0,
                    "error": message,
                    "execution_time_ms": round((perf_counter() - started) * 1000, 2),
                }
            )

    if not state.get("validated_sql"):
        errors.append({"node": "execute_sql", "message": "No validated SQL was available to execute."})

    next_state = {**state, "execution_results": execution_results, "errors": errors}
    if trace_writer:
        trace_writer.write(
            "execute_sql",
            {
                "execution_results": execution_results,
                "errors": errors,
            },
        )
    return next_state
