from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path
from typing import Any

import pandas as pd
from pandas.testing import assert_frame_equal

from sql_rag_agent.config import ROOT
from sql_rag_agent.evaluation import (
    build_session_layout,
    build_session_manifest,
    diagnosis_override_path,
    load_diagnosis_overrides,
    reference_case_dir,
    render_session_summary_markdown,
    session_type_from_run_id,
    summarize_session_results,
)


DEFAULT_RUN_JSON = (
    ROOT
    / "results"
    / "sessions"
    / "mismatch_rerun"
    / "mismatch_rerun_gpt-5.4-high_20260609T034001Z"
    / "merged"
    / "mismatch_rerun_gpt-5.4-high_20260609T034001Z_merged.json"
)
NUMERIC_ATOL = 0.01


def main() -> None:
    parser = argparse.ArgumentParser(description="Build comparison folders and summary reports for a rerun session.")
    parser.add_argument("--run-json", type=Path, default=DEFAULT_RUN_JSON)
    parser.add_argument("--manifest", type=Path, default=None)
    args = parser.parse_args()

    manifest, run_payload, layout = _load_session_inputs(run_json_path=args.run_json, manifest_path=args.manifest)
    table_dir = layout.comparisons_dir / "table"
    value_dir = layout.comparisons_dir / "value"
    _reset_dir(table_dir)
    _reset_dir(value_dir)
    layout.summaries_dir.mkdir(parents=True, exist_ok=True)

    table_results = []
    value_results = []
    for record in run_payload["records"]:
        rows, trace_error = _rows_from_trace(_repo_path(record["trace_path"]))
        execution_error = trace_error or record.get("execution_error")
        if record["type"] == "table":
            table_results.append(_build_table_case(record, rows, execution_error, table_dir))
        elif record["type"] == "value":
            value_results.append(_build_value_case(record, rows, execution_error, value_dir))

    _write_type_summary(
        output_dir=table_dir,
        suite_id=f"{layout.session_id}-table",
        result_type="table",
        results=table_results,
    )
    _write_type_summary(
        output_dir=value_dir,
        suite_id=f"{layout.session_id}-value",
        result_type="value",
        results=value_results,
    )

    comparison_manifest = build_session_manifest(
        layout,
        source_benchmark=_repo_path(manifest.get("source_benchmark") or run_payload["source"]),
        strong_model=manifest.get("strong_model") or run_payload.get("model") or "",
        weak_model=manifest.get("weak_model") or run_payload.get("weak_model") or "",
        question_count=manifest.get("question_count") or run_payload.get("question_count") or len(run_payload["records"]),
        chunk_files=manifest.get("chunk_files", []),
        merged_outputs=_merged_outputs_for_manifest(layout, manifest, args.run_json),
        comparison_paths={
            "table_dir": table_dir,
            "value_dir": value_dir,
        },
        summary_paths={
            "markdown_path": layout.summary_markdown_path,
            "json_path": layout.summary_json_path,
        },
    )
    comparison_manifest.update(
        {
            "created_at": manifest.get("created_at") or run_payload.get("created_at"),
            "case_set": manifest.get("case_set") or run_payload.get("case_set"),
            "manifest_version": 1,
        }
    )

    overrides = load_diagnosis_overrides(diagnosis_override_path())
    summary_payload = summarize_session_results(
        manifest=comparison_manifest,
        results=table_results + value_results,
        overrides=overrides,
    )
    layout.summary_json_path.write_text(
        json.dumps(summary_payload, ensure_ascii=True, indent=2, default=str),
        encoding="utf-8",
    )
    layout.summary_markdown_path.write_text(
        render_session_summary_markdown(summary_payload),
        encoding="utf-8",
    )
    layout.manifest_path.write_text(json.dumps(comparison_manifest, ensure_ascii=True, indent=2), encoding="utf-8")

    print(layout.summary_markdown_path)
    print(
        json.dumps(
            {
                "table": _summary_counts(table_results),
                "value": _summary_counts(value_results),
                "summary": str(layout.summary_json_path),
            },
            indent=2,
        )
    )


def _load_session_inputs(run_json_path: Path, manifest_path: Path | None) -> tuple[dict[str, Any], dict[str, Any], Any]:
    manifest: dict[str, Any] = {}
    if manifest_path and manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    elif (run_json_path.parent.parent / "manifest.json").exists():
        manifest = json.loads((run_json_path.parent.parent / "manifest.json").read_text(encoding="utf-8"))

    run_payload = json.loads(run_json_path.read_text(encoding="utf-8"))
    session_id = str(run_payload["run_id"]).replace("_merged", "")
    session_type = manifest.get("session_type") or session_type_from_run_id(session_id)
    layout = build_session_layout(session_type=session_type, session_id=session_id)
    for directory in (layout.root, layout.comparisons_dir, layout.summaries_dir):
        directory.mkdir(parents=True, exist_ok=True)
    if not manifest:
        manifest = {
            "session_type": session_type,
            "session_id": session_id,
            "source_benchmark": str(run_payload.get("source", "")),
            "strong_model": run_payload.get("model", ""),
            "weak_model": run_payload.get("weak_model", ""),
            "question_count": run_payload.get("question_count", len(run_payload.get("records", []))),
            "chunk_files": [],
            "merged_outputs": {},
        }
    return manifest, run_payload, layout


