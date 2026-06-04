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
    selected_tables = _select_tables(state["question"], available_tables)
    schema_context: list[dict[str, Any]] = []

    errors = list(state.get("errors", []))
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


def _select_tables(question: str, available_tables: list[str]) -> list[str]:
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
