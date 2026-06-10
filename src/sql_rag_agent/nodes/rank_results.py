from __future__ import annotations

import re
from typing import Any

from sql_rag_agent.state import SQLAgentState
from sql_rag_agent.tracing import TraceWriter


def rank_results(
    state: SQLAgentState,
    trace_writer: TraceWriter | None = None,
) -> SQLAgentState:
    candidates = {candidate["candidate_id"]: candidate for candidate in state.get("validated_sql", [])}
    ranked = []
    for result in state.get("execution_results", []):
        candidate = candidates.get(result.get("candidate_id"), {})
        ranked.append(
            _score_candidate(
                question=state.get("question", ""),
                question_analysis=state.get("question_analysis", {}),
                retrieved_context=state.get("retrieved_context", []),
                candidate=candidate,
                result=result,
            )
        )

    ranked.sort(key=lambda item: item["score"], reverse=True)
    next_state = {**state, "ranked_results": ranked}
    if trace_writer:
        trace_writer.write("rank_results", {"ranked_results": ranked})
    return next_state


def _score_candidate(
    *,
    question: str,
    question_analysis: dict[str, Any],
    retrieved_context: list[dict[str, Any]],
    candidate: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    sql = str(result.get("sql") or candidate.get("sql") or "")
    rows = list(result.get("rows") or [])
    required_columns = _required_columns(question, candidate)
    result_columns = list(rows[0].keys()) if rows else []

    execution_score = 1.0 if result.get("error") is None else 0.0
    output_score = _output_contract_score(
        question=question,
        question_analysis=question_analysis,
        required_columns=required_columns,
        result_columns=result_columns,
        rows=rows,
        sql=sql,
    )
    business_score = _business_rule_score(question, retrieved_context, sql)
    simplicity_score = _simplicity_score(sql)

    score_breakdown = {
        "execution_success": round(execution_score, 4),
        "business_rule_match": round(business_score, 4),
        "output_contract_match": round(output_score, 4),
        "simplicity": round(simplicity_score, 4),
    }
    score = (
        execution_score * 40
        + business_score * 30
        + output_score * 25
        + simplicity_score * 5
    )

    return {
        "candidate_id": result.get("candidate_id") or candidate.get("candidate_id"),
        "score": round(score, 4),
        "score_breakdown": score_breakdown,
        "reason": _ranking_reason(score_breakdown),
        "sql": sql,
        "row_count": result.get("row_count", len(rows)),
        "error": result.get("error"),
    }


def _required_columns(question: str, candidate: dict[str, Any]) -> list[str]:
    match = re.search(r"(?:columns?|including columns?)\s+(.+?)(?:\.|$)", question, re.IGNORECASE)
    if match:
        text = match.group(1)
        text = re.sub(r"\band\b", ",", text, flags=re.IGNORECASE)
        return [part.strip(" `\"") for part in text.split(",") if part.strip(" `\"")]

    shape = candidate.get("expected_result_shape") or []
    if isinstance(shape, dict):
        columns = shape.get("columns") or []
        return [str(column) for column in columns]
    return [str(column) for column in shape]


def _output_contract_score(
    *,
    question: str,
    question_analysis: dict[str, Any],
    required_columns: list[str],
    result_columns: list[str],
    rows: list[dict[str, Any]],
    sql: str,
) -> float:
    checks = []
    if required_columns:
        checks.append(set(required_columns).issubset(set(result_columns)))
    else:
        checks.append(bool(result_columns) or not rows)

    lowered_question = question.lower()
    lowered_sql = sql.lower()
    if any(term in lowered_question for term in ["rate", "share", "percentage", "percent"]):
        checks.append(("* 100" in lowered_sql or "100.0" in lowered_sql) and any(column.endswith("_pct") for column in result_columns))

    if "month" in lowered_question:
        checks.append("to_char" in lowered_sql or any(_looks_like_year_month(value) for row in rows for value in row.values()))

    if question_analysis.get("expected_answer_type") == "table":
        checks.append(len(rows) >= 1)

    return sum(1 for check in checks if check) / len(checks) if checks else 1.0


def _business_rule_score(question: str, retrieved_context: list[dict[str, Any]], sql: str) -> float:
    lowered_question = question.lower()
    lowered_context = "\n".join(str(item.get("content", "")) for item in retrieved_context).lower()
    lowered_sql = sql.lower()
    checks = []

    if "net revenue" in lowered_question or "order value" in lowered_question:
        uses_item_net = all(term in lowered_sql for term in ["quantity", "unit_price", "discount_amount"])
        uses_payment_refund = any(term in lowered_sql for term in ["payment_value", "refund_amount", "core.returns"])
        checks.append(uses_item_net and ("do not subtract" not in lowered_context or not uses_payment_refund))

    if "promo" in lowered_question:
        uses_promo_contract = any(term in lowered_sql for term in ["promo_id", "order_item_promotions", "promo_code"])
        checks.append(uses_promo_contract and "discount_amount > 0" not in lowered_sql)

    if "return rate" in lowered_question or "returned quantity" in lowered_question:
        checks.append("order_status = 'returned'" in lowered_sql and "core.returns" not in lowered_sql)

    if "repeat-customer rate" in lowered_question or "repeat customer rate" in lowered_question:
        checks.append("join core.orders" in lowered_sql and "left join core.orders" not in lowered_sql)

    if "top 10%" in lowered_question:
        checks.append("row_number" in lowered_sql and "ceil" in lowered_sql and "ntile" not in lowered_sql)

    if "order-size buckets" in lowered_question or "unit_bucket" in lowered_question:
        checks.append("4 and 6" in lowered_sql and "7 and 10" in lowered_sql)

    return sum(1 for check in checks if check) / len(checks) if checks else 0.75


def _simplicity_score(sql: str) -> float:
    joins = len(re.findall(r"\bjoin\b", sql, flags=re.IGNORECASE))
    ctes = len(re.findall(r"\bas\s*\(", sql, flags=re.IGNORECASE))
    penalty = min(0.6, joins * 0.06 + ctes * 0.04)
    return max(0.4, 1.0 - penalty)


def _looks_like_year_month(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}", value) is not None


def _ranking_reason(score_breakdown: dict[str, float]) -> str:
    return (
        "Scored by execution success, retrieved business-rule fit, "
        "requested output-contract fit, and SQL simplicity. "
        f"Breakdown: {score_breakdown}."
    )
