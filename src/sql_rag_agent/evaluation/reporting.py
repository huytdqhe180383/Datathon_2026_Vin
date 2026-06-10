from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_diagnosis_overrides(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def diagnose_case(
    result: dict[str, Any],
    overrides: dict[str, dict[str, str]] | None = None,
) -> dict[str, str]:
    question_id = _question_id(result)
    override = (overrides or {}).get(question_id)
    if override:
        return {
            "label": override["label"],
            "summary": override["summary"],
            "evidence": override["evidence"],
            "source": "manual_override",
        }

    execution_error = str(result.get("execution_error") or "").strip()
    if result.get("status") == "error" or execution_error:
        return {
            "label": "timeout_or_execution_issue",
            "summary": "The query did not produce a usable result set, so the mismatch is driven by execution failure rather than answer comparison.",
            "evidence": execution_error or _fallback_evidence(result),
            "source": "deterministic",
        }

    if result.get("ordering_only_mismatch"):
        return {
            "label": "ordering_only",
            "summary": "The rows match after sorting, so the mismatch is limited to output ordering.",
            "evidence": _fallback_evidence(result),
            "source": "deterministic",
        }

    if result.get("reason") == "shape_mismatch":
        reference_shape = list(result.get("reference_shape") or [0, 0])
        agent_shape = list(result.get("agent_shape") or [0, 0])
        if reference_shape and agent_shape and reference_shape[0] > agent_shape[0] == 100:
            return {
                "label": "row_limit_truncation",
                "summary": "The output stopped at 100 rows, so the table shape diverged before the full benchmark result could be compared.",
                "evidence": f"reference_shape={reference_shape}, agent_shape={agent_shape}",
                "source": "deterministic",
            }
        return {
            "label": "shape_mismatch",
            "summary": "The result shape differs from the benchmark reference, so the output contract is incomplete even before checking cell values.",
            "evidence": f"reference_shape={reference_shape}, agent_shape={agent_shape}",
            "source": "deterministic",
        }

    if result.get("reason") == "column_mismatch":
        return {
            "label": "column_mismatch",
            "summary": "The query returned a different column set or alias contract from the benchmark reference.",
            "evidence": _fallback_evidence(result),
            "source": "deterministic",
        }

    if result.get("reason") == "value_mismatch":
        return {
            "label": "value_mismatch",
            "summary": "The query returned the expected shape but at least one value diverged from the benchmark reference.",
            "evidence": _fallback_evidence(result),
            "source": "deterministic",
        }

    return {
        "label": str(result.get("classification") or "value_mismatch"),
        "summary": "The output differs from the benchmark reference.",
        "evidence": _fallback_evidence(result),
        "source": "deterministic",
    }


def summarize_session_results(
    *,
    manifest: dict[str, Any],
    results: list[dict[str, Any]],
    overrides: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    ordered = sorted(results, key=lambda item: (_type_rank(item.get("type")), int(item.get("index") or 0)))
    annotated = []
    for item in ordered:
        diagnosis = diagnose_case(item, overrides=overrides)
        annotated.append(
            {
                **item,
                "id": _question_id(item),
                "diagnosis": diagnosis,
                "output_shape_summary": _output_shape_summary(item),
            }
        )

    mismatches = [item for item in annotated if not item.get("match")]
    exact_matches = [item["id"] for item in annotated if item.get("match")]
    near_matches = [item["id"] for item in annotated if item.get("ordering_only_mismatch")]
    output_contract_cases = [
        item["id"]
        for item in annotated
        if item.get("diagnosis", {}).get("label") == "output_contract_mismatch"
    ]

    metrics = {
        "total_questions": len(annotated),
        "ordered_matches": sum(1 for item in annotated if item.get("match")),
        "unordered_matches": sum(1 for item in annotated if item.get("unordered_match")),
        "ordering_only_mismatches": sum(1 for item in annotated if item.get("ordering_only_mismatch")),
        "execution_errors": sum(1 for item in annotated if item.get("status") == "error"),
    }
    metrics["ordered_accuracy"] = _percent(metrics["ordered_matches"], metrics["total_questions"])
    metrics["unordered_accuracy"] = _percent(metrics["unordered_matches"], metrics["total_questions"])
    metrics["per_type"] = {
        result_type: {
            "total_questions": len([item for item in annotated if item.get("type") == result_type]),
            "ordered_matches": sum(
                1 for item in annotated if item.get("type") == result_type and item.get("match")
            ),
            "unordered_matches": sum(
                1 for item in annotated if item.get("type") == result_type and item.get("unordered_match")
            ),
            "execution_errors": sum(
                1 for item in annotated if item.get("type") == result_type and item.get("status") == "error"
            ),
        }
        for result_type in ("value", "table")
    }

    mismatch_index = [
        {
            "question_id": item["id"],
            "question": item.get("question"),
            "type": item.get("type"),
            "classification": item.get("classification"),
            "ordered_outcome": "match" if item.get("match") else "mismatch",
            "unordered_outcome": "match" if item.get("unordered_match") else "mismatch",
            "status": item.get("status"),
            "diagnosis_label": item["diagnosis"]["label"],
        }
        for item in mismatches
    ]

    detailed_mismatches = [
        {
            "question_id": item["id"],
            "question": item.get("question"),
            "classification": item.get("classification"),
            "generated_sql": item.get("generated_sql") or item.get("sql_query") or "",
            "reference_sql": item.get("reference_sql") or item.get("pandas_sql_query") or "",
            "output_shape_summary": item["output_shape_summary"],
            "diagnosis_label": item["diagnosis"]["label"],
            "diagnosis_summary": item["diagnosis"]["summary"],
            "evidence_snippet": item["diagnosis"]["evidence"],
            "status": item.get("status"),
            "ordered_outcome": "match" if item.get("match") else "mismatch",
            "unordered_outcome": "match" if item.get("unordered_match") else "mismatch",
            "type": item.get("type"),
        }
        for item in mismatches
    ]

    return {
        "session": {
            "session_id": manifest.get("session_id"),
            "session_type": manifest.get("session_type"),
            "source_benchmark": manifest.get("source_benchmark"),
            "strong_model": manifest.get("strong_model"),
            "weak_model": manifest.get("weak_model"),
            "question_count": manifest.get("question_count", len(annotated)),
            "merged_outputs": manifest.get("merged_outputs", {}),
            "comparison_paths": manifest.get("comparison_paths", {}),
            "summary_paths": manifest.get("summary_paths", {}),
            "trace_dir": manifest.get("trace_dir"),
        },
        "metrics": metrics,
        "mismatch_index": mismatch_index,
        "detailed_mismatches": detailed_mismatches,
        "notable_wins": {
            "exact_matches": exact_matches,
            "near_matches": near_matches,
            "output_contract_only": output_contract_cases,
        },
    }


def render_session_summary_markdown(payload: dict[str, Any]) -> str:
    session = payload["session"]
    metrics = payload["metrics"]
    lines = [
        f"# {session['session_id']}",
        "",
        "## Session Header",
        f"- Session id: `{session['session_id']}`",
        f"- Session type: `{session['session_type']}`",
        f"- Source benchmark: `{session['source_benchmark']}`",
        f"- Strong model: `{session['strong_model']}`",
        f"- Weak model: `{session['weak_model']}`",
        f"- Question count: `{session['question_count']}`",
        f"- Merged outputs: `{session.get('merged_outputs', {})}`",
        f"- Comparisons: `{session.get('comparison_paths', {})}`",
        f"- Trace folder: `{session['trace_dir']}`",
        "",
        "## Headline Metrics",
        f"- Total questions: `{metrics['total_questions']}`",
        f"- Ordered matches: `{metrics['ordered_matches']}`",
        f"- Unordered matches: `{metrics['unordered_matches']}`",
        f"- Ordering-only mismatches: `{metrics['ordering_only_mismatches']}`",
        f"- Execution errors: `{metrics['execution_errors']}`",
        f"- Ordered accuracy: `{metrics['ordered_accuracy']}`",
        f"- Unordered accuracy: `{metrics['unordered_accuracy']}`",
        "",
        "| Type | Total | Ordered Matches | Unordered Matches | Execution Errors |",
        "|---|---:|---:|---:|---:|",
    ]
    for result_type in ("value", "table"):
        breakdown = metrics["per_type"][result_type]
        lines.append(
            f"| {result_type} | {breakdown['total_questions']} | {breakdown['ordered_matches']} | "
            f"{breakdown['unordered_matches']} | {breakdown['execution_errors']} |"
        )

    lines.extend(
        [
            "",
            "## Mismatch Index",
            "| Question ID | Question | Type | Classification | Ordered | Unordered | Status | Diagnosis |",
            "|---|---|---|---|---|---|---|---|",
        ]
    )
    for item in payload["mismatch_index"]:
        lines.append(
            f"| {item['question_id']} | {item['question']} | {item['type']} | {item['classification']} | "
            f"{item['ordered_outcome']} | {item['unordered_outcome']} | {item['status']} | {item['diagnosis_label']} |"
        )

    lines.extend(["", "## Detailed Mismatches"])
    for item in payload["detailed_mismatches"]:
        lines.extend(
            [
                f"### {item['question_id']}",
                f"- Question: {item['question']}",
                f"- Type: `{item['type']}`",
                f"- Classification: `{item['classification']}`",
                f"- Ordered / unordered: `{item['ordered_outcome']}` / `{item['unordered_outcome']}`",
                f"- Status: `{item['status']}`",
                f"- Diagnosis: `{item['diagnosis_label']}`",
                f"- Output shape summary: {item['output_shape_summary']}",
                f"- Short diagnosis: {item['diagnosis_summary']}",
                f"- Evidence snippet: {item['evidence_snippet']}",
                "",
                "Generated SQL:",
                "```sql",
                item["generated_sql"] or "-- missing generated SQL --",
                "```",
                "",
                "Reference SQL:",
                "```sql",
                item["reference_sql"] or "-- missing reference SQL --",
                "```",
                "",
            ]
        )

    notable = payload["notable_wins"]
    lines.extend(
        [
            "## Notable Wins",
            f"- Exact matches: {', '.join(notable['exact_matches']) if notable['exact_matches'] else 'None'}",
            f"- Ordering-only or near matches: {', '.join(notable['near_matches']) if notable['near_matches'] else 'None'}",
            f"- Output-contract-only cases: {', '.join(notable['output_contract_only']) if notable['output_contract_only'] else 'None'}",
            "",
        ]
    )
    return "\n".join(lines)


def _question_id(result: dict[str, Any]) -> str:
    if result.get("id"):
        return str(result["id"])
    return f"{result.get('type')}-Q{int(result.get('index') or 0)}"


def _output_shape_summary(result: dict[str, Any]) -> str:
    reference_shape = list(result.get("reference_shape") or [0, 0])
    agent_shape = list(result.get("agent_shape") or [0, 0])
    reference_columns = list(result.get("reference_columns") or [])
    agent_columns = list(result.get("agent_columns") or [])
    return (
        f"reference_shape={reference_shape}, agent_shape={agent_shape}, "
        f"reference_columns={reference_columns}, agent_columns={agent_columns}"
    )


def _fallback_evidence(result: dict[str, Any]) -> str:
    for key in ("diff_preview", "unordered_diff_preview"):
        preview = result.get(key)
        if isinstance(preview, list) and preview:
            return "; ".join(str(item) for item in preview[:3])
        if isinstance(preview, str) and preview.strip():
            return preview.strip()
    return _output_shape_summary(result)


def _percent(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "0.00%"
    return f"{(100 * numerator / denominator):.2f}%"


def _type_rank(value: Any) -> int:
    if value == "table":
        return 0
    if value == "value":
        return 1
    return 2
