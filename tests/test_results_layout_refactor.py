from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))
sys.path.append(str(ROOT / "src"))

from sql_rag_agent.evaluation.results_layout import (  # type: ignore[attr-defined]
    build_session_layout,
    build_session_manifest,
    classify_legacy_result_artifact,
    session_type_from_run_id,
)
from sql_rag_agent.evaluation.reporting import (  # type: ignore[attr-defined]
    diagnose_case,
    render_session_summary_markdown,
    summarize_session_results,
)


def test_session_layout_builds_expected_paths_for_full_mismatch_and_smoke_runs():
    full_layout = build_session_layout(
        session_type="full_rerun",
        session_id="full_rerun_phase3_chunk01_gpt-5.4-high_20260610T022911Z",
        results_root=ROOT / "results",
        trace_sessions_root=ROOT / "logs" / "agent_traces" / "sessions",
    )
    mismatch_layout = build_session_layout(
        session_type="mismatch_rerun",
        session_id="mismatch_rerun_gpt-5.4-high_20260609T034001Z",
        results_root=ROOT / "results",
        trace_sessions_root=ROOT / "logs" / "agent_traces" / "sessions",
    )
    smoke_layout = build_session_layout(
        session_type="smoke",
        session_id="smoke_full_rerun_gpt-5.4-nano_20260609T093317Z",
        results_root=ROOT / "results",
        trace_sessions_root=ROOT / "logs" / "agent_traces" / "sessions",
    )

    assert session_type_from_run_id(full_layout.session_id) == "full_rerun"
    assert session_type_from_run_id(mismatch_layout.session_id) == "mismatch_rerun"
    assert session_type_from_run_id(smoke_layout.session_id) == "smoke"

    assert full_layout.root == ROOT / "results" / "sessions" / "full_rerun" / full_layout.session_id
    assert full_layout.chunk_json_path(full_layout.session_id) == full_layout.root / "chunks" / f"{full_layout.session_id}.json"
    assert full_layout.chunk_csv_path(full_layout.session_id) == full_layout.root / "chunks" / f"{full_layout.session_id}.csv"
    assert mismatch_layout.merged_json_path(f"{mismatch_layout.session_id}_merged") == (
        mismatch_layout.root / "merged" / f"{mismatch_layout.session_id}_merged.json"
    )
    assert smoke_layout.summary_markdown_path == smoke_layout.root / "summaries" / "summary.md"
    assert smoke_layout.comparison_case_dir("table", 1) == smoke_layout.root / "comparisons" / "table" / "Q1"
    assert mismatch_layout.trace_dir == (
        ROOT / "logs" / "agent_traces" / "sessions" / "mismatch_rerun" / mismatch_layout.session_id
    )


def test_session_manifest_uses_repo_relative_paths_for_chunks_merged_outputs_and_summaries():
    layout = build_session_layout(
        session_type="mismatch_rerun",
        session_id="mismatch_rerun_gpt-5.4-high_20260609T034001Z",
        results_root=ROOT / "results",
        trace_sessions_root=ROOT / "logs" / "agent_traces" / "sessions",
    )

    manifest = build_session_manifest(
        layout,
        source_benchmark=ROOT / "results" / "reference" / "benchmark_runs" / "sql_rag_vs_pandasai_20260608T043329Z.json",
        strong_model="gpt-5.4-high",
        weak_model="gpt-5.4-nano",
        question_count=26,
        chunk_files=[
            {
                "chunk_id": layout.session_id,
                "json_path": layout.chunk_json_path(layout.session_id),
                "csv_path": layout.chunk_csv_path(layout.session_id),
                "question_count": 26,
            }
        ],
        merged_outputs={
            "json_path": layout.merged_json_path(f"{layout.session_id}_merged"),
            "csv_path": layout.merged_csv_path(f"{layout.session_id}_merged"),
        },
        comparison_paths={
            "table_dir": layout.comparisons_dir / "table",
            "value_dir": layout.comparisons_dir / "value",
        },
        summary_paths={
            "markdown_path": layout.summary_markdown_path,
            "json_path": layout.summary_json_path,
        },
    )

    assert manifest["source_benchmark"] == "results/reference/benchmark_runs/sql_rag_vs_pandasai_20260608T043329Z.json"
    assert manifest["trace_dir"] == (
        "logs/agent_traces/sessions/mismatch_rerun/mismatch_rerun_gpt-5.4-high_20260609T034001Z"
    )
    assert manifest["chunk_files"][0]["json_path"] == (
        "results/sessions/mismatch_rerun/mismatch_rerun_gpt-5.4-high_20260609T034001Z/chunks/"
        "mismatch_rerun_gpt-5.4-high_20260609T034001Z.json"
    )
    assert manifest["merged_outputs"]["json_path"].endswith("_merged.json")
    assert manifest["summary_paths"]["markdown_path"].endswith("/summaries/summary.md")


