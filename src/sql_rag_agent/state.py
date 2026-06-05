from typing import Any, TypedDict


class SQLAgentState(TypedDict, total=False):
    question: str
    allowed_tables: list[str]
    question_analysis: dict[str, Any]
    retrieved_context: list[dict[str, Any]]
    schema_context: list[dict[str, Any]]
    selected_tables: list[str]
    candidate_sql: list[dict[str, Any]]
    validated_sql: list[dict[str, Any]]
    execution_results: list[dict[str, Any]]
    ranked_results: list[dict[str, Any]]
    final_answer: str
    confidence: float
    ground_truth: dict[str, Any]
    errors: list[dict[str, Any]]
    trace_id: str
    trace_path: str
