from __future__ import annotations

import json
from pathlib import Path
import shutil
from typing import Any

from sql_rag_agent.config import ROOT
from sql_rag_agent.evaluation import (
    build_session_layout,
    build_session_manifest,
    classify_legacy_result_artifact,
    classify_legacy_trace_artifact,
    diagnosis_override_path,
    load_diagnosis_overrides,
    render_session_summary_markdown,
    session_type_from_run_id,
    summarize_session_results,
)


RESULTS_ROOT = ROOT / "results"
TRACE_ROOT = ROOT / "logs" / "agent_traces"


def main() -> None:
    _move_legacy_results()
    _move_legacy_traces()
    _refresh_session_payloads_and_manifests()
    _refresh_session_summaries()


def _move_legacy_results() -> None:
    for path in RESULTS_ROOT.iterdir():
        if path.name in {".gitkeep", "reference", "sessions", "README.md"}:
            continue
        destination = classify_legacy_result_artifact(path)
        _move_path(path, destination)


def _move_legacy_traces() -> None:
    for path in TRACE_ROOT.iterdir():
        if path.name in {".gitkeep", "sessions"}:
            continue
        destination = classify_legacy_trace_artifact(path)
        _move_path(path, destination)


def _refresh_session_payloads_and_manifests() -> None:
    sessions_root = RESULTS_ROOT / "sessions"
    for session_type_dir in sessions_root.iterdir():
        if not session_type_dir.is_dir():
            continue
        for session_dir in session_type_dir.iterdir():
            if not session_dir.is_dir():
                continue
            _rewrite_run_payloads(session_dir)
            _write_manifest_for_session(session_dir)


def _rewrite_run_payloads(session_dir: Path) -> None:
    session_id = session_dir.name
    session_type = session_dir.parent.name
    layout = build_session_layout(session_type=session_type, session_id=session_id)
    for json_path in list(layout.chunks_dir.glob("*.json")) + list(layout.merged_dir.glob("*.json")):
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        payload["session_type"] = session_type
        payload["session_id"] = session_id
        source_value = str(payload.get("source", ""))
        payload["source"] = str(_normalized_source_path(source_value))
        for record in payload.get("records", []):
            trace_path = Path(str(record.get("trace_path", "")))
            if trace_path.name:
                new_trace_path = classify_legacy_trace_artifact(Path(trace_path.name))
                record["trace_path"] = str(new_trace_path)
        json_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2, default=str), encoding="utf-8")


def _write_manifest_for_session(session_dir: Path) -> None:
    session_id = session_dir.name
    session_type = session_dir.parent.name
    layout = build_session_layout(session_type=session_type, session_id=session_id)
    run_payload = _first_run_payload(layout)
    if run_payload is None:
        return

    chunk_files = []
    for json_path in sorted(layout.chunks_dir.glob("*.json")):
        csv_path = json_path.with_suffix(".csv")
        chunk_payload = json.loads(json_path.read_text(encoding="utf-8"))
        chunk_files.append(
            {
                "chunk_id": json_path.stem,
                "json_path": json_path,
                "csv_path": csv_path if csv_path.exists() else "",
                "question_count": chunk_payload.get("question_count", len(chunk_payload.get("records", []))),
            }
        )

    merged_outputs: dict[str, Any] = {}
    merged_jsons = sorted(layout.merged_dir.glob("*.json"))
    if merged_jsons:
        merged_json = merged_jsons[0]
        merged_outputs["json_path"] = merged_json
        merged_csv = merged_json.with_suffix(".csv")
        if merged_csv.exists():
            merged_outputs["csv_path"] = merged_csv

    comparison_paths: dict[str, Any] = {}
    if (layout.comparisons_dir / "table").exists():
        comparison_paths["table_dir"] = layout.comparisons_dir / "table"
    if (layout.comparisons_dir / "value").exists():
        comparison_paths["value_dir"] = layout.comparisons_dir / "value"

    summary_paths: dict[str, Any] = {}
    if layout.summary_markdown_path.exists():
        summary_paths["markdown_path"] = layout.summary_markdown_path
    if layout.summary_json_path.exists():
        summary_paths["json_path"] = layout.summary_json_path

    manifest = build_session_manifest(
        layout,
        source_benchmark=_normalized_source_path(str(run_payload.get("source", ""))),
        strong_model=run_payload.get("model", ""),
        weak_model=run_payload.get("weak_model", ""),
        question_count=run_payload.get("question_count", len(run_payload.get("records", []))),
        chunk_files=chunk_files,
        merged_outputs=merged_outputs,
        comparison_paths=comparison_paths,
        summary_paths=summary_paths or None,
    )
    manifest.update(
        {
            "created_at": run_payload.get("created_at"),
            "case_set": run_payload.get("case_set"),
            "manifest_version": 1,
        }
    )
    layout.manifest_path.write_text(json.dumps(manifest, ensure_ascii=True, indent=2), encoding="utf-8")


