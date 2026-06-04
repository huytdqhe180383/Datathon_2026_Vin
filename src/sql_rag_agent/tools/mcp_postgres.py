from __future__ import annotations

from decimal import Decimal
from typing import Any, Protocol

import psycopg
from psycopg.rows import dict_row

from sql_rag_agent.config import (
    DEFAULT_ROW_LIMIT,
    DEFAULT_STATEMENT_TIMEOUT_MS,
    DatabaseConfig,
)


class PostgresMCPToolProtocol(Protocol):
    def list_tables(self) -> list[str]: ...

    def describe_table(self, table_name: str) -> dict[str, Any]: ...

    def get_foreign_keys(self, table_name: str) -> list[dict[str, Any]]: ...

    def get_sample_rows(self, table_name: str, limit: int = 3) -> list[dict[str, Any]]: ...

    def execute_sql(
        self,
        sql: str,
        limit: int = DEFAULT_ROW_LIMIT,
        statement_timeout_ms: int = DEFAULT_STATEMENT_TIMEOUT_MS,
    ) -> list[dict[str, Any]]: ...


class PostgresMCPTool:
    """Small MCP-style wrapper around read-only PostgreSQL operations."""

    def __init__(self, config: DatabaseConfig | None = None):
        self.config = config or DatabaseConfig.from_env()

    def _connect(self):
        return psycopg.connect(**self.config.to_psycopg_kwargs(), row_factory=dict_row)

    def list_tables(self) -> list[str]:
        sql = """
            SELECT table_schema || '.' || table_name AS table_name
            FROM information_schema.tables
            WHERE table_schema IN ('core', 'mart', 'stg')
              AND table_type = 'BASE TABLE'
            ORDER BY table_schema, table_name
        """
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(sql)
            return [row["table_name"] for row in cur.fetchall()]

    def describe_table(self, table_name: str) -> dict[str, Any]:
        schema_name, bare_table = _split_table_name(table_name)
        columns_sql = """
            SELECT
                column_name AS name,
                data_type AS type,
                is_nullable = 'YES' AS nullable
            FROM information_schema.columns
            WHERE table_schema = %s
              AND table_name = %s
            ORDER BY ordinal_position
        """
        pk_sql = """
            SELECT kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            WHERE tc.table_schema = %s
              AND tc.table_name = %s
              AND tc.constraint_type = 'PRIMARY KEY'
            ORDER BY kcu.ordinal_position
        """
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(columns_sql, (schema_name, bare_table))
            columns = [
                {
                    "name": row["name"],
                    "type": row["type"],
                    "nullable": row["nullable"],
                    "description": None,
                }
                for row in cur.fetchall()
            ]
            cur.execute(pk_sql, (schema_name, bare_table))
            primary_keys = [row["column_name"] for row in cur.fetchall()]

        return {
            "table_name": table_name,
            "columns": columns,
            "primary_keys": primary_keys,
            "foreign_keys": self.get_foreign_keys(table_name),
            "sample_rows": self.get_sample_rows(table_name),
        }

    def get_foreign_keys(self, table_name: str) -> list[dict[str, Any]]:
        schema_name, bare_table = _split_table_name(table_name)
        sql = """
            SELECT
                kcu.column_name AS column,
                ccu.table_schema || '.' || ccu.table_name AS references_table,
                ccu.column_name AS references_column
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage ccu
              ON ccu.constraint_name = tc.constraint_name
             AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_schema = %s
              AND tc.table_name = %s
            ORDER BY kcu.column_name
        """
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(sql, (schema_name, bare_table))
            return [dict(row) for row in cur.fetchall()]

    def get_sample_rows(self, table_name: str, limit: int = 3) -> list[dict[str, Any]]:
        schema_name, bare_table = _split_table_name(table_name)
        limit = max(0, min(int(limit), 10))
        sql = f'SELECT * FROM "{schema_name}"."{bare_table}" LIMIT {limit}'
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(sql)
            return [_json_ready(dict(row)) for row in cur.fetchall()]

    def execute_sql(
        self,
        sql: str,
        limit: int = DEFAULT_ROW_LIMIT,
        statement_timeout_ms: int = DEFAULT_STATEMENT_TIMEOUT_MS,
    ) -> list[dict[str, Any]]:
        timeout = max(1, int(statement_timeout_ms))
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(f"SET LOCAL statement_timeout = {timeout}")
            cur.execute(sql)
            rows = cur.fetchmany(max(1, int(limit)))
            return [_json_ready(dict(row)) for row in rows]


def _split_table_name(table_name: str) -> tuple[str, str]:
    parts = table_name.split(".", 1)
    if len(parts) != 2:
        raise ValueError(f"Expected schema-qualified table name, got {table_name!r}")
    return parts[0], parts[1]


def _json_ready(row: dict[str, Any]) -> dict[str, Any]:
    converted = {}
    for key, value in row.items():
        if isinstance(value, Decimal):
            converted[key] = float(value)
        else:
            converted[key] = value
    return converted

