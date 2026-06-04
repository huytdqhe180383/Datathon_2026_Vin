from decimal import Decimal
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "src"))

from sql_rag_agent.config import DatabaseConfig
from sql_rag_agent.graph import run_agent
from sql_rag_agent.nodes.understand_question import understand_question
from sql_rag_agent.tracing import TraceWriter
from sql_rag_agent.tools.sql_validator import validate_sql_candidate
from sql_rag_agent.ui import answer_question


class FakePostgresMCPTool:
    def __init__(self):
        self.executed_sql = []

    def list_tables(self):
        return [
            "core.customers",
            "core.orders",
            "core.order_items",
            "core.products",
            "core.payments",
            "core.returns",
            "mart.sales_daily",
        ]

    def describe_table(self, table_name):
        columns_by_table = {
            "core.orders": [
                {"name": "order_id", "type": "integer", "nullable": False, "description": None},
                {"name": "order_date", "type": "date", "nullable": False, "description": None},
                {"name": "customer_id", "type": "integer", "nullable": False, "description": None},
                {"name": "order_status", "type": "text", "nullable": False, "description": None},
            ],
            "core.customers": [
                {"name": "customer_id", "type": "integer", "nullable": False, "description": None},
                {"name": "signup_date", "type": "date", "nullable": False, "description": None},
                {"name": "acquisition_channel", "type": "text", "nullable": False, "description": None},
            ],
            "core.order_items": [
                {"name": "order_item_id", "type": "integer", "nullable": False, "description": None},
                {"name": "order_id", "type": "integer", "nullable": False, "description": None},
                {"name": "product_id", "type": "integer", "nullable": False, "description": None},
                {"name": "quantity", "type": "integer", "nullable": False, "description": None},
                {"name": "unit_price", "type": "numeric", "nullable": False, "description": None},
                {"name": "discount_amount", "type": "numeric", "nullable": False, "description": None},
            ],
            "core.products": [
                {"name": "product_id", "type": "integer", "nullable": False, "description": None},
                {"name": "product_name", "type": "text", "nullable": False, "description": None},
                {"name": "category", "type": "text", "nullable": False, "description": None},
            ],
            "core.payments": [
                {"name": "payment_id", "type": "integer", "nullable": False, "description": None},
                {"name": "order_id", "type": "integer", "nullable": False, "description": None},
                {"name": "payment_value", "type": "numeric", "nullable": False, "description": None},
            ],
            "core.returns": [
                {"name": "return_id", "type": "integer", "nullable": False, "description": None},
                {"name": "order_item_id", "type": "integer", "nullable": False, "description": None},
                {"name": "return_date", "type": "date", "nullable": False, "description": None},
                {"name": "refund_amount", "type": "numeric", "nullable": False, "description": None},
            ],
            "mart.sales_daily": [
                {"name": "sales_date", "type": "date", "nullable": False, "description": None},
                {"name": "revenue", "type": "numeric", "nullable": False, "description": None},
                {"name": "cogs", "type": "numeric", "nullable": False, "description": None},
            ],
        }
        return {
            "table_name": table_name,
            "columns": columns_by_table[table_name],
            "primary_keys": [columns_by_table[table_name][0]["name"]],
            "foreign_keys": self.get_foreign_keys(table_name),
            "sample_rows": [],
        }

    def get_foreign_keys(self, table_name):
        relationships = {
            "core.order_items": [
                {
                    "column": "order_id",
                    "references_table": "core.orders",
                    "references_column": "order_id",
                },
                {
                    "column": "product_id",
                    "references_table": "core.products",
                    "references_column": "product_id",
                },
            ],
            "core.payments": [
                {
                    "column": "order_id",
                    "references_table": "core.orders",
                    "references_column": "order_id",
                }
            ],
            "core.orders": [
                {
                    "column": "customer_id",
                    "references_table": "core.customers",
                    "references_column": "customer_id",
                }
            ],
            "core.returns": [
                {
                    "column": "order_item_id",
                    "references_table": "core.order_items",
                    "references_column": "order_item_id",
                }
            ],
        }
        return relationships.get(table_name, [])

    def get_sample_rows(self, table_name, limit=3):
        return []

    def execute_sql(self, sql, limit=100, statement_timeout_ms=5000):
        self.executed_sql.append(sql)
        if "core.returns" in sql and "COUNT(DISTINCT o.customer_id)" in sql:
            return [
                {
                    "customer_count": 42,
                }
            ]
        return [
            {
                "product_name": "Product A",
                "revenue": Decimal("128400.00"),
            }
        ]


