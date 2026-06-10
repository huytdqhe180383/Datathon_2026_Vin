from pathlib import Path
import json
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))
sys.path.append(str(ROOT / "src"))

from sql_rag_agent.evaluation import build_session_layout
from scripts import build_mismatch_rerun_comparisons as comparisons
from scripts import rerun_mismatched_questions as rerun


def test_adjusted_mismatch_set_covers_26_reference_cases_without_ordering_only_cases():
    source = ROOT / "results" / "reference" / "benchmark_runs" / "sql_rag_vs_pandasai_20260608T043329Z.json"
    records = rerun._load_records(source)

    selected = rerun._select_records(records, "adjusted-mismatches")
    selected_ids = {record["id"] for record in selected}

    assert len(rerun.ADJUSTED_MISMATCH_IDS) == 26
    assert selected_ids == rerun.ADJUSTED_MISMATCH_IDS
    assert sum(1 for record in selected if record["type"] == "value") == 13
    assert sum(1 for record in selected if record["type"] == "table") == 13
    assert all(not record.get("ordering_only_mismatch") for record in selected)


def test_all_case_set_covers_full_50_question_benchmark():
    source = ROOT / "results" / "reference" / "benchmark_runs" / "sql_rag_vs_pandasai_20260608T043329Z.json"
    records = rerun._load_records(source)

    selected = rerun._select_records(records, "all")

    assert len(selected) == 50
    assert sum(1 for record in selected if record["type"] == "value") == 30
    assert sum(1 for record in selected if record["type"] == "table") == 20
    assert selected[0]["id"] == "table-Q1"
    assert selected[-1]["id"] == "value-Q30"
    assert rerun._default_run_prefix("all") == "full_rerun"


def test_rerun_log_uses_ranked_sql_when_multiple_candidates_exist():
    record = {
        "id": "value-Q8",
        "type": "value",
        "index": 8,
        "question": "What share of total net revenue comes from orders that used at least one promo code?",
        "pandas_sql": "SELECT reference_sql",
        "sql_rag_candidate_sql": ["SELECT old_sql"],
    }
    state = {
        "candidate_sql": [
            {"candidate_id": "generic_discount", "sql": "SELECT discount_amount_sql"},
            {"candidate_id": "promo_bridge", "sql": "SELECT promo_bridge_sql"},
        ],
        "ranked_results": [
            {"candidate_id": "promo_bridge", "score": 95},
            {"candidate_id": "generic_discount", "score": 65},
        ],
        "execution_results": [
            {
                "candidate_id": "generic_discount",
                "sql": "SELECT discount_amount_sql",
                "rows": [{"promo_share_pct": 10}],
                "row_count": 1,
                "error": None,
            },
            {
                "candidate_id": "promo_bridge",
                "sql": "SELECT promo_bridge_sql",
                "rows": [{"promo_share_pct": 25}],
                "row_count": 1,
                "error": None,
            },
        ],
        "final_answer": "25",
        "trace_id": "trace",
        "trace_path": "trace.jsonl",
        "errors": [],
    }

    output = rerun._record_from_run_state(
        source_record=record,
        state=state,
        model="gpt-5.4-high",
        weak_model="gpt-5.4-mini",
        latency_seconds=1.234,
        error=None,
        fallback_trace_id="fallback",
        fallback_trace_path="fallback.jsonl",
    )

    assert output["generated_sql"] == "SELECT promo_bridge_sql"
    assert output["executed_sql"] == "SELECT promo_bridge_sql"
    assert output["row_count"] == 1
    assert output["reference_sql"] == "SELECT reference_sql"
    assert output["generated_sql_candidates"] == [
        "SELECT discount_amount_sql",
        "SELECT promo_bridge_sql",
    ]


def test_mismatch_rerun_result_folders_have_summaries_and_case_outputs():
    layout = build_session_layout(
        session_type="mismatch_rerun",
        session_id="mismatch_rerun_gpt-5.4-high_20260609T034001Z",
    )
    table_summary = json.loads((layout.comparisons_dir / "table" / "summary.json").read_text(encoding="utf-8"))
    value_summary = json.loads((layout.comparisons_dir / "value" / "summary.json").read_text(encoding="utf-8"))
    session_summary = json.loads(layout.summary_json_path.read_text(encoding="utf-8"))

    assert table_summary["question_count"] == 13
    assert value_summary["question_count"] == 13
    assert table_summary["ordered_match_count"] + value_summary["ordered_match_count"] == 1
    assert table_summary["unordered_match_count"] + value_summary["unordered_match_count"] == 1
    assert table_summary["error_count"] + value_summary["error_count"] == 1
    assert session_summary["metrics"]["total_questions"] == 26
    assert layout.summary_markdown_path.exists()

    for summary in (table_summary, value_summary):
        output_dir = layout.comparisons_dir / summary["type"]
        assert (output_dir / "summary.md").exists()
        for item in summary["results"]:
            case_dir = output_dir / f"Q{item['index']}"
            assert (case_dir / "comparison.json").exists()
            assert (case_dir / "agent_output.csv").exists()
            assert (case_dir / "reference_sql.csv").exists()


def test_summary_counts_treat_ordered_and_unordered_matches_separately():
    counts = comparisons._summary_counts(
        [
            {"status": "ok", "match": True, "unordered_match": True, "ordering_only_mismatch": False},
            {"status": "ok", "match": False, "unordered_match": True, "ordering_only_mismatch": True},
            {"status": "error", "match": False, "unordered_match": False, "ordering_only_mismatch": False},
        ]
    )

    assert counts == {
        "question_count": 3,
        "ok_count": 2,
        "ordered_match_count": 1,
        "unordered_match_count": 2,
        "ordering_only_count": 1,
        "mismatch_count_ordered": 2,
        "mismatch_count_unordered": 1,
        "error_count": 1,
    }
def test_full_rerun_layout_routes_artifacts_into_session_directories():
    layout = build_session_layout(
        session_type="full_rerun",
        session_id="full_rerun_phase3_chunk01_gpt-5.4-high_20260610T022911Z",
    )

    assert layout.chunk_json_path(layout.session_id) == (
        ROOT
        / "results"
        / "sessions"
        / "full_rerun"
        / "full_rerun_phase3_chunk01_gpt-5.4-high_20260610T022911Z"
        / "chunks"
        / "full_rerun_phase3_chunk01_gpt-5.4-high_20260610T022911Z.json"
    )
    assert layout.trace_dir == (
        ROOT
        / "logs"
        / "agent_traces"
        / "sessions"
        / "full_rerun"
        / "full_rerun_phase3_chunk01_gpt-5.4-high_20260610T022911Z"
    )