def _merged_outputs_for_manifest(layout: Any, manifest: dict[str, Any], run_json_path: Path) -> dict[str, Any]:
    existing = manifest.get("merged_outputs") or {}
    if existing:
        return existing
    if run_json_path.stem.endswith("_merged"):
        csv_path = run_json_path.with_suffix(".csv")
        outputs = {"json_path": run_json_path}
        if csv_path.exists():
            outputs["csv_path"] = csv_path
        return outputs
    return {}


def _build_table_case(
    record: dict[str, Any],
    rows: list[dict[str, Any]],
    execution_error: str | None,
    output_root: Path,
) -> dict[str, Any]:
    index = int(record["index"])
    case_dir = output_root / f"Q{index}"
    case_dir.mkdir(parents=True, exist_ok=True)
    reference_csv = reference_case_dir("table", index) / "reference_sql.csv"
    local_reference_csv = case_dir / "reference_sql.csv"
    shutil.copyfile(reference_csv, local_reference_csv)
    reference_df = pd.read_csv(local_reference_csv, dtype=str)
    agent_csv = case_dir / "agent_output.csv"
    _write_rows_csv(agent_csv, rows, reference_columns=list(reference_df.columns))

    agent_df = pd.read_csv(agent_csv, dtype=str) if agent_csv.stat().st_size else pd.DataFrame()
    agent_df = _align_columns(reference_df, agent_df)
    comparison = _compare_frames(reference_df, agent_df)
    comparison.update(
        {
            "id": record.get("id") or f"table-Q{index}",
            "type": "table",
            "index": index,
            "question": record["question"],
            "status": "error" if execution_error else "ok",
            "execution_error": execution_error,
            "latency_seconds": record.get("latency_seconds"),
            "generated_sql": record.get("generated_sql"),
            "reference_sql": record.get("reference_sql"),
            "trace_path": record.get("trace_path"),
        }
    )
    _write_json(case_dir / "comparison.json", comparison)
    return comparison


def _build_value_case(
    record: dict[str, Any],
    rows: list[dict[str, Any]],
    execution_error: str | None,
    output_root: Path,
) -> dict[str, Any]:
    index = int(record["index"])
    case_dir = output_root / f"Q{index}"
    case_dir.mkdir(parents=True, exist_ok=True)
    reference_row, reference_sql = _value_reference(index)
    reference_csv = case_dir / "reference_sql.csv"
    agent_csv = case_dir / "agent_output.csv"
    _write_rows_csv(reference_csv, [reference_row])
    reference_df = pd.read_csv(reference_csv, dtype=str)
    _write_rows_csv(agent_csv, rows[:1], reference_columns=list(reference_df.columns))

    agent_df = pd.read_csv(agent_csv, dtype=str) if agent_csv.stat().st_size else pd.DataFrame()
    agent_df = _align_columns(reference_df, agent_df)
    comparison = _compare_frames(reference_df, agent_df)
    comparison.update(
        {
            "id": record.get("id") or f"value-Q{index}",
            "type": "value",
            "index": index,
            "question": record["question"],
            "status": "error" if execution_error else "ok",
            "execution_error": execution_error,
            "latency_seconds": record.get("latency_seconds"),
            "generated_sql": record.get("generated_sql"),
            "reference_sql": reference_sql,
            "trace_path": record.get("trace_path"),
        }
    )
    _write_json(case_dir / "comparison.json", comparison)
    return comparison


def _compare_frames(reference_df: pd.DataFrame, agent_df: pd.DataFrame) -> dict[str, Any]:
    reference_norm = _normalize_df(reference_df)
    agent_norm = _normalize_df(agent_df)
    ordered_match, ordered_reason, ordered_preview = _try_compare(reference_norm, agent_norm)
    unordered_match = False
    unordered_reason = ordered_reason
    unordered_preview = ordered_preview
    if list(reference_norm.columns) == list(agent_norm.columns):
        unordered_match, unordered_reason, unordered_preview = _try_compare(
            _sort_rows(reference_norm),
            _sort_rows(agent_norm),
        )
    ordering_only = (not ordered_match) and unordered_match
    return {
        "reference_shape": list(reference_df.shape),
        "agent_shape": list(agent_df.shape),
        "reference_columns": list(reference_df.columns),
        "agent_columns": list(agent_df.columns),
        "match": ordered_match,
        "reason": ordered_reason,
        "unordered_match": unordered_match,
        "unordered_reason": unordered_reason,
        "ordering_only_mismatch": ordering_only,
        "classification": "ordering_only" if ordering_only else ordered_reason,
        "diff_preview": ordered_preview,
        "unordered_diff_preview": unordered_preview,
    }


