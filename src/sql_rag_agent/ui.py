from __future__ import annotations

from collections.abc import Callable
import inspect
import os
from typing import Any

from sql_rag_agent.graph import run_agent
from sql_rag_agent.llm import OpenAICompatibleLLMProvider
from sql_rag_agent.tools.mcp_postgres import PostgresMCPTool, PostgresMCPToolProtocol


def answer_question(
    question: str,
    selected_tables: list[str] | None = None,
    runner: Callable[..., dict[str, Any]] | None = None,
) -> str:
    cleaned = question.strip()
    if not cleaned:
        return "Please enter a question."

    scoped_tables = [table for table in (selected_tables or []) if table]
    run = runner or _run_agent_with_default_llm
    try:
        state = _invoke_runner(run, cleaned, scoped_tables)
    except Exception as exc:
        return f"Unable to answer the question: {exc}"
    return state.get("final_answer") or "No answer was produced."


def get_available_tables(mcp_tool: PostgresMCPToolProtocol | None = None) -> list[str]:
    tool = mcp_tool or PostgresMCPTool()
    try:
        return sorted(tool.list_tables())
    except Exception:
        return []


def _run_agent_with_default_llm(
    question: str,
    selected_tables: list[str] | None = None,
) -> dict[str, Any]:
    return run_agent(
        question,
        llm_provider=OpenAICompatibleLLMProvider(),
        allowed_tables=selected_tables,
    )


def _invoke_runner(
    runner: Callable[..., dict[str, Any]],
    question: str,
    selected_tables: list[str],
) -> dict[str, Any]:
    try:
        signature = inspect.signature(runner)
    except (TypeError, ValueError):
        return runner(question, selected_tables)

    parameters = signature.parameters
    if "selected_tables" in parameters:
        return runner(question, selected_tables=selected_tables)
    if len(parameters) >= 2:
        return runner(question, selected_tables)
    return runner(question)


def build_app(
    mcp_tool: PostgresMCPToolProtocol | None = None,
    runner: Callable[..., dict[str, Any]] | None = None,
):
    import gradio as gr

    available_tables = get_available_tables(mcp_tool)

    with gr.Blocks(title="Datathon SQL Agent") as demo:
        gr.Markdown("# Datathon SQL Agent")
        question = gr.Textbox(
            label="Question",
            placeholder="Ask a question about the PostgreSQL ecommerce data...",
            lines=3,
            autofocus=True,
        )
        table_selector = gr.Dropdown(
            label="Tables",
            info="Optional. If you select tables here, the agent will only inspect and query those tables.",
            choices=available_tables,
            multiselect=True,
            value=[],
        )
        answer = gr.Textbox(label="Answer", lines=8, interactive=False)
        submit = gr.Button("Ask", variant="primary")
        submit.click(
            fn=lambda q, tables: answer_question(q, tables, runner=runner),
            inputs=[question, table_selector],
            outputs=answer,
        )
        question.submit(
            fn=lambda q, tables: answer_question(q, tables, runner=runner),
            inputs=[question, table_selector],
            outputs=answer,
        )
    return demo


if __name__ == "__main__":
    port = int(os.getenv("GRADIO_SERVER_PORT", "7860"))
    build_app().launch(server_name="127.0.0.1", server_port=port)
