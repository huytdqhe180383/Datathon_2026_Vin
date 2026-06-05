from __future__ import annotations

from typing import Any

from sql_rag_agent.retrieval.schema_context import (
    LlamaIndexSchemaRetriever,
    SchemaRetrieverProtocol,
    filter_context_by_allowed_tables,
)
from sql_rag_agent.state import SQLAgentState
from sql_rag_agent.tools.mcp_postgres import PostgresMCPToolProtocol
from sql_rag_agent.tracing import TraceWriter

MAX_LOGGED_CONTEXT_CHARS = 500


def retrieve_schema_context(
    state: SQLAgentState,
    schema_retriever: SchemaRetrieverProtocol | None = None,
    mcp_tool: PostgresMCPToolProtocol | None = None,
    trace_writer: TraceWriter | None = None,
) -> SQLAgentState:
    allowed_tables = list(state.get("allowed_tables", []))
    retriever = schema_retriever or LlamaIndexSchemaRetriever(mcp_tool=mcp_tool)
    errors = list(state.get("errors", []))

    try:
        retrieved_context = retriever.retrieve(
            question=state["question"],
            allowed_tables=allowed_tables,
        )
        retrieved_context = _normalize_context(retrieved_context)
        retrieved_context = filter_context_by_allowed_tables(retrieved_context, allowed_tables)
    except Exception as exc:
        retrieved_context = []
        errors.append(
            {
                "node": "retrieve_schema_context",
                "code": "schema_retrieval_failed",
                "message": str(exc),
            }
        )

    if trace_writer:
        trace_writer.write(
            "retrieve_schema_context",
            {
                "allowed_tables": allowed_tables,
                "retrieved_context": [_log_safe_context(item) for item in retrieved_context],
                "errors": [error for error in errors if error.get("node") == "retrieve_schema_context"],
            },
        )

    return {
        **state,
        "retrieved_context": retrieved_context,
        "errors": errors,
    }


def _normalize_context(context: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for item in context:
        normalized.append(
            {
                "type": str(item.get("type") or "semantic_doc"),
                "name": str(item.get("name") or "retrieved_context"),
                "content": str(item.get("content") or ""),
                "score": float(item.get("score") or 0.0),
                "source": str(item.get("source") or ""),
                "tables": list(item.get("tables") or []),
                "columns": list(item.get("columns") or []),
            }
        )
    return normalized


def _log_safe_context(item: dict[str, Any]) -> dict[str, Any]:
    content = item.get("content", "")
    if len(content) > MAX_LOGGED_CONTEXT_CHARS:
        content = content[:MAX_LOGGED_CONTEXT_CHARS] + "...[truncated]"
    return {**item, "content": content}