def test_diagnosis_layer_detects_row_limit_execution_errors_and_manual_override_precedence():
    row_limit_case = {
        "id": "table-Q11",
        "type": "table",
        "question": "Return a table showing signup-month cohorts.",
        "status": "ok",
        "match": False,
        "unordered_match": False,
        "ordering_only_mismatch": False,
        "reason": "shape_mismatch",
        "classification": "shape_mismatch",
        "reference_shape": [132, 5],
        "agent_shape": [100, 5],
        "reference_columns": ["signup_month", "customers_signed_up"],
        "agent_columns": ["signup_month", "customers_signed_up"],
        "execution_error": None,
        "diff_preview": [],
    }
    error_case = {
        "id": "table-Q1",
        "type": "table",
        "question": "Return a table with the top acquisition channels.",
        "status": "error",
        "match": False,
        "unordered_match": False,
        "ordering_only_mismatch": False,
        "reason": "column_mismatch",
        "classification": "column_mismatch",
        "reference_shape": [6, 4],
        "agent_shape": [0, 0],
        "reference_columns": ["acquisition_channel"],
        "agent_columns": [],
        "execution_error": "statement timeout",
        "diff_preview": [],
    }

    assert diagnose_case(row_limit_case)["label"] == "row_limit_truncation"
    assert diagnose_case(error_case)["label"] == "timeout_or_execution_issue"

    override = diagnose_case(
        row_limit_case,
        overrides={
            "table-Q11": {
                "label": "output_contract_mismatch",
                "summary": "Manual override wins.",
                "evidence": "Imported benchmark note.",
            }
        },
    )
    assert override["label"] == "output_contract_mismatch"
    assert override["summary"] == "Manual override wins."
    assert override["evidence"] == "Imported benchmark note."


