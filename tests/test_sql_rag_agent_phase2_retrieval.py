from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "src"))

from sql_rag_agent.graph import run_agent
from sql_rag_agent.nodes.retrieve_schema_context import retrieve_schema_context
from sql_rag_agent.retrieval.schema_context import filter_context_by_allowed_tables


class FakePostgresMCPTool:
    def __init__(self):
        self.executed_sql = []
        self.described_tables = []

    def list_tables(self):
        return [
            "core.customers",
            "core.orders",
            "core.order_items",
            "core.returns",
        ]

    def describe_table(self, table_name):
        self.described_tables.append(table_name)
        columns_by_table = {
            "core.customers": [
                {"name": "customer_id", "type": "integer", "nullable": False, "description": None},
            ],
            "core.orders": [
                {"name": "order_id", "type": "integer", "nullable": False, "description": None},
                {"name": "order_date", "type": "date", "nullable": False, "description": None},
                {"name": "order_status", "type": "text", "nullable": False, "description": None},
            ],
            "core.order_items": [
                {"name": "order_item_id", "type": "integer", "nullable": False, "description": None},
                {"name": "order_id", "type": "integer", "nullable": False, "description": None},
            ],
            "core.returns": [
                {"name": "return_id", "type": "integer", "nullable": False, "description": None},
                {"name": "order_item_id", "type": "integer", "nullable": False, "description": None},
                {"name": "refund_amount", "type": "numeric", "nullable": False, "description": None},
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
        return [{"total_refunded_amount": 123.45, "combined_number": 7}]


class FakeSchemaRetriever:
    def __init__(self, fail=False):
        self.fail = fail
        self.requests = []

    def retrieve(self, *, question, allowed_tables=None):
        self.requests.append({"question": question, "allowed_tables": allowed_tables})
        if self.fail:
            raise RuntimeError("retriever unavailable")
        return [
            {
                "type": "business_rule",
                "name": "order_status_vocabulary",
                "content": "User word canceled maps to core.orders.order_status = 'cancelled'. Refunded orders may appear as returns or returned status.",
                "score": 0.91,
                "source": "docs/schema_context/ecommerce_semantics.md",
                "tables": ["core.orders", "core.returns", "core.order_items"],
                "columns": ["core.orders.order_status", "core.returns.refund_amount"],
            },
            {
                "type": "table_description",
                "name": "customers",
                "content": "Customer dimension only.",
                "score": 0.55,
                "source": "generated",
                "tables": ["core.customers"],
                "columns": ["core.customers.customer_id"],
            },
        ]


class ContextAwareLLMProvider:
    def __init__(self):
        self.sql_requests = []
        self.answer_requests = []

    def analyze_question(self, *, question):
        return {
            "question_type": "aggregate",
            "expected_answer_type": "number",
            "requires_time_filter": True,
            "requires_join": True,
            "requires_metric_definition": True,
            "ambiguities": [],
        }

    def generate_sql_candidate(
        self,
        *,
        question,
        question_analysis,
        schema_context,
        selected_tables,
        retrieved_context,
    ):
        self.sql_requests.append(
            {
                "question": question,
                "schema_context": schema_context,
                "selected_tables": selected_tables,
                "retrieved_context": retrieved_context,
            }
        )
        return {
            "candidate_id": "candidate_1",
            "sql": (
                "SELECT 123.45 AS total_refunded_amount, "
                "7 AS combined_number "
                "FROM core.orders AS o "
                "WHERE o.order_status = 'cancelled'"
            ),
            "reasoning_summary": "Used semantic context to map canceled to cancelled.",
            "expected_result_shape": ["total_refunded_amount", "combined_number"],
            "filters": ["o.order_status = 'cancelled'"],
        }

    def repair_sql_candidate(
        self,
        *,
        question,
        question_analysis,
        schema_context,
        selected_tables,
        retrieved_context,
        previous_candidate,
        execution_error,
        retry_count,
    ):
        raise AssertionError("repair should not be called")

    def compose_answer(self, *, question, candidate, execution_result, selected_tables):
        self.answer_requests.append({"candidate": candidate, "execution_result": execution_result})
        return "The combined number is 7 and the refunded amount is 123.45."


def test_retrieve_schema_context_normalizes_results_and_falls_back_on_error():
    state = retrieve_schema_context(
        {
            "question": "What is canceled revenue?",
            "allowed_tables": [],
            "errors": [],
        },
        schema_retriever=FakeSchemaRetriever(),
    )

    assert [item["name"] for item in state["retrieved_context"]] == [
        "order_status_vocabulary",
        "customers",
    ]
    assert state["retrieved_context"][0]["score"] == 0.91

    failed = retrieve_schema_context(
        {
            "question": "What is canceled revenue?",
            "allowed_tables": [],
            "errors": [],
        },
        schema_retriever=FakeSchemaRetriever(fail=True),
    )

    assert failed["retrieved_context"] == []
    assert failed["errors"][-1]["node"] == "retrieve_schema_context"
    assert failed["errors"][-1]["code"] == "schema_retrieval_failed"


def test_filter_context_by_allowed_tables_removes_disallowed_table_context():
    filtered = filter_context_by_allowed_tables(
        FakeSchemaRetriever().retrieve(question="refunds"),
        allowed_tables=["core.customers"],
    )

    assert [item["name"] for item in filtered] == ["customers"]


def test_run_agent_passes_retrieved_context_to_llm_and_uses_retrieved_tables():
    tool = FakePostgresMCPTool()
    retriever = FakeSchemaRetriever()
    llm = ContextAwareLLMProvider()

    state = run_agent(
        "What is the total amount of refunded & canceled order in 2021? What is the combined number?",
        mcp_tool=tool,
        llm_provider=llm,
        schema_retriever=retriever,
        current_date="2026-06-05",
    )

    assert retriever.requests[0]["allowed_tables"] == []
    assert "order_status_vocabulary" in [item["name"] for item in state["retrieved_context"]]
    assert {"core.orders", "core.order_items", "core.returns"}.issubset(set(state["selected_tables"]))
    assert llm.sql_requests[0]["retrieved_context"][0]["content"].count("cancelled") >= 1
    assert "cancelled" in state["candidate_sql"][0]["sql"]
    assert tool.executed_sql
    assert state["final_answer"].startswith("The combined number is 7")


def test_run_agent_filters_retrieved_context_by_allowed_tables():
    tool = FakePostgresMCPTool()
    retriever = FakeSchemaRetriever()
    llm = ContextAwareLLMProvider()

    state = run_agent(
        "What is the total amount of refunded & canceled order in 2021? What is the combined number?",
        mcp_tool=tool,
        llm_provider=llm,
        schema_retriever=retriever,
        allowed_tables=["core.customers"],
        current_date="2026-06-05",
    )

    assert retriever.requests[0]["allowed_tables"] == ["core.customers"]
    assert [item["name"] for item in state["retrieved_context"]] == ["customers"]
    assert state["selected_tables"] == ["core.customers"]
    assert tool.executed_sql == []
    assert "selected tables" in state["final_answer"]


def test_restart_script_uses_uv_run_for_the_ui():
    script = (ROOT / "scripts" / "restart_sql_rag_agent_ui.cmd").read_text(encoding="utf-8")

    assert "uv" in script.lower()
    assert "-m sql_rag_agent.ui" in script
    assert "uv run" in script.lower()
