from pathlib import Path
import json
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "src"))

from sql_rag_agent.graph import run_agent
from sql_rag_agent.nodes.rank_results import rank_results
from sql_rag_agent.tracing import TraceWriter


class FakePostgresMCPTool:
    def __init__(self):
        self.executed_sql = []
        self.execution_limits = []

    def list_tables(self):
        return [
            "core.orders",
            "core.order_items",
            "core.payments",
            "core.returns",
        ]

    def describe_table(self, table_name):
        columns_by_table = {
            "core.orders": [
                {"name": "order_id", "type": "integer", "nullable": False, "description": None},
                {"name": "order_status", "type": "text", "nullable": False, "description": None},
            ],
            "core.order_items": [
                {"name": "order_item_id", "type": "integer", "nullable": False, "description": None},
                {"name": "order_id", "type": "integer", "nullable": False, "description": None},
                {"name": "quantity", "type": "integer", "nullable": False, "description": None},
                {"name": "unit_price", "type": "numeric", "nullable": False, "description": None},
                {"name": "discount_amount", "type": "numeric", "nullable": False, "description": None},
            ],
            "core.payments": [
                {"name": "payment_id", "type": "integer", "nullable": False, "description": None},
                {"name": "order_id", "type": "integer", "nullable": False, "description": None},
                {"name": "payment_value", "type": "numeric", "nullable": False, "description": None},
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
            "core.payments": [
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
        self.execution_limits.append(limit)
        if "payment_value" in sql:
            return [{"delivered_net_revenue": 90}]
        return [{"delivered_net_revenue": 100}]


class ContractRetriever:
    def retrieve(self, *, question, allowed_tables=None):
        return [
            {
                "type": "metric_definition",
                "name": "delivered_net_revenue",
                "content": (
                    "Metric: delivered net revenue. Definition: use "
                    "SUM(core.order_items.quantity * core.order_items.unit_price - "
                    "core.order_items.discount_amount) for delivered orders. "
                    "Do not subtract payments or refunds unless the user explicitly asks for refunds."
                ),
                "score": 0.99,
                "source": "docs/schema_context/benchmark_metric_contracts.md",
                "tables": ["core.orders", "core.order_items"],
                "columns": [
                    "core.orders.order_status",
                    "core.order_items.quantity",
                    "core.order_items.unit_price",
                    "core.order_items.discount_amount",
                ],
            },
            {
                "type": "output_contract",
                "name": "required_aliases",
                "content": "For value questions, preserve expected aliases such as delivered_net_revenue.",
                "score": 0.9,
                "source": "docs/schema_context/benchmark_output_contracts.md",
                "tables": [],
                "columns": [],
            },
        ]


class MultiCandidateLLMProvider:
    def __init__(self):
        self.answer_requests = []

    def analyze_question(self, *, question):
        return {
            "question_type": "aggregate",
            "expected_answer_type": "number",
            "requires_time_filter": False,
            "requires_join": True,
            "requires_metric_definition": True,
            "ambiguities": [],
        }

    def generate_sql_candidates(
        self,
        *,
        question,
        question_analysis,
        schema_context,
        selected_tables,
        retrieved_context,
    ):
        return [
            {
                "candidate_id": "payments_minus_refunds",
                "sql": (
                    "SELECT SUM(p.payment_value) - COALESCE(SUM(r.refund_amount), 0) "
                    "AS delivered_net_revenue "
                    "FROM core.payments AS p "
                    "LEFT JOIN core.orders AS o ON o.order_id = p.order_id "
                    "LEFT JOIN core.order_items AS oi ON oi.order_id = o.order_id "
                    "LEFT JOIN core.returns AS r ON r.order_item_id = oi.order_item_id "
                    "WHERE o.order_status = 'delivered'"
                ),
                "reasoning_summary": "Uses payments minus refunds.",
                "expected_result_shape": ["delivered_net_revenue"],
                "assumptions": ["Net revenue means payments minus refunds."],
            },
            {
                "candidate_id": "item_net_revenue",
                "sql": (
                    "SELECT SUM(oi.quantity * oi.unit_price - oi.discount_amount) "
                    "AS delivered_net_revenue "
                    "FROM core.orders AS o "
                    "JOIN core.order_items AS oi ON oi.order_id = o.order_id "
                    "WHERE o.order_status = 'delivered'"
                ),
                "reasoning_summary": "Uses documented item-level net revenue.",
                "expected_result_shape": ["delivered_net_revenue"],
                "assumptions": ["Net revenue means item revenue after discount."],
            },
        ]

    def repair_sql_candidate(self, **kwargs):
        raise AssertionError("repair should not be called")

    def compose_answer(self, *, question, candidate, execution_result, selected_tables):
        self.answer_requests.append({"candidate": candidate, "execution_result": execution_result})
        return f"winner={candidate['candidate_id']}"


def test_rank_results_prefers_documented_metric_and_output_contract():
    state = rank_results(
        {
            "question": "What is the delivered net revenue after discounts?",
            "question_analysis": {"expected_answer_type": "number"},
            "retrieved_context": ContractRetriever().retrieve(question="delivered net revenue"),
            "validated_sql": MultiCandidateLLMProvider()
            .generate_sql_candidates(
                question="What is delivered net revenue?",
                question_analysis={},
                schema_context=[],
                selected_tables=[],
                retrieved_context=[],
            ),
            "execution_results": [
                {
                    "candidate_id": "payments_minus_refunds",
                    "sql": "SELECT SUM(p.payment_value) - SUM(r.refund_amount) AS delivered_net_revenue FROM core.payments p LEFT JOIN core.returns r ON true",
                    "rows": [{"delivered_net_revenue": 90}],
                    "row_count": 1,
                    "error": None,
                },
                {
                    "candidate_id": "item_net_revenue",
                    "sql": "SELECT SUM(oi.quantity * oi.unit_price - oi.discount_amount) AS delivered_net_revenue FROM core.order_items oi",
                    "rows": [{"delivered_net_revenue": 100}],
                    "row_count": 1,
                    "error": None,
                },
            ],
        }
    )

    assert state["ranked_results"][0]["candidate_id"] == "item_net_revenue"
    assert state["ranked_results"][0]["score_breakdown"]["business_rule_match"] > state["ranked_results"][1]["score_breakdown"]["business_rule_match"]


def test_run_agent_executes_multiple_candidates_and_composes_answer_from_ranked_winner():
    tool = FakePostgresMCPTool()
    llm = MultiCandidateLLMProvider()

    state = run_agent(
        "What is the delivered net revenue after discounts?",
        mcp_tool=tool,
        llm_provider=llm,
        schema_retriever=ContractRetriever(),
    )

    assert len(state["candidate_sql"]) == 2
    assert len(tool.executed_sql) == 2
    assert state["ranked_results"][0]["candidate_id"] == "item_net_revenue"
    assert state["final_answer"] == "winner=item_net_revenue"


def test_table_questions_execute_with_a_large_enough_row_limit():
    tool = FakePostgresMCPTool()
    llm = MultiCandidateLLMProvider()

    run_agent(
        "Return a table of monthly delivered orders with columns order_month and delivered_orders.",
        mcp_tool=tool,
        llm_provider=llm,
        schema_retriever=ContractRetriever(),
    )

    assert tool.execution_limits
    assert max(tool.execution_limits) >= 500


def test_final_trace_includes_ranked_results(tmp_path):
    trace_writer = TraceWriter(log_dir=tmp_path, trace_id="phase3_trace")

    run_agent(
        "What is the delivered net revenue after discounts?",
        mcp_tool=FakePostgresMCPTool(),
        llm_provider=MultiCandidateLLMProvider(),
        schema_retriever=ContractRetriever(),
        trace_writer=trace_writer,
    )

    records = [
        json.loads(line)
        for line in trace_writer.path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    final_state = next(record for record in records if record["event"] == "final_state")

    assert final_state["payload"]["ranked_results"][0]["candidate_id"] == "item_net_revenue"
