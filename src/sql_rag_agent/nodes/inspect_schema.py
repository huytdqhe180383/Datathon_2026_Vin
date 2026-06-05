from __future__ import annotations

from typing import Any

from sql_rag_agent.state import SQLAgentState
from sql_rag_agent.tools.mcp_postgres import PostgresMCPTool, PostgresMCPToolProtocol


TABLE_KEYWORDS = {
    "core.orders": {"order", "orders", "date", "device", "source", "status", "revenue"},
    "core.order_items": {"item", "items", "product", "quantity", "discount", "revenue"},
    "core.products": {"product", "products", "category", "segment", "price", "cogs"},
    "core.customers": {"customer", "customers", "channel", "signup", "gender", "age"},
    "core.payments": {"paid", "payment", "payments", "revenue", "value"},
    "core.shipments": {"shipment", "ship", "delivery", "delivered", "shipping"},
    "core.returns": {"return", "returns", "refund"},
    "core.reviews": {"review", "reviews", "rating"},
    "mart.sales_daily": {"sales", "revenue", "cogs", "daily", "date"},
    "mart.web_traffic_daily": {"traffic", "sessions", "visitors", "bounce", "source"},
}


def inspect_schema(
    state: SQLAgentState,
    mcp_tool: PostgresMCPToolProtocol | None = None,
) -> SQLAgentState:
    tool = mcp_tool or PostgresMCPTool()
    available_tables = tool.list_tables()
    allowed_tables = state.get("allowed_tables", [])
    constrained_tables = _constrain_tables(available_tables, allowed_tables)
    selected_tables = _select_tables(
        state["question"],
        constrained_tables,
        retrieved_context=state.get("retrieved_context", []),
    )
    schema_context: list[dict[str, Any]] = []

    errors = list(state.get("errors", []))
    if allowed_tables and not constrained_tables:
        errors.append(
            {
                "node": "inspect_schema",
                "code": "no_selected_tables_available",
                "message": "None of the selected tables are available in the connected database.",
            }
        )

    for table_name in selected_tables:
        try:
            schema_context.append(tool.describe_table(table_name))
        except Exception as exc:
            errors.append(
                {
                    "node": "inspect_schema",
                    "table_name": table_name,
                    "message": str(exc),
                }
            )

    return {
        **state,
        "selected_tables": selected_tables,
        "schema_context": schema_context,
        "errors": errors,
    }


def _constrain_tables(available_tables: list[str], allowed_tables: list[str]) -> list[str]:
    if not allowed_tables:
        return available_tables
    allowed = set(allowed_tables)
    return [table for table in available_tables if table in allowed]


def _select_tables(
    question: str,
    available_tables: list[str],
    retrieved_context: list[dict[str, Any]] | None = None,
) -> list[str]:
    if not available_tables:
        return []

    context_tables = _tables_from_retrieved_context(retrieved_context or [], available_tables)
    if context_tables:
        selected = list(dict.fromkeys(context_tables))
        keyword_selected = _keyword_selected_tables(question, available_tables)
        for table_name in keyword_selected:
            if table_name not in selected:
                selected.append(table_name)
        return selected[:6]

    return _keyword_selected_tables(question, available_tables)


def _keyword_selected_tables(question: str, available_tables: list[str]) -> list[str]:
    lowered = question.lower()
    scores: dict[str, int] = {}
    for table_name in available_tables:
        keywords = TABLE_KEYWORDS.get(table_name, set()) | set(table_name.replace(".", "_").split("_"))
        score = sum(1 for keyword in keywords if keyword in lowered)
        scores[table_name] = score

    if "customer" in lowered and any(term in lowered for term in ["refund", "refunded", "return", "returned"]):
        preferred = ["core.returns", "core.order_items", "core.orders", "core.customers"]
        return [table for table in preferred if table in available_tables]

    if "revenue" in lowered and "product" in lowered:
        preferred = ["core.orders", "core.order_items", "core.products", "core.payments"]
        return [table for table in preferred if table in available_tables]

    selected = [table for table, score in sorted(scores.items(), key=lambda item: (-item[1], item[0])) if score > 0]
    if selected:
        return selected[:6]

    preferred_fallback = ["core.orders", "core.order_items", "core.products", "mart.sales_daily"]
    fallback = [table for table in preferred_fallback if table in available_tables]
    return fallback or available_tables[:3]


def _tables_from_retrieved_context(
    retrieved_context: list[dict[str, Any]],
    available_tables: list[str],
) -> list[str]:
    available = set(available_tables)
    selected = []
    for item in sorted(retrieved_context, key=lambda entry: float(entry.get("score") or 0.0), reverse=True):
        for table_name in item.get("tables") or []:
            if table_name in available and table_name not in selected:
                selected.append(table_name)
    return selected
