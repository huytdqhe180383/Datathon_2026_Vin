from __future__ import annotations

from collections.abc import Callable
import os
from typing import Any

from sql_rag_agent.graph import run_agent
from sql_rag_agent.llm import OpenAICompatibleLLMProvider


def answer_question(
    question: str,
    runner: Callable[[str], dict[str, Any]] | None = None,
) -> str:
    cleaned = question.strip()
    if not cleaned:
        return "Please enter a question."

    run = runner or _run_agent_with_default_llm
    try:
        state = run(cleaned)
    except Exception as exc:
        return f"Unable to answer the question: {exc}"
    return state.get("final_answer") or "No answer was produced."


def _run_agent_with_default_llm(question: str) -> dict[str, Any]:
    return run_agent(question, llm_provider=OpenAICompatibleLLMProvider())


def build_app():
    import gradio as gr

    with gr.Blocks(title="Datathon SQL Agent") as demo:
        gr.Markdown("# Datathon SQL Agent")
        question = gr.Textbox(
            label="Question",
            placeholder="Ask a question about the PostgreSQL ecommerce data...",
            lines=3,
            autofocus=True,
        )
        answer = gr.Textbox(label="Answer", lines=8, interactive=False)
        submit = gr.Button("Ask", variant="primary")
        submit.click(fn=answer_question, inputs=question, outputs=answer)
        question.submit(fn=answer_question, inputs=question, outputs=answer)
    return demo


if __name__ == "__main__":
    port = int(os.getenv("GRADIO_SERVER_PORT", "7860"))
    build_app().launch(server_name="127.0.0.1", server_port=port)