class FakeLLMProvider:
    def __init__(self):
        self.sql_requests = []
        self.answer_requests = []

    def generate_sql_candidate(self, *, question, question_analysis, schema_context, selected_tables):
        self.sql_requests.append(
            {
                "question": question,
                "question_analysis": question_analysis,
                "schema_context": schema_context,
                "selected_tables": selected_tables,
            }
        )
        return {
            "candidate_id": "candidate_1",
            "sql": "SELECT COUNT(*) AS customer_count FROM core.customers AS c",
            "reasoning_summary": "LLM selected the normalized customer table.",
            "expected_result_shape": ["customer_count"],
            "filters": [],
        }

    def compose_answer(self, *, question, candidate, execution_result, selected_tables):
        self.answer_requests.append(
            {
                "question": question,
                "candidate": candidate,
                "execution_result": execution_result,
                "selected_tables": selected_tables,
            }
        )
        return "LLM answer: there are 121,930 customers in core.customers."


def test_understand_question_detects_ranking_revenue_and_time_filter():
    state = understand_question(
        {"question": "Which product had the highest revenue last quarter?"}
    )

    analysis = state["question_analysis"]
    assert analysis["question_type"] == "ranking"
    assert analysis["expected_answer_type"] == "ranked_list"
    assert analysis["requires_time_filter"] is True
    assert analysis["requires_join"] is True
    assert analysis["requires_metric_definition"] is True
    assert analysis["ambiguities"] == ["last quarter depends on the current date"]


def test_sql_validator_blocks_unsafe_sql_and_accepts_known_read_only_query():
    schema_context = [
        FakePostgresMCPTool().describe_table("core.orders"),
        FakePostgresMCPTool().describe_table("core.order_items"),
        FakePostgresMCPTool().describe_table("core.products"),
    ]

    unsafe = validate_sql_candidate(
        {
            "candidate_id": "candidate_1",
            "sql": "DROP TABLE core.orders",
            "reasoning_summary": "bad",
            "expected_result_shape": [],
        },
        schema_context=schema_context,
        question_analysis={"requires_time_filter": False},
    )
    assert unsafe["is_valid"] is False
    assert any("destructive" in error["message"] for error in unsafe["errors"])

    star = validate_sql_candidate(
        {
            "candidate_id": "candidate_2",
            "sql": "SELECT * FROM core.orders LIMIT 10",
            "reasoning_summary": "bad",
            "expected_result_shape": [],
        },
        schema_context=schema_context,
        question_analysis={"requires_time_filter": False},
    )
    assert star["is_valid"] is False
    assert any("SELECT *" in error["message"] for error in star["errors"])

    valid = validate_sql_candidate(
        {
            "candidate_id": "candidate_3",
            "sql": (
                "SELECT p.product_name, "
                "SUM((oi.quantity * oi.unit_price) - oi.discount_amount) AS revenue "
                "FROM core.orders AS o "
                "JOIN core.order_items AS oi ON oi.order_id = o.order_id "
                "JOIN core.products AS p ON p.product_id = oi.product_id "
                "WHERE o.order_date >= DATE '2026-01-01' "
                "AND o.order_date < DATE '2026-04-01' "
                "GROUP BY p.product_name "
                "ORDER BY revenue DESC "
                "LIMIT 1"
            ),
            "reasoning_summary": "Ranks products by order item revenue.",
            "expected_result_shape": ["product_name", "revenue"],
        },
        schema_context=schema_context,
        question_analysis={"requires_time_filter": True},
    )
    assert valid["is_valid"] is True
    assert valid["errors"] == []