def _refresh_session_summaries() -> None:
    overrides = load_diagnosis_overrides(diagnosis_override_path())
    sessions_root = RESULTS_ROOT / "sessions"
    for session_type_dir in sessions_root.iterdir():
        if not session_type_dir.is_dir():
            continue
        for session_dir in session_type_dir.iterdir():
            if not session_dir.is_dir():
                continue
            _write_session_summary(session_dir, overrides)


def _write_session_summary(session_dir: Path, overrides: dict[str, dict[str, str]]) -> None:
    session_id = session_dir.name
    session_type = session_dir.parent.name
    layout = build_session_layout(session_type=session_type, session_id=session_id)
    layout.summaries_dir.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(layout.manifest_path.read_text(encoding="utf-8")) if layout.manifest_path.exists() else {}
    results = []
    for result_type in ("table", "value"):
        result_dir = layout.comparisons_dir / result_type
        if not result_dir.exists():
            continue
        for comparison_path in sorted(result_dir.glob("Q*/comparison.json")):
            comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
            if not comparison.get("id"):
                comparison["id"] = f"{result_type}-{comparison_path.parent.name}"
            results.append(comparison)

    if results:
        payload = summarize_session_results(manifest=manifest, results=results, overrides=overrides)
        layout.summary_json_path.write_text(
            json.dumps(payload, ensure_ascii=True, indent=2, default=str),
            encoding="utf-8",
        )
        layout.summary_markdown_path.write_text(render_session_summary_markdown(payload), encoding="utf-8")
        return

    placeholder = {
        "session": {
            "session_id": manifest.get("session_id", session_id),
            "session_type": manifest.get("session_type", session_type),
            "source_benchmark": manifest.get("source_benchmark", ""),
            "strong_model": manifest.get("strong_model", ""),
            "weak_model": manifest.get("weak_model", ""),
            "question_count": manifest.get("question_count", 0),
            "merged_outputs": manifest.get("merged_outputs", {}),
            "comparison_paths": manifest.get("comparison_paths", {}),
            "summary_paths": {
                "markdown_path": str(layout.summary_markdown_path),
                "json_path": str(layout.summary_json_path),
            },
            "trace_dir": manifest.get("trace_dir", ""),
        },
        "metrics": {
            "total_questions": manifest.get("question_count", 0),
            "ordered_matches": 0,
            "unordered_matches": 0,
            "ordering_only_mismatches": 0,
            "execution_errors": 0,
            "ordered_accuracy": "n/a",
            "unordered_accuracy": "n/a",
            "per_type": {
                "value": {"total_questions": 0, "ordered_matches": 0, "unordered_matches": 0, "execution_errors": 0},
                "table": {"total_questions": 0, "ordered_matches": 0, "unordered_matches": 0, "execution_errors": 0},
            },
        },
        "mismatch_index": [],
        "detailed_mismatches": [],
        "notable_wins": {
            "exact_matches": [],
            "near_matches": [],
            "output_contract_only": [],
        },
        "note": "Comparison artifacts were not available during migration for this session.",
    }
    layout.summary_json_path.write_text(json.dumps(placeholder, ensure_ascii=True, indent=2), encoding="utf-8")
    layout.summary_markdown_path.write_text(
        "\n".join(
            [
                f"# {session_id}",
                "",
                "## Session Header",
                f"- Session id: `{session_id}`",
                f"- Session type: `{session_type}`",
                f"- Source benchmark: `{manifest.get('source_benchmark', '')}`",
                f"- Strong model: `{manifest.get('strong_model', '')}`",
                f"- Weak model: `{manifest.get('weak_model', '')}`",
                f"- Question count: `{manifest.get('question_count', 0)}`",
                "",
                "## Headline Metrics",
                "- Comparison artifacts were not available during migration for this session.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _first_run_payload(layout: Any) -> dict[str, Any] | None:
    candidate_files = sorted(layout.merged_dir.glob("*.json")) + sorted(layout.chunks_dir.glob("*.json"))
    if not candidate_files:
        return None
    return json.loads(candidate_files[0].read_text(encoding="utf-8"))


def _normalized_source_path(value: str) -> Path:
    path = Path(value)
    if path.name == "sql_rag_vs_pandasai_20260608T043329Z.json":
        return RESULTS_ROOT / "reference" / "benchmark_runs" / path.name
    return path


def _move_path(source: Path, destination: Path) -> None:
    if not source.exists():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        if destination.exists():
            _merge_directories(source, destination)
            shutil.rmtree(source)
        else:
            shutil.move(str(source), str(destination))
        return
    if destination.exists():
        destination.unlink()
    shutil.move(str(source), str(destination))


def _merge_directories(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for child in source.iterdir():
        target = destination / child.name
        if child.is_dir():
            _merge_directories(child, target)
            shutil.rmtree(child)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                target.unlink()
            shutil.move(str(child), str(target))


if __name__ == "__main__":
    main()
