from __future__ import annotations

import re
from typing import Any


BLOCKED_KEYWORDS = {
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "ALTER",
    "TRUNCATE",
    "CREATE",
    "GRANT",
    "REVOKE",
    "COPY",
    "CALL",
    "DO",
}


def validate_sql_candidate(
    candidate: dict[str, Any],
    schema_context: list[dict[str, Any]],
    question_analysis: dict[str, Any],
) -> dict[str, Any]:
    sql = candidate.get("sql", "")
    errors: list[dict[str, Any]] = []
    normalized = _normalize_sql(sql)
    upper_sql = normalized.upper()

    if not (upper_sql.startswith("SELECT ") or upper_sql.startswith("WITH ")):
        errors.append({"code": "not_select", "message": "Only read-only SELECT queries are allowed."})

    found_blocked = sorted(keyword for keyword in BLOCKED_KEYWORDS if re.search(rf"\b{keyword}\b", upper_sql))
    if found_blocked:
        errors.append(
            {
                "code": "destructive_keyword",
                "message": f"SQL contains destructive or unsafe keyword(s): {', '.join(found_blocked)}.",
            }
        )

    if _has_multiple_statements(normalized):
        errors.append({"code": "multiple_statements", "message": "SQL must contain a single statement."})

    if re.search(r"SELECT\s+\*", upper_sql) or re.search(r"\.\*", upper_sql):
        errors.append({"code": "select_star", "message": "SQL must not use SELECT *."})

    known_tables = {table["table_name"] for table in schema_context}
    referenced_tables = _extract_tables(normalized)
    missing_tables = sorted(table for table in referenced_tables if table not in known_tables)
    if missing_tables:
        errors.append(
            {
                "code": "unknown_table",
                "message": f"SQL references unknown table(s): {', '.join(missing_tables)}.",
            }
        )

    if question_analysis.get("requires_time_filter") and not _has_explicit_date_filter(upper_sql):
        errors.append(
            {
                "code": "missing_time_filter",
                "message": "Time-bounded questions require explicit date filters.",
            }
        )

    if _has_aggregation_without_group_by(upper_sql):
        errors.append(
            {
                "code": "missing_group_by",
                "message": "Aggregated queries with selected dimensions must include GROUP BY.",
            }
        )

    validated = dict(candidate)
    validated["is_valid"] = not errors
    validated["errors"] = errors
    return validated


def _normalize_sql(sql: str) -> str:
    return re.sub(r"\s+", " ", sql.strip())


def _has_multiple_statements(sql: str) -> bool:
    stripped = sql.strip()
    if stripped.endswith(";"):
        stripped = stripped[:-1]
    return ";" in stripped


def _extract_tables(sql: str) -> set[str]:
    tables: set[str] = set()
    pattern = re.compile(r"\b(?:FROM|JOIN)\s+([A-Za-z_][\w]*\.[A-Za-z_][\w]*)", re.IGNORECASE)
    for match in pattern.finditer(sql):
        tables.add(match.group(1))
    return tables


def _has_explicit_date_filter(upper_sql: str) -> bool:
    return bool(
        re.search(r"\bDATE\s+'?\d{4}-\d{2}-\d{2}'?", upper_sql)
        or re.search(r"\d{4}-\d{2}-\d{2}", upper_sql)
    )


def _has_aggregation_without_group_by(upper_sql: str) -> bool:
    has_aggregate = bool(re.search(r"\b(SUM|AVG|COUNT|MIN|MAX)\s*\(", upper_sql))
    if not has_aggregate or " GROUP BY " in upper_sql:
        return False
    select_clause = upper_sql.split(" FROM ", 1)[0]
    return "," in select_clause and "COUNT(*)" not in select_clause