def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    normalized = df.copy()
    for column in normalized.columns:
        numeric = pd.to_numeric(normalized[column], errors="coerce")
        if numeric.notna().all():
            normalized[column] = numeric.astype(float)
        else:
            normalized[column] = normalized[column].map(lambda value: "" if pd.isna(value) else str(value))
    return normalized


def _try_compare(left: pd.DataFrame, right: pd.DataFrame) -> tuple[bool, str, list[str]]:
    if list(left.columns) != list(right.columns):
        return False, "column_mismatch", []
    if left.shape != right.shape:
        return False, "shape_mismatch", []
    try:
        assert_frame_equal(
            left.reset_index(drop=True),
            right.reset_index(drop=True),
            check_dtype=False,
            check_exact=False,
            atol=NUMERIC_ATOL,
            rtol=0,
        )
        return True, "exact_after_normalization", []
    except AssertionError as exc:
        return False, "value_mismatch", str(exc).splitlines()[:12]


def _sort_rows(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    return df.sort_values(by=list(df.columns), kind="mergesort").reset_index(drop=True)


def _align_columns(reference_df: pd.DataFrame, agent_df: pd.DataFrame) -> pd.DataFrame:
    if set(reference_df.columns) == set(agent_df.columns):
        return agent_df[list(reference_df.columns)]
    return agent_df


def _rows_from_trace(path: Path) -> tuple[list[dict[str, Any]], str | None]:
    if not path.exists():
        return [], f"trace file not found: {path}"
    execution_results = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        payload = record.get("payload", {})
        if record.get("event") == "execute_sql":
            execution_results = payload.get("execution_results", [])
        elif record.get("event") == "final_state" and not execution_results:
            execution_results = payload.get("execution_results", [])

    first_success = next((item for item in execution_results if not item.get("error")), None)
    if first_success:
        return list(first_success.get("rows") or []), None
    first_error = next((item.get("error") for item in execution_results if item.get("error")), None)
    return [], first_error


def _value_reference(index: int) -> tuple[dict[str, Any], str]:
    path = reference_case_dir("value", index) / "comparison.json"
    comparison = json.loads(path.read_text(encoding="utf-8"))
    outer = json.loads(comparison["ground_truth_answer"])
    return json.loads(outer["ground_truth_answer"]), outer["sql_query"]


def _write_rows_csv(
    path: Path,
    rows: list[dict[str, Any]],
    reference_columns: list[str] | None = None,
) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    row_columns = list(rows[0].keys())
    columns = reference_columns if reference_columns and set(reference_columns) == set(row_columns) else row_columns
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _write_type_summary(output_dir: Path, suite_id: str, result_type: str, results: list[dict[str, Any]]) -> None:
    counts = _summary_counts(results)
    payload = {
        "suite_id": suite_id,
        "type": result_type,
        **counts,
        "results": [
            {
                "id": item["id"],
                "type": item["type"],
                "index": item["index"],
                "question": item["question"],
                "status": item["status"],
                "match": item["match"],
                "unordered_match": item["unordered_match"],
                "ordering_only_mismatch": item["ordering_only_mismatch"],
                "classification": item["classification"],
                "reason": item["reason"],
                "unordered_reason": item["unordered_reason"],
                "latency_seconds": item["latency_seconds"],
            }
            for item in sorted(results, key=lambda value: int(value["index"]))
        ],
    }
    _write_json(output_dir / "summary.json", payload)
    (output_dir / "summary.md").write_text(_type_summary_markdown(payload), encoding="utf-8")


def _summary_counts(results: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "question_count": len(results),
        "ok_count": sum(1 for item in results if item["status"] == "ok"),
        "ordered_match_count": sum(1 for item in results if item["match"]),
        "unordered_match_count": sum(1 for item in results if item["unordered_match"]),
        "ordering_only_count": sum(1 for item in results if item["ordering_only_mismatch"]),
        "mismatch_count_ordered": sum(1 for item in results if not item["match"]),
        "mismatch_count_unordered": sum(1 for item in results if not item["unordered_match"]),
        "error_count": sum(1 for item in results if item["status"] == "error"),
    }


def _type_summary_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# {payload['suite_id']}",
        "",
        f"- Questions: `{payload['question_count']}`",
        f"- Ordered matches: `{payload['ordered_match_count']}`",
        f"- Unordered matches: `{payload['unordered_match_count']}`",
        f"- Ordering-only mismatches: `{payload['ordering_only_count']}`",
        f"- Ordered mismatches: `{payload['mismatch_count_ordered']}`",
        f"- Unordered mismatches: `{payload['mismatch_count_unordered']}`",
        f"- Execution errors: `{payload['error_count']}`",
        "",
        "| Question | Status | Ordered | Unordered | Classification |",
        "|---|---|---:|---:|---|",
    ]
    for item in payload["results"]:
        lines.append(
            "| Q{index} | {status} | {match} | {unordered_match} | {classification} |".format(
                index=item["index"],
                status=item["status"],
                match=str(item["match"]).lower(),
                unordered_match=str(item["unordered_match"]).lower(),
                classification=item["classification"],
            )
        )
    return "\n".join(lines) + "\n"


def _repo_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _reset_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
