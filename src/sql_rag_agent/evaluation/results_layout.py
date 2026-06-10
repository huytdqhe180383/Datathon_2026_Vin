from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

from sql_rag_agent.config import ROOT


RESULTS_ROOT = ROOT / "results"
SESSIONS_ROOT = RESULTS_ROOT / "sessions"
REFERENCE_ROOT = RESULTS_ROOT / "reference"
TRACE_SESSIONS_ROOT = ROOT / "logs" / "agent_traces" / "sessions"
TRACE_ROOT = ROOT / "logs" / "agent_traces"


@dataclass(frozen=True)
class SessionLayout:
    session_type: str
    session_id: str
    root: Path
    chunks_dir: Path
    merged_dir: Path
    comparisons_dir: Path
    summaries_dir: Path
    trace_dir: Path
    manifest_path: Path

    @property
    def summary_markdown_path(self) -> Path:
        return self.summaries_dir / "summary.md"

    @property
    def summary_json_path(self) -> Path:
        return self.summaries_dir / "summary.json"

    def chunk_json_path(self, chunk_id: str) -> Path:
        return self.chunks_dir / f"{chunk_id}.json"

    def chunk_csv_path(self, chunk_id: str) -> Path:
        return self.chunks_dir / f"{chunk_id}.csv"

    def merged_json_path(self, merged_id: str) -> Path:
        return self.merged_dir / f"{merged_id}.json"

    def merged_csv_path(self, merged_id: str) -> Path:
        return self.merged_dir / f"{merged_id}.csv"

    def comparison_case_dir(self, result_type: str, index: int) -> Path:
        return self.comparisons_dir / result_type / f"Q{int(index)}"


def build_session_layout(
    *,
    session_type: str,
    session_id: str,
    results_root: Path = RESULTS_ROOT,
    trace_sessions_root: Path = TRACE_SESSIONS_ROOT,
) -> SessionLayout:
    root = results_root / "sessions" / session_type / session_id
    return SessionLayout(
        session_type=session_type,
        session_id=session_id,
        root=root,
        chunks_dir=root / "chunks",
        merged_dir=root / "merged",
        comparisons_dir=root / "comparisons",
        summaries_dir=root / "summaries",
        trace_dir=trace_sessions_root / session_type / session_id,
        manifest_path=root / "manifest.json",
    )


def session_type_from_run_id(run_id: str) -> str:
    if run_id.startswith("smoke_"):
        return "smoke"
    if run_id.startswith("mismatch_rerun"):
        return "mismatch_rerun"
    if run_id.startswith("full_rerun"):
        return "full_rerun"
    return "legacy_import"


def build_session_manifest(
    layout: SessionLayout,
    *,
    source_benchmark: str | Path,
    strong_model: str,
    weak_model: str,
    question_count: int,
    chunk_files: list[dict[str, Any]] | None = None,
    merged_outputs: dict[str, Any] | None = None,
    comparison_paths: dict[str, Any] | None = None,
    summary_paths: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "session_type": layout.session_type,
        "session_id": layout.session_id,
        "source_benchmark": _repo_relative_string(Path(source_benchmark)),
        "strong_model": strong_model,
        "weak_model": weak_model,
        "question_count": question_count,
        "trace_dir": _repo_relative_string(layout.trace_dir),
        "chunk_files": [_relative_dict(item) for item in (chunk_files or [])],
        "merged_outputs": _relative_dict(merged_outputs or {}),
        "comparison_paths": _relative_dict(comparison_paths or {}),
        "summary_paths": _relative_dict(
            summary_paths
            or {
                "markdown_path": layout.summary_markdown_path,
                "json_path": layout.summary_json_path,
            }
        ),
    }
    return payload


def classify_legacy_result_artifact(path: Path, results_root: Path = RESULTS_ROOT) -> Path:
    name = path.name
    if name.startswith("sql_rag_vs_pandasai_"):
        return results_root / "reference" / "benchmark_runs" / name
    if name == "table_output_comparison":
        return results_root / "reference" / "comparisons" / "table"
    if name == "value_output_comparison":
        return results_root / "reference" / "comparisons" / "value"
    if name == "summary.md":
        return results_root / "reference" / "summaries" / "baseline_summary.md"
    if name == "summary.json":
        return results_root / "reference" / "summaries" / "baseline_summary.json"
    if name == "mismatch_root_cause_summary.md":
        return results_root / "reference" / "reviews" / name

    comparison_match = re.match(r"^(table|value)_output_(.+)$", name)
    if comparison_match:
        result_type = comparison_match.group(1)
        session_id = comparison_match.group(2)
        layout = build_session_layout(
            session_type=session_type_from_run_id(session_id),
            session_id=session_id,
            results_root=results_root,
        )
        return layout.comparisons_dir / result_type

    if path.suffix in {".json", ".csv"}:
        stem = path.stem
        if stem.endswith("_merged"):
            session_id = stem.removesuffix("_merged")
            layout = build_session_layout(
                session_type=session_type_from_run_id(session_id),
                session_id=session_id,
                results_root=results_root,
            )
            return layout.merged_dir / path.name
        session_type = session_type_from_run_id(stem)
        if session_type != "legacy_import":
            layout = build_session_layout(session_type=session_type, session_id=stem, results_root=results_root)
            return layout.chunks_dir / path.name

    return results_root / "sessions" / "legacy_import" / name


def classify_legacy_trace_artifact(path: Path, trace_root: Path = TRACE_ROOT) -> Path:
    match = re.match(r"^(?P<run_id>.+)_(?P<kind>table|value)_Q\d+\.jsonl$", path.name)
    if not match:
        return trace_root / "sessions" / "legacy_import" / "misc" / path.name
    run_id = match.group("run_id")
    session_type = session_type_from_run_id(run_id)
    return trace_root / "sessions" / session_type / run_id / path.name


def reference_comparison_dir(result_type: str, results_root: Path = RESULTS_ROOT) -> Path:
    return results_root / "reference" / "comparisons" / result_type


def reference_case_dir(result_type: str, index: int, results_root: Path = RESULTS_ROOT) -> Path:
    return reference_comparison_dir(result_type, results_root=results_root) / f"Q{int(index)}"


def diagnosis_override_path(results_root: Path = RESULTS_ROOT) -> Path:
    return results_root / "reference" / "diagnosis_overrides" / "benchmark_mismatch_diagnoses.json"


def _relative_dict(payload: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, Path):
            normalized[key] = _repo_relative_string(value)
        elif isinstance(value, list):
            normalized[key] = [
                _repo_relative_string(item) if isinstance(item, Path) else item
                for item in value
            ]
        else:
            normalized[key] = value
    return normalized


def _repo_relative_string(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()
