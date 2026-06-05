from __future__ import annotations

from datetime import date, datetime
import re

from sql_rag_agent.llm import LLMProviderProtocol
from sql_rag_agent.state import SQLAgentState
from sql_rag_agent.tracing import TraceWriter


def generate_sql(
    state: SQLAgentState,
    current_date: str | date | None = None,
    llm_provider: LLMProviderProtocol | None = None,
    trace_writer: TraceWriter | None = None,
) -> SQLAgentState:
    question = state["question"].lower()
    selected_tables = state.get("selected_tables", [])
    current = _coerce_date(current_date)

    llm_candidate = _generate_with_llm(state, llm_provider, trace_writer)
    if llm_candidate is not None:
        return {**state, "candidate_sql": [llm_candidate]}

    requires_product_revenue_tables = "revenue" in question and "product" in question
    requires_refund_tables = _is_refund_customer_count_question(question)

    if requires_product_revenue_tables and not {"core.orders", "core.order_items", "core.products"}.issubset(set(selected_tables)):
        return _unsupported_question_state(
            state,
            "No phase-1 SQL pattern matched because the selected tables do not include core.orders, core.order_items, and core.products.",
        )

    if requires_refund_tables and not {"core.returns", "core.order_items", "core.orders"}.issubset(set(selected_tables)):
        return _unsupported_question_state(
            state,
            "No phase-1 SQL pattern matched because the selected tables do not include core.returns, core.order_items, and core.orders.",
        )

    if requires_product_revenue_tables and {"core.orders", "core.order_items", "core.products"}.issubset(set(selected_tables)):
        start_date, end_date, time_summary = _date_bounds_for_question(question, current)
        where_parts = [
            "o.order_date >= DATE '{start}'".format(start=start_date.isoformat()),
            "o.order_date < DATE '{end}'".format(end=end_date.isoformat()),
        ]
        sql = (
            "SELECT p.product_name, "
            "SUM((oi.quantity * oi.unit_price) - oi.discount_amount) AS revenue "
            "FROM core.orders AS o "
            "JOIN core.order_items AS oi ON oi.order_id = o.order_id "
            "JOIN core.products AS p ON p.product_id = oi.product_id "
            f"WHERE {' AND '.join(where_parts)} "
            "GROUP BY p.product_name "
            "ORDER BY revenue DESC "
            "LIMIT 1"
        )
        candidate = {
            "candidate_id": "candidate_1",
            "sql": sql,
            "reasoning_summary": (
                "Ranks products by order-item revenue after item-level discounts"
                f" using {time_summary}."
            ),
            "expected_result_shape": ["product_name", "revenue"],
            "filters": where_parts,
        }
    elif requires_refund_tables and {"core.returns", "core.order_items", "core.orders"}.issubset(set(selected_tables)):
        start_date, end_date, time_summary = _date_bounds_for_question(question, current)
        where_parts = [
            f"r.return_date >= DATE '{start_date.isoformat()}'",
            f"r.return_date < DATE '{end_date.isoformat()}'",
        ]
        sql = (
            "SELECT COUNT(DISTINCT o.customer_id) AS customer_count "
            "FROM core.returns AS r "
            "JOIN core.order_items AS oi ON oi.order_item_id = r.order_item_id "
            "JOIN core.orders AS o ON o.order_id = oi.order_id "
            f"WHERE {' AND '.join(where_parts)}"
        )
        candidate = {
            "candidate_id": "candidate_1",
            "sql": sql,
            "reasoning_summary": f"Counts distinct customers with returns using {time_summary}.",
            "expected_result_shape": ["customer_count"],
            "filters": where_parts,
            "answer_label": "refunded customers",
        }
    elif "revenue" in question and "mart.sales_daily" in selected_tables:
        start_date, end_date, time_summary = _date_bounds_for_question(question, current)
        sql = (
            "SELECT SUM(sd.revenue) AS revenue "
            "FROM mart.sales_daily AS sd "
            f"WHERE sd.sales_date >= DATE '{start_date.isoformat()}' "
            f"AND sd.sales_date < DATE '{end_date.isoformat()}'"
        )
        candidate = {
            "candidate_id": "candidate_1",
            "sql": sql,
            "reasoning_summary": f"Sums daily mart revenue using {time_summary}.",
            "expected_result_shape": ["revenue"],
            "filters": [
                f"sd.sales_date >= DATE '{start_date.isoformat()}'",
                f"sd.sales_date < DATE '{end_date.isoformat()}'",
            ],
        }
    elif "customer" in question and "core.customers" in selected_tables:
        candidate = {
            "candidate_id": "candidate_1",
            "sql": "SELECT COUNT(*) AS customer_count FROM core.customers AS c",
            "reasoning_summary": "Counts customers in the normalized customer table.",
            "expected_result_shape": ["customer_count"],
            "filters": [],
        }
    else:
        return _unsupported_question_state(
            state,
            "No phase-1 SQL pattern matched this question. Ask about supported ecommerce metrics such as customers, refunds, or revenue.",
        )

    return {**state, "candidate_sql": [candidate]}


