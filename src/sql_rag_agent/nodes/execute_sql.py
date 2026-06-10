from __future__ import annotations

from time import perf_counter

from sql_rag_agent.config import DEFAULT_ROW_LIMIT, DEFAULT_STATEMENT_TIMEOUT_MS
from sql_rag_agent.llm import LLMProviderProtocol
from sql_rag_agent.state import SQLAgentState
from sql_rag_agent.tools.mcp_postgres import PostgresMCPTool, PostgresMCPToolProtocol
from sql_rag_agent.tools.sql_validator import validate_sql_candidate
from sql_rag_agent.tracing import TraceWriter

MAX_SQL_RETRIES = 3


def execute_sql(
    state: SQLAgentState,
    mcp_tool: PostgresMCPToolProtocol | None = None,
    llm_provider: LLMProviderProtocol | None = None,
    trace_writer: TraceWriter | None = None,
) -> SQLAgentState:
    tool = mcp_tool or PostgresMCPTool()
    execution_results = []
    errors = list(state.get("errors", []))
    candidate_sql = list(state.get("candidate_sql", []))
    validated_candidates = list(state.get("validated_sql", []))

    for candidate in list(validated_candidates):
        current_candidate = candidate
        retry_count = 0

        while True:
            started = perf_counter()
            try:
                rows = tool.execute_sql(
                    current_candidate["sql"],
                    limit=_row_limit_for_state(state),
                    statement_timeout_ms=DEFAULT_STATEMENT_TIMEOUT_MS,
                )
                execution_results.append(
                    {
                        "candidate_id": current_candidate["candidate_id"],
                        "sql": current_candidate["sql"],
                        "rows": rows,
                        "row_count": len(rows),
                        "error": None,
                        "execution_time_ms": round((perf_counter() - started) * 1000, 2),
                        "retry_count": retry_count,
                    }
                )
                break
            except Exception as exc:
                message = str(exc)
                errors.append(
                    {
                        "node": "execute_sql",
                        "candidate_id": current_candidate["candidate_id"],
                        "retry_count": retry_count,
                        "message": message,
                    }
                )
                execution_results.append(
                    {
                        "candidate_id": current_candidate["candidate_id"],
                        "sql": current_candidate["sql"],
                        "rows": [],
                        "row_count": 0,
                        "error": message,
                        "execution_time_ms": round((perf_counter() - started) * 1000, 2),
                        "retry_count": retry_count,
                    }
                )

                if retry_count >= MAX_SQL_RETRIES or llm_provider is None:
                    break

                repaired_candidate = _repair_sql_candidate(
                    state=state,
                    candidate=current_candidate,
                    execution_error=message,
                    retry_count=retry_count + 1,
                    llm_provider=llm_provider,
                    trace_writer=trace_writer,
                )
                if repaired_candidate is None:
                    break

                candidate_sql.append(repaired_candidate)
                validated_repair = validate_sql_candidate(
                    repaired_candidate,
                    schema_context=state.get("schema_context", []),
                    question_analysis=state.get("question_analysis", {}),
                    allowed_tables=state.get("allowed_tables", []),
                )
                if not validated_repair["is_valid"]:
                    for error in validated_repair.get("errors", []):
                        errors.append(
                            {
                                "node": "execute_sql",
                                "candidate_id": validated_repair["candidate_id"],
                                "retry_count": retry_count + 1,
                                **error,
                            }
                        )
                    break

                validated_candidates.append(validated_repair)
                current_candidate = validated_repair
                retry_count += 1

    if not validated_candidates:
        errors.append({"node": "execute_sql", "message": "No validated SQL was available to execute."})

    next_state = {
        **state,
        "candidate_sql": candidate_sql,
        "validated_sql": validated_candidates,
        "execution_results": execution_results,
        "errors": errors,
    }
    if trace_writer:
        trace_writer.write(
            "execute_sql",
            {
                "execution_results": execution_results,
                "errors": errors,
            },
        )
    return next_state


def _repair_sql_candidate(
    *,
    state: SQLAgentState,
    candidate: dict[str, object],
    execution_error: str,
    retry_count: int,
    llm_provider: LLMProviderProtocol,
    trace_writer: TraceWriter | None,
) -> dict[str, object] | None:
    try:
        repaired = llm_provider.repair_sql_candidate(
            question=state["question"],
            question_analysis=state.get("question_analysis", {}),
            schema_context=state.get("schema_context", []),
            selected_tables=state.get("selected_tables", []),
            retrieved_context=state.get("retrieved_context", []),
            previous_candidate=candidate,
            execution_error=execution_error,
            retry_count=retry_count,
        )
    except TypeError as exc:
        if "retrieved_context" not in str(exc):
            raise
        repaired = llm_provider.repair_sql_candidate(
            question=state["question"],
            question_analysis=state.get("question_analysis", {}),
            schema_context=state.get("schema_context", []),
            selected_tables=state.get("selected_tables", []),
            previous_candidate=candidate,
            execution_error=execution_error,
            retry_count=retry_count,
        )
    except Exception as exc:
        if trace_writer:
            trace_writer.write("llm_repair_sql_error", {"error": str(exc), "retry_count": retry_count})
        return None

    if not repaired:
        return None

    repaired = dict(repaired)
    repaired["candidate_id"] = f"{candidate['candidate_id']}_retry_{retry_count}"
    if trace_writer:
        trace_writer.write(
            "llm_repair_sql",
            {
                "retry_count": retry_count,
                "execution_error": execution_error,
                "previous_candidate_id": candidate.get("candidate_id"),
                "repaired_candidate": repaired,
            },
        )
    return repaired


def _row_limit_for_state(state: SQLAgentState) -> int:
    analysis = state.get("question_analysis", {})
    question = state.get("question", "").lower()
    if analysis.get("expected_answer_type") == "table" or question.startswith("return a table"):
        return 1000
    return DEFAULT_ROW_LIMIT
