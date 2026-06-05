from __future__ import annotations

from decimal import Decimal
from typing import Any

from sql_rag_agent.llm import LLMProviderProtocol
from sql_rag_agent.state import SQLAgentState
from sql_rag_agent.tracing import TraceWriter


def compose_answer(
    state: SQLAgentState,
    llm_provider: LLMProviderProtocol | None = None,
    trace_writer: TraceWriter | None = None,
) -> SQLAgentState:
    result = _first_successful_result(state.get("execution_results", []))
    selected_tables = state.get("selected_tables", [])
    candidate = _candidate_for_result(state.get("validated_sql", []), result)

    if result is None:
        final_answer = _no_result_answer(state)
        confidence = 0.0
        ground_truth: dict[str, Any] = {
            "question": state["question"],
            "selected_tables": selected_tables,
            "executed_sql": None,
            "result_rows": [],
        }
    else:
        rows = result["rows"]
        first_row = rows[0] if rows else {}
        filters = candidate.get("filters", []) if candidate else []
        tables_text = ", ".join(selected_tables) if selected_tables else "the selected schema tables"
        filter_text = "; ".join(filters) if filters else "no explicit filters"
        basis = candidate.get("reasoning_summary", "Uses the validated SQL result.") if candidate else "Uses the validated SQL result."
        caveat = "" if rows else " The result set was empty, so confidence is low."
        final_answer = _compose_with_llm(
            state=state,
            candidate=candidate,
            result=result,
            selected_tables=selected_tables,
            llm_provider=llm_provider,
            trace_writer=trace_writer,
        )
        if final_answer is None:
            direct_answer = _direct_answer(first_row, candidate)
            final_answer = (
                f"{direct_answer} This was calculated from {tables_text}. "
                f"Calculation basis: {basis} Filters applied: {filter_text}.{caveat}"
            )
        confidence = 0.8 if rows else 0.35
        ground_truth = {
            "question": state["question"],
            "selected_tables": selected_tables,
            "executed_sql": result["sql"],
            "result_rows": rows,
            "confidence": confidence,
        }

    return {
        **state,
        "final_answer": final_answer,
        "confidence": confidence,
        "ground_truth": ground_truth,
        "ranked_results": [],
    }


def _compose_with_llm(
    *,
    state: SQLAgentState,
    candidate: dict[str, Any] | None,
    result: dict[str, Any],
    selected_tables: list[str],
    llm_provider: LLMProviderProtocol | None,
    trace_writer: TraceWriter | None,
) -> str | None:
    if llm_provider is None or candidate is None:
        return None
    try:
        answer = llm_provider.compose_answer(
            question=state["question"],
            candidate=candidate,
            execution_result=result,
            selected_tables=selected_tables,
        )
    except Exception as exc:
        if trace_writer:
            trace_writer.write("llm_compose_answer_error", {"error": str(exc)})
        return None

    if answer and trace_writer:
        trace_writer.write(
            "llm_compose_answer",
            {
                "question": state["question"],
                "candidate_id": candidate.get("candidate_id"),
                "answer": answer,
            },
        )
    return answer


def _no_result_answer(state: SQLAgentState) -> str:
    selected_scope_codes = {"unsupported_question", "table_outside_allowed_scope"}
    if state.get("allowed_tables") and any(error.get("code") in selected_scope_codes for error in state.get("errors", [])):
        return (
            "I could not answer using only the selected tables. "
            "Choose tables that contain the needed fields, or clear the table filter."
        )
    if any(error.get("code") == "unsupported_question" for error in state.get("errors", [])):
        return (
            "I do not have enough information to answer that as a SQL question yet. "
            "This phase-1 agent currently supports a small set of ecommerce questions, "
            "including total customers, refunded customers in an explicit date range, "
            "and highest-revenue product."
        )
    return "I could not produce an answer because no validated SQL query returned results."


def _first_successful_result(results: list[dict[str, Any]]) -> dict[str, Any] | None:
    for result in results:
        if result.get("error") is None:
            return result
    return None


def _candidate_for_result(
    candidates: list[dict[str, Any]],
    result: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if result is None:
        return None
    for candidate in candidates:
        if candidate["candidate_id"] == result["candidate_id"]:
            return candidate
    return None


def _direct_answer(row: dict[str, Any], candidate: dict[str, Any] | None) -> str:
    if not row:
        return "The validated query returned no rows."

    if "product_name" in row and "revenue" in row:
        return f"{row['product_name']} had the highest revenue, with {_format_money(row['revenue'])}."
    if "revenue" in row:
        return f"The revenue was {_format_money(row['revenue'])}."
    if "customer_count" in row:
        label = candidate.get("answer_label") if candidate else None
        if label:
            return f"There were {row['customer_count']:,} {label}."
        return f"There were {row['customer_count']:,} customers."
    if "row_count" in row:
        return f"The selected table contained {row['row_count']:,} rows."

    formatted = ", ".join(f"{key}: {value}" for key, value in row.items())
    return f"The validated query returned {formatted}."


def _format_money(value: Any) -> str:
    if isinstance(value, Decimal):
        amount = float(value)
    else:
        amount = float(value)
    return f"${amount:,.2f}"