def test_summary_renderer_highlights_each_mismatch_with_diagnosis_and_notable_wins():
    manifest = {
        "session_type": "mismatch_rerun",
        "session_id": "mismatch_rerun_gpt-5.4-high_20260609T034001Z",
        "source_benchmark": "results/reference/benchmark_runs/sql_rag_vs_pandasai_20260608T043329Z.json",
        "strong_model": "gpt-5.4-high",
        "weak_model": "gpt-5.4-nano",
        "question_count": 3,
        "merged_outputs": {"json_path": "results/sessions/mismatch_rerun/.../merged/run.json"},
        "comparison_paths": {"table_dir": "results/sessions/mismatch_rerun/.../comparisons/table"},
        "summary_paths": {"markdown_path": "results/sessions/mismatch_rerun/.../summaries/summary.md"},
        "trace_dir": "logs/agent_traces/sessions/mismatch_rerun/...",
    }
    results = [
        {
            "id": "value-Q7",
            "type": "value",
            "index": 7,
            "question": "Which payment method has the highest return rate, and what is that rate?",
            "status": "ok",
            "match": False,
            "unordered_match": False,
            "ordering_only_mismatch": False,
            "classification": "value_mismatch",
            "reason": "value_mismatch",
            "unordered_reason": "value_mismatch",
            "generated_sql": "SELECT payment_method, return_rate FROM demo",
            "reference_sql": "SELECT payment_method, return_rate_pct FROM demo",
            "reference_shape": [1, 2],
            "agent_shape": [1, 2],
            "reference_columns": ["payment_method", "return_rate_pct"],
            "agent_columns": ["payment_method", "return_rate"],
            "execution_error": None,
            "diff_preview": ["return_rate_pct differs: 8.9159 vs 0.0890"],
        },
        {
            "id": "table-Q3",
            "type": "table",
            "index": 3,
            "question": "Return a table of order counts by payment_method and order_status.",
            "status": "ok",
            "match": False,
            "unordered_match": True,
            "ordering_only_mismatch": True,
            "classification": "ordering_only",
            "reason": "value_mismatch",
            "unordered_reason": "exact_after_normalization",
            "generated_sql": "SELECT payment_method, order_status, order_count FROM demo ORDER BY order_count DESC",
            "reference_sql": "SELECT payment_method, order_status, order_count FROM demo ORDER BY payment_method",
            "reference_shape": [12, 3],
            "agent_shape": [12, 3],
            "reference_columns": ["payment_method", "order_status", "order_count"],
            "agent_columns": ["payment_method", "order_status", "order_count"],
            "execution_error": None,
            "diff_preview": ["row ordering differs"],
        },
        {
            "id": "value-Q1",
            "type": "value",
            "index": 1,
            "question": "What is the total number of orders?",
            "status": "ok",
            "match": True,
            "unordered_match": True,
            "ordering_only_mismatch": False,
            "classification": "exact_after_normalization",
            "reason": "exact_after_normalization",
            "unordered_reason": "exact_after_normalization",
            "generated_sql": "SELECT COUNT(*) AS total_orders FROM demo",
            "reference_sql": "SELECT COUNT(*) AS total_orders FROM demo",
            "reference_shape": [1, 1],
            "agent_shape": [1, 1],
            "reference_columns": ["total_orders"],
            "agent_columns": ["total_orders"],
            "execution_error": None,
            "diff_preview": [],
        },
    ]
    overrides = {
        "value-Q7": {
            "label": "ambiguous_reference_or_prompt",
            "summary": "The agent used returns-table logic and a fractional rate instead of the benchmark's status-based percent output.",
            "evidence": "Reference expects `return_rate_pct`; agent returned `return_rate = 0.0890`.",
        }
    }

    payload = summarize_session_results(manifest=manifest, results=results, overrides=overrides)
    markdown = render_session_summary_markdown(payload)

    assert payload["metrics"]["total_questions"] == 3
    assert payload["metrics"]["ordered_matches"] == 1
    assert payload["metrics"]["unordered_matches"] == 2
    assert payload["metrics"]["ordering_only_mismatches"] == 1
    assert payload["metrics"]["ordered_accuracy"] == "33.33%"
    mismatch_by_id = {item["question_id"]: item for item in payload["mismatch_index"]}
    assert mismatch_by_id["value-Q7"]["diagnosis_label"] == "ambiguous_reference_or_prompt"
    assert "## Mismatch Index" in markdown
    assert "value-Q7" in markdown
    assert "ambiguous_reference_or_prompt" in markdown
    assert "The agent used returns-table logic and a fractional rate" in markdown
    assert "Reference expects `return_rate_pct`; agent returned `return_rate = 0.0890`." in markdown
    assert "## Detailed Mismatches" in markdown
    assert "### value-Q7" in markdown
    assert "### table-Q3" in markdown
    assert "## Notable Wins" in markdown
    assert "value-Q1" in markdown
    assert "table-Q3" in markdown


def test_legacy_result_artifacts_map_to_reference_session_and_legacy_import_destinations():
    assert classify_legacy_result_artifact(ROOT / "results" / "sql_rag_vs_pandasai_20260608T043329Z.json") == (
        ROOT / "results" / "reference" / "benchmark_runs" / "sql_rag_vs_pandasai_20260608T043329Z.json"
    )
    assert classify_legacy_result_artifact(ROOT / "results" / "table_output_comparison") == (
        ROOT / "results" / "reference" / "comparisons" / "table"
    )
    assert classify_legacy_result_artifact(
        ROOT / "results" / "table_output_mismatch_rerun_gpt-5.4-high_20260609T034001Z"
    ) == (
        ROOT
        / "results"
        / "sessions"
        / "mismatch_rerun"
        / "mismatch_rerun_gpt-5.4-high_20260609T034001Z"
        / "comparisons"
        / "table"
    )
    assert classify_legacy_result_artifact(ROOT / "results" / "full_rerun_phase3_chunk01_gpt-5.4-high_20260610T022911Z.json") == (
        ROOT
        / "results"
        / "sessions"
        / "full_rerun"
        / "full_rerun_phase3_chunk01_gpt-5.4-high_20260610T022911Z"
        / "chunks"
        / "full_rerun_phase3_chunk01_gpt-5.4-high_20260610T022911Z.json"
    )
    assert classify_legacy_result_artifact(ROOT / "results" / "scratch_notes.txt") == (
        ROOT / "results" / "sessions" / "legacy_import" / "scratch_notes.txt"
    )
