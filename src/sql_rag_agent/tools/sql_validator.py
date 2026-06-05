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
    allowed_tables: list[str] | None = None,
) -> dict[str, Any]:
    del schema_context
    del question_analysis

    sql = candidate.get("sql", "")
    errors: list[dict[str, Any]] = []
    upper_sql = _normalize_sql(sql).upper()

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

    if allowed_tables:
        referenced_tables = _schema_qualified_tables(sql)
        disallowed_tables = sorted(table for table in referenced_tables if table not in set(allowed_tables))
        if disallowed_tables:
            errors.append(
                {
                    "code": "table_outside_allowed_scope",
                    "message": (
                        "SQL references table(s) outside the selected UI scope: "
                        + ", ".join(disallowed_tables)
                        + "."
                    ),
                }
            )

    validated = dict(candidate)
    validated["is_valid"] = not errors
    validated["errors"] = errors
    return validated


def _normalize_sql(sql: str) -> str:
    return re.sub(r"\s+", " ", sql.strip())


def _schema_qualified_tables(sql: str) -> set[str]:
    return {
        f"{match.group(1)}.{match.group(2)}"
        for match in re.finditer(r"\b(core|mart|stg)\.([A-Za-z_][A-Za-z0-9_]*)\b", sql)
    }
