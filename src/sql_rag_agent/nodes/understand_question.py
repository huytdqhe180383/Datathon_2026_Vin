from __future__ import annotations

from typing import Any

from sql_rag_agent.llm import LLMProviderProtocol
from sql_rag_agent.state import SQLAgentState
from sql_rag_agent.tracing import TraceWriter


def understand_question(
    state: SQLAgentState,
    llm_provider: LLMProviderProtocol | None = None,
    trace_writer: TraceWriter | None = None,
) -> SQLAgentState:
    question = state["question"].strip()
    llm_analysis = _analyze_with_llm(question, llm_provider, trace_writer)
    if llm_analysis is not None:
        return {
            **state,
            "question_analysis": llm_analysis,
            "errors": state.get("errors", []),
        }

    return {
        **state,
        "question_analysis": _keyword_analysis(question),
        "errors": state.get("errors", []),
    }


def _keyword_analysis(question: str) -> dict[str, Any]:
    lowered = question.lower()

    question_type = "lookup"
    expected_answer_type = "sentence"
    if any(word in lowered for word in ["highest", "lowest", "top", "most", "least", "rank"]):
        question_type = "ranking"
        expected_answer_type = "ranked_list"
    elif any(word in lowered for word in ["how many", "count", "number of"]):
        question_type = "count"
        expected_answer_type = "number"
    elif any(word in lowered for word in ["total", "sum", "average", "median", "mean"]):
        question_type = "aggregate"
        expected_answer_type = "number"
    elif any(word in lowered for word in ["compare", "versus", "vs", "difference"]):
        question_type = "comparison"
        expected_answer_type = "table"
    elif any(word in lowered for word in ["trend", "over time", "monthly", "daily"]):
        question_type = "trend"
        expected_answer_type = "table"
    elif any(word in lowered for word in ["where", "filter"]):
        question_type = "filter"
        expected_answer_type = "table"

    requires_time_filter = any(
        phrase in lowered
        for phrase in [
            "last quarter",
            "this quarter",
            "q1",
            "q2",
            "q3",
            "q4",
            "month",
            "year",
            "week",
            "between",
        ]
    )
    requires_join = any(
        word in lowered
        for word in [
            "product",
            "customer",
            "category",
            "channel",
            "shipment",
            "return",
            "review",
            "device",
        ]
    )
    requires_metric_definition = any(
        word in lowered
        for word in ["revenue", "cogs", "discount", "refund", "repeat", "rate", "value"]
    )

    ambiguities: list[str] = []
    if "last quarter" in lowered:
        ambiguities.append("last quarter depends on the current date")

    return {
        "question_type": question_type,
        "expected_answer_type": expected_answer_type,
        "requires_time_filter": requires_time_filter,
        "requires_join": requires_join,
        "requires_metric_definition": requires_metric_definition,
        "ambiguities": ambiguities,
    }


def _analyze_with_llm(
    question: str,
    llm_provider: LLMProviderProtocol | None,
    trace_writer: TraceWriter | None,
) -> dict[str, Any] | None:
    if llm_provider is None:
        return None

    try:
        analysis = llm_provider.analyze_question(question=question)
    except Exception as exc:
        if trace_writer:
            trace_writer.write("llm_understand_question_error", {"error": str(exc)})
        return None

    if analysis and trace_writer:
        trace_writer.write(
            "llm_understand_question",
            {
                "question": question,
                "analysis": analysis,
            },
        )
    return analysis
