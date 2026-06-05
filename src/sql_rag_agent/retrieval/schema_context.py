from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from sql_rag_agent.config import SchemaRetrievalConfig
from sql_rag_agent.tools.mcp_postgres import PostgresMCPTool, PostgresMCPToolProtocol

LOW_CARDINALITY_COLUMNS = {
    "order_status",
    "payment_method",
    "device_type",
    "order_source",
    "return_reason",
}


class SchemaRetrieverProtocol(Protocol):
    def retrieve(
        self,
        *,
        question: str,
        allowed_tables: list[str] | None = None,
    ) -> list[dict[str, Any]]: ...


class LlamaIndexSchemaRetriever:
    def __init__(
        self,
        config: SchemaRetrievalConfig | None = None,
        mcp_tool: PostgresMCPToolProtocol | None = None,
    ):
        self.config = config or SchemaRetrievalConfig.from_env()
        self.mcp_tool = mcp_tool or PostgresMCPTool()

    def retrieve(
        self,
        *,
        question: str,
        allowed_tables: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        if not self.config.enabled:
            return []

        index = self._load_or_build_index()
        retriever = index.as_retriever(similarity_top_k=max(1, self.config.top_k))
        nodes = retriever.retrieve(question)
        context = [_context_from_node(node) for node in nodes]
        return filter_context_by_allowed_tables(context, allowed_tables or [])

    def _load_or_build_index(self):
        from llama_index.core import StorageContext, VectorStoreIndex, load_index_from_storage
        from llama_index.core.settings import Settings
        from llama_index.embeddings.openai import OpenAIEmbedding

        kwargs: dict[str, Any] = {
            "model": self.config.embedding_model,
        }
        if self.config.api_key:
            kwargs["api_key"] = self.config.api_key
        if self.config.base_url:
            kwargs["api_base"] = self.config.base_url
        Settings.embed_model = OpenAIEmbedding(**kwargs)
        Settings.llm = None

        index_dir = self.config.index_dir
        if _has_persisted_index(index_dir):
            storage_context = StorageContext.from_defaults(persist_dir=str(index_dir))
            return load_index_from_storage(storage_context)

        documents = self._build_documents()
        index = VectorStoreIndex.from_documents(documents)
        index_dir.mkdir(parents=True, exist_ok=True)
        index.storage_context.persist(persist_dir=str(index_dir))
        return index

    def _build_documents(self):
        from llama_index.core import Document

        documents = []
        for item in build_schema_context_entries(self.mcp_tool):
            documents.append(
                Document(
                    text=item["content"],
                    metadata={
                        "type": item["type"],
                        "name": item["name"],
                        "source": item["source"],
                        "tables": item.get("tables", []),
                        "columns": item.get("columns", []),
                    },
                )
            )
        for item in load_manual_context_entries(self.config.docs_dir):
            documents.append(
                Document(
                    text=item["content"],
                    metadata={
                        "type": item["type"],
                        "name": item["name"],
                        "source": item["source"],
                        "tables": item.get("tables", []),
                        "columns": item.get("columns", []),
                    },
                )
            )
        return documents


def build_schema_context_entries(mcp_tool: PostgresMCPToolProtocol) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for table_name in mcp_tool.list_tables():
        table = mcp_tool.describe_table(table_name)
        columns = table.get("columns", [])
        column_names = [column["name"] for column in columns]
        lines = [
            f"Table {table_name}.",
            "Columns: " + ", ".join(f"{column['name']} ({column['type']})" for column in columns),
        ]
        if table.get("primary_keys"):
            lines.append("Primary keys: " + ", ".join(table["primary_keys"]))
        for fk in table.get("foreign_keys", []):
            lines.append(f"Join rule: {table_name}.{fk['column']} -> {fk['references_table']}.{fk['references_column']}.")
        samples = table.get("sample_rows", [])
        if samples:
            lines.append(f"Sample rows: {samples[:3]}.")
        value_lines = _distinct_value_lines(mcp_tool, table_name, column_names)
        lines.extend(value_lines)
        entries.append(
            {
                "type": "table_schema",
                "name": table_name,
                "content": "\n".join(lines),
                "score": 1.0,
                "source": "postgres_schema",
                "tables": [table_name],
                "columns": [f"{table_name}.{column}" for column in column_names],
            }
        )
    return entries


def load_manual_context_entries(docs_dir: Path) -> list[dict[str, Any]]:
    if not docs_dir.exists():
        return []

    entries = []
    for path in sorted(docs_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            continue
        entries.append(
            {
                "type": "semantic_doc",
                "name": path.stem,
                "content": text,
                "score": 1.0,
                "source": str(path),
                "tables": _known_tables_in_text(text),
                "columns": [],
            }
        )
    return entries


def filter_context_by_allowed_tables(
    context: list[dict[str, Any]],
    allowed_tables: list[str] | None,
) -> list[dict[str, Any]]:
    if not allowed_tables:
        return context

    allowed = set(allowed_tables)
    filtered = []
    for item in context:
        tables = set(item.get("tables") or [])
        if tables and tables.issubset(allowed):
            filtered.append(item)
    return filtered


def _context_from_node(node: Any) -> dict[str, Any]:
    metadata = dict(getattr(node, "metadata", {}) or {})
    text = getattr(node, "text", None)
    if text is None and hasattr(node, "get_content"):
        text = node.get_content()
    score = getattr(node, "score", None)
    return {
        "type": metadata.get("type") or "semantic_doc",
        "name": metadata.get("name") or "retrieved_context",
        "content": str(text or ""),
        "score": float(score) if score is not None else 0.0,
        "source": metadata.get("source") or "",
        "tables": list(metadata.get("tables") or []),
        "columns": list(metadata.get("columns") or []),
    }


def _distinct_value_lines(
    mcp_tool: PostgresMCPToolProtocol,
    table_name: str,
    column_names: list[str],
) -> list[str]:
    lines = []
    schema_name, bare_table = table_name.split(".", 1)
    for column_name in column_names:
        if column_name not in LOW_CARDINALITY_COLUMNS:
            continue
        sql = (
            f'SELECT DISTINCT "{column_name}" AS value '
            f'FROM "{schema_name}"."{bare_table}" '
            f'WHERE "{column_name}" IS NOT NULL '
            f'ORDER BY "{column_name}" LIMIT 25'
        )
        try:
            rows = mcp_tool.execute_sql(sql, limit=25)
        except Exception:
            continue
        values = [str(row["value"]) for row in rows if row.get("value") is not None]
        if values:
            lines.append(f"Known values for {table_name}.{column_name}: {', '.join(values)}.")
    return lines


def _known_tables_in_text(text: str) -> list[str]:
    tables = set()
    for schema in ("core", "mart", "stg"):
        marker = f"{schema}."
        for token in text.replace("`", " ").replace(",", " ").split():
            if token.startswith(marker):
                tables.add(token.strip(".,;:()[]"))
    return sorted(tables)


def _has_persisted_index(index_dir: Path) -> bool:
    return index_dir.exists() and any(index_dir.iterdir())
