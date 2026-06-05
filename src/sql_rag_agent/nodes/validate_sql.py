from __future__ import annotations

from sql_rag_agent.state import SQLAgentState
from sql_rag_agent.tracing import TraceWriter
from sql_rag_agent.tools.sql_validator import validate_sql_candidate


def validate_sql(state: SQLAgentState, trace_writer: TraceWriter | None = None) -> SQLAgentState:
    validated = [
        validate_sql_candidate(
            candidate,
            schema_context=state.get("schema_context", []),
            question_analysis=state.get("question_analysis", {}),
            allowed_tables=state.get("allowed_tables", []),
        )
        for candidate in state.get("candidate_sql", [])
    ]
    errors = list(state.get("errors", []))
    for candidate in validated:
        for error in candidate.get("errors", []):
            errors.append({"node": "validate_sql", "candidate_id": candidate["candidate_id"], **error})

    next_state = {
        **state,
        "validated_sql": [candidate for candidate in validated if candidate["is_valid"]],
        "errors": errors,
    }
    if trace_writer:
        trace_writer.write(
            "validate_sql",
            {
                "candidate_count": len(validated),
                "valid_candidate_count": len(next_state["validated_sql"]),
                "validated_candidates": validated,
            },
        )
    return next_state