def _unsupported_question_state(state: SQLAgentState, message: str) -> SQLAgentState:
    errors = list(state.get("errors", []))
    errors.append(
        {
            "node": "generate_sql",
            "code": "unsupported_question",
            "message": message,
        }
    )
    return {**state, "candidate_sql": [], "errors": errors}


def _generate_with_llm(
    state: SQLAgentState,
    llm_provider: LLMProviderProtocol | None,
    trace_writer: TraceWriter | None,
) -> dict | None:
    if llm_provider is None:
        return None

    try:
        candidate = llm_provider.generate_sql_candidate(
            question=state["question"],
            question_analysis=state.get("question_analysis", {}),
            schema_context=state.get("schema_context", []),
            selected_tables=state.get("selected_tables", []),
            retrieved_context=state.get("retrieved_context", []),
        )
    except TypeError as exc:
        if "retrieved_context" not in str(exc):
            raise
        candidate = llm_provider.generate_sql_candidate(
            question=state["question"],
            question_analysis=state.get("question_analysis", {}),
            schema_context=state.get("schema_context", []),
            selected_tables=state.get("selected_tables", []),
        )
    except Exception as exc:
        if trace_writer:
            trace_writer.write("llm_generate_sql_error", {"error": str(exc)})
        return None

    if candidate and trace_writer:
        trace_writer.write(
            "llm_generate_sql",
            {
                "question": state["question"],
                "selected_tables": state.get("selected_tables", []),
                "retrieved_context": state.get("retrieved_context", []),
                "candidate": candidate,
            },
        )
    return candidate


def _coerce_date(value: str | date | None) -> date:
    if value is None:
        return date.today()
    if isinstance(value, date):
        return value
    return datetime.strptime(value, "%Y-%m-%d").date()


def _date_bounds_for_question(question: str, current_date: date) -> tuple[date, date, str]:
    explicit_range = _extract_explicit_date_range(question)
    if explicit_range is not None:
        start, end_inclusive = explicit_range
        end_exclusive = end_inclusive.fromordinal(end_inclusive.toordinal() + 1)
        return start, end_exclusive, (
            f"the explicit date range {start.isoformat()} to {end_inclusive.isoformat()}"
        )

    if "last quarter" in question:
        current_quarter = (current_date.month - 1) // 3 + 1
        last_quarter = current_quarter - 1
        year = current_date.year
        if last_quarter == 0:
            last_quarter = 4
            year -= 1
        start_month = (last_quarter - 1) * 3 + 1
        start = date(year, start_month, 1)
        end_month = start_month + 3
        end = date(year + 1, 1, 1) if end_month == 13 else date(year, end_month, 1)
        return start, end, f"last quarter ({start.isoformat()} to {end.isoformat()}, exclusive end)"

    year = current_date.year
    return date(year, 1, 1), date(year + 1, 1, 1), f"calendar year {year}"


def _extract_explicit_date_range(question: str) -> tuple[date, date] | None:
    match = re.search(
        r"(\d{1,2}/\d{1,2}/\d{4})\s*-\s*(\d{1,2}/\d{1,2}/\d{4})",
        question,
    )
    if not match:
        return None

    start = datetime.strptime(match.group(1), "%d/%m/%Y").date()
    end = datetime.strptime(match.group(2), "%d/%m/%Y").date()
    if end < start:
        start, end = end, start
    return start, end


def _is_refund_customer_count_question(question: str) -> bool:
    return (
        "customer" in question
        and any(term in question for term in ["refund", "refunded", "return", "returned"])
    )
