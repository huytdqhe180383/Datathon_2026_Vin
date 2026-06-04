from __future__ import annotations

from datetime import date
from functools import partial

from langgraph.graph import END, StateGraph

from sql_rag_agent.llm import LLMProviderProtocol
from sql_rag_agent.nodes.compose_answer import compose_answer
from sql_rag_agent.nodes.execute_sql import execute_sql
from sql_rag_agent.nodes.generate_sql import generate_sql
from sql_rag_agent.nodes.inspect_schema import inspect_schema
from sql_rag_agent.nodes.understand_question import understand_question
from sql_rag_agent.nodes.validate_sql import validate_sql
from sql_rag_agent.state import SQLAgentState
from sql_rag_agent.tools.mcp_postgres import PostgresMCPToolProtocol
from sql_rag_agent.tracing import TraceWriter


def build_graph(
    mcp_tool: PostgresMCPToolProtocol | None = None,
    llm_provider: LLMProviderProtocol | None = None,
    trace_writer: TraceWriter | None = None,
    current_date: str | date | None = None,
):
    graph = StateGraph(SQLAgentState)
    graph.add_node("understand_question", understand_question)
    graph.add_node("inspect_schema", partial(inspect_schema, mcp_tool=mcp_tool))
    graph.add_node(
        "generate_sql",
        partial(generate_sql, current_date=current_date, llm_provider=llm_provider, trace_writer=trace_writer),
    )
    graph.add_node("validate_sql", partial(validate_sql, trace_writer=trace_writer))
    graph.add_node("execute_sql", partial(execute_sql, mcp_tool=mcp_tool, trace_writer=trace_writer))
    graph.add_node(
        "compose_answer",
        partial(compose_answer, llm_provider=llm_provider, trace_writer=trace_writer),
    )

    graph.set_entry_point("understand_question")
    graph.add_edge("understand_question", "inspect_schema")
    graph.add_edge("inspect_schema", "generate_sql")
    graph.add_edge("generate_sql", "validate_sql")
    graph.add_edge("validate_sql", "execute_sql")
    graph.add_edge("execute_sql", "compose_answer")
    graph.add_edge("compose_answer", END)
    return graph.compile()


def run_agent(
    question: str,
    mcp_tool: PostgresMCPToolProtocol | None = None,
    llm_provider: LLMProviderProtocol | None = None,
    trace_writer: TraceWriter | None = None,
    current_date: str | date | None = None,
) -> SQLAgentState:
    trace = trace_writer or TraceWriter()
    trace.write("question_received", {"question": question})
    app = build_graph(
        mcp_tool=mcp_tool,
        llm_provider=llm_provider,
        trace_writer=trace,
        current_date=current_date,
    )
    initial_state: SQLAgentState = {
        "question": question,
        "question_analysis": {},
        "schema_context": [],
        "selected_tables": [],
        "candidate_sql": [],
        "validated_sql": [],
        "execution_results": [],
        "ranked_results": [],
        "final_answer": "",
        "confidence": 0.0,
        "ground_truth": {},
        "errors": [],
    }
    final_state = app.invoke(initial_state)
    trace.write(
        "final_state",
        {
            "question": final_state.get("question"),
            "selected_tables": final_state.get("selected_tables", []),
            "candidate_sql": final_state.get("candidate_sql", []),
            "validated_sql": final_state.get("validated_sql", []),
            "execution_results": final_state.get("execution_results", []),
            "final_answer": final_state.get("final_answer"),
            "confidence": final_state.get("confidence"),
            "errors": final_state.get("errors", []),
        },
    )
    final_state["trace_id"] = trace.trace_id
    final_state["trace_path"] = str(trace.path)
    return final_state