def test_run_agent_executes_validated_query_and_composes_grounded_answer():
    tool = FakePostgresMCPTool()

    state = run_agent(
        "Which product had the highest revenue last quarter?",
        mcp_tool=tool,
        current_date="2026-06-04",
    )

    assert tool.executed_sql
    assert "DROP" not in tool.executed_sql[0].upper()
    assert state["validated_sql"][0]["candidate_id"] == "candidate_1"
    assert state["execution_results"][0]["row_count"] == 1
    assert state["confidence"] > 0.0
    assert "Product A" in state["final_answer"]
    assert "$128,400.00" in state["final_answer"]
    assert "core.orders" in state["final_answer"]


def test_run_agent_counts_refunded_customers_within_explicit_date_range():
    tool = FakePostgresMCPTool()

    state = run_agent(
        "How many customers refunded in 17/7/2017 - 17/8/2017",
        mcp_tool=tool,
        current_date="2026-06-04",
    )

    assert state["selected_tables"]
    assert "core.returns" in state["selected_tables"]
    assert "COUNT(DISTINCT o.customer_id)" in state["candidate_sql"][0]["sql"]
    assert "core.returns AS r" in state["candidate_sql"][0]["sql"]
    assert "DATE '2017-07-17'" in state["candidate_sql"][0]["sql"]
    assert "DATE '2017-08-18'" in state["candidate_sql"][0]["sql"]
    assert state["execution_results"][0]["rows"][0]["customer_count"] == 42
    assert "42 refunded customers" in state["final_answer"]


def test_run_agent_does_not_execute_fallback_sql_for_unsupported_question():
    tool = FakePostgresMCPTool()

    state = run_agent(
        "hello",
        mcp_tool=tool,
        current_date="2026-06-04",
    )

    assert tool.executed_sql == []
    assert state["candidate_sql"] == []
    assert "do not have enough information" in state["final_answer"]
    assert "646,945 rows" not in state["final_answer"]


def test_run_agent_uses_llm_for_sql_generation_answer_composition_and_tracing(tmp_path):
    tool = FakePostgresMCPTool()
    llm = FakeLLMProvider()
    trace_writer = TraceWriter(log_dir=tmp_path)

    state = run_agent(
        "How many customers are there?",
        mcp_tool=tool,
        llm_provider=llm,
        trace_writer=trace_writer,
        current_date="2026-06-04",
    )

    assert llm.sql_requests
    assert llm.answer_requests
    assert tool.executed_sql == ["SELECT COUNT(*) AS customer_count FROM core.customers AS c"]
    assert state["candidate_sql"][0]["reasoning_summary"] == "LLM selected the normalized customer table."
    assert state["final_answer"] == "LLM answer: there are 121,930 customers in core.customers."

    trace_files = list(tmp_path.glob("*.jsonl"))
    assert trace_files
    trace_text = trace_files[0].read_text(encoding="utf-8")
    assert '"event": "llm_generate_sql"' in trace_text
    assert '"event": "llm_compose_answer"' in trace_text
    assert '"event": "final_state"' in trace_text


def test_gradio_handler_returns_final_answer_from_injected_runner():
    def runner(question):
        return {"final_answer": f"answer for: {question}"}

    assert answer_question("How much revenue?", runner=runner) == "answer for: How much revenue?"
    assert answer_question(" ", runner=runner) == "Please enter a question."


def test_database_config_loads_pgpassword_from_dotenv(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("PGPASSWORD=from-dotenv\nPGDATABASE=dotenv_db\n", encoding="utf-8")

    monkeypatch.delenv("PGPASSWORD", raising=False)
    monkeypatch.delenv("PGDATABASE", raising=False)

    config = DatabaseConfig.from_env(env_file=env_file)

    assert config.password == "from-dotenv"
    assert config.dbname == "dotenv_db"
