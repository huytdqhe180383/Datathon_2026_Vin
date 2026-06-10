from __future__ import annotations

import argparse
import csv
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from time import perf_counter
from typing import Any

from sql_rag_agent.config import LLMConfig, ROOT, SchemaRetrievalConfig
from sql_rag_agent.evaluation import build_session_layout, build_session_manifest, session_type_from_run_id
from sql_rag_agent.graph import run_agent
from sql_rag_agent.llm import OpenAICompatibleLLMProvider
from sql_rag_agent.retrieval.schema_context import LlamaIndexSchemaRetriever
from sql_rag_agent.tools.mcp_postgres import PostgresMCPTool
from sql_rag_agent.tracing import TraceWriter


ADJUSTED_MISMATCH_IDS = {
    "value-Q7",
    "value-Q8",
    "value-Q9",
    "value-Q10",
    "value-Q14",
    "value-Q16",
    "value-Q17",
    "value-Q18",
    "value-Q19",
    "value-Q25",
    "value-Q26",
    "value-Q29",
    "value-Q30",
    "table-Q1",
    "table-Q2",
    "table-Q4",
    "table-Q5",
    "table-Q9",
    "table-Q10",
    "table-Q11",
    "table-Q12",
    "table-Q13",
    "table-Q15",
    "table-Q18",
    "table-Q19",
    "table-Q20",
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rerun SQL-RAG mismatched benchmark questions and log generated SQL."
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=ROOT / "results" / "reference" / "benchmark_runs" / "sql_rag_vs_pandasai_20260608T043329Z.json",
        help="Original benchmark JSON containing questions and reference SQL.",
    )
    parser.add_argument(
        "--case-set",
        choices=("all", "adjusted-mismatches", "strict-mismatches"),
        default="adjusted-mismatches",
        help="Question set to rerun. all reruns the full 30 value + 20 table benchmark.",
    )
    parser.add_argument(
        "--run-prefix",
        default=None,
        help="Optional run id prefix. Defaults to full_rerun for --case-set all, otherwise mismatch_rerun.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Override SQL_AGENT_LLM_STRONG_MODEL for this rerun.",
    )
    parser.add_argument(
        "--weak-model",
        default=None,
        help="Override SQL_AGENT_LLM_WEAK_MODEL for answer composition.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "results",
        help="Results root for session-based rerun artifacts.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional limit for smoke testing the runner.",
    )
    parser.add_argument(
        "--ids",
        nargs="+",
        default=None,
        help="Optional case ids to rerun, such as table-Q2 value-Q10.",
    )
    args = parser.parse_args()

    records = _load_records(args.source)
    selected_records = _select_records(records, args.case_set)
    if args.ids:
        requested_ids = set(args.ids)
        selected_records = [record for record in selected_records if record.get("id") in requested_ids]
        missing_ids = requested_ids - {record.get("id") for record in selected_records}
        if missing_ids:
            raise SystemExit(f"Requested ids are not in {args.case_set}: {sorted(missing_ids)}")
    if args.limit is not None:
        selected_records = selected_records[: max(0, args.limit)]

    llm_config = LLMConfig.from_env()
    if args.model or args.weak_model:
        llm_config = replace(
            llm_config,
            strong_model=args.model or llm_config.strong_model,
            weak_model=args.weak_model or llm_config.weak_model,
        )
    if not llm_config.is_configured:
        raise SystemExit("LLM is not configured. Set OPENAI_API_KEY and SQL_AGENT_USE_LLM=true.")

    model_label = _safe_label(llm_config.strong_model)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_prefix = args.run_prefix or _default_run_prefix(args.case_set)
    run_id = f"{run_prefix}_{model_label}_{timestamp}"
    session_type = session_type_from_run_id(run_id)
    layout = build_session_layout(
        session_type=session_type,
        session_id=run_id,
        results_root=args.output_dir,
    )
    for directory in (
        layout.root,
        layout.chunks_dir,
        layout.merged_dir,
        layout.comparisons_dir,
        layout.summaries_dir,
        layout.trace_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)
    json_path = layout.chunk_json_path(run_id)
    csv_path = layout.chunk_csv_path(run_id)

    mcp_tool = PostgresMCPTool()
    llm_provider = OpenAICompatibleLLMProvider(llm_config)
    retriever = LlamaIndexSchemaRetriever(
        config=SchemaRetrievalConfig.from_env(),
        mcp_tool=mcp_tool,
    )

    output_records = []
    for index, record in enumerate(selected_records, start=1):
        case_id = record["id"]
        print(f"[{index}/{len(selected_records)}] rerunning {case_id}: {record['question']}", flush=True)
        trace_writer = TraceWriter(
            log_dir=layout.trace_dir,
            trace_id=f"{run_id}_{case_id.replace('-', '_')}",
        )
        started = perf_counter()
        error = None
        state: dict[str, Any] = {}
        try:
            state = run_agent(
                record["question"],
                mcp_tool=mcp_tool,
                llm_provider=llm_provider,
                schema_retriever=retriever,
                trace_writer=trace_writer,
            )
        except Exception as exc:
            error = str(exc)

        elapsed = round(perf_counter() - started, 6)
        output_records.append(
            _record_from_run_state(
                source_record=record,
                state=state,
                model=llm_config.strong_model,
                weak_model=llm_config.weak_model,
                latency_seconds=elapsed,
                error=error,
                fallback_trace_id=trace_writer.trace_id,
                fallback_trace_path=str(trace_writer.path),
            )
        )

    payload = {
        "run_id": run_id,
        "session_type": session_type,
        "session_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": str(args.source),
        "case_set": args.case_set,
        "model": llm_config.strong_model,
        "weak_model": llm_config.weak_model,
        "question_count": len(output_records),
        "records": output_records,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2, default=str), encoding="utf-8")
    _write_csv(csv_path, output_records)
    manifest = build_session_manifest(
        layout,
        source_benchmark=args.source,
        strong_model=llm_config.strong_model,
        weak_model=llm_config.weak_model,
        question_count=len(output_records),
        chunk_files=[
            {
                "chunk_id": run_id,
                "json_path": json_path,
                "csv_path": csv_path,
                "question_count": len(output_records),
                "case_set": args.case_set,
            }
        ],
    )
    manifest.update(
        {
            "created_at": payload["created_at"],
            "case_set": args.case_set,
            "manifest_version": 1,
        }
    )
    layout.manifest_path.write_text(json.dumps(manifest, ensure_ascii=True, indent=2), encoding="utf-8")
    print(f"Wrote JSON: {json_path}")
    print(f"Wrote CSV: {csv_path}")
    print(f"Wrote manifest: {layout.manifest_path}")


def _load_records(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("records", [])
    if not isinstance(records, list):
        raise ValueError(f"Expected records list in {path}")
    return records


def _select_records(records: list[dict[str, Any]], case_set: str) -> list[dict[str, Any]]:
    if case_set == "all":
        selected = list(records)
    elif case_set == "adjusted-mismatches":
        selected = [record for record in records if record.get("id") in ADJUSTED_MISMATCH_IDS]
    else:
        selected = [record for record in records if not record.get("sql_rag_correct")]
    selected.sort(key=lambda item: (str(item.get("type")), int(item.get("index") or 0)))
    return selected


def _default_run_prefix(case_set: str) -> str:
    return "full_rerun" if case_set == "all" else "mismatch_rerun"


def _write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    columns = [
        "id",
        "type",
        "index",
        "question",
        "model",
        "weak_model",
        "latency_seconds",
        "generated_sql",
        "executed_sql",
        "reference_sql",
        "previous_sql_rag_sql",
        "row_count",
        "execution_error",
        "trace_path",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    key: _csv_value(record.get(key))
                    for key in columns
                }
            )


def _record_from_run_state(
    *,
    source_record: dict[str, Any],
    state: dict[str, Any],
    model: str,
    weak_model: str,
    latency_seconds: float,
    error: str | None,
    fallback_trace_id: str,
    fallback_trace_path: str,
) -> dict[str, Any]:
    candidate_sql = [item.get("sql") for item in state.get("candidate_sql", []) if item.get("sql")]
    execution_results = list(state.get("execution_results", []))
    selected_result = _ranked_successful_execution_result(state)
    selected_candidate_id = selected_result.get("candidate_id") if selected_result else None
    first_execution_error = next((item.get("error") for item in execution_results if item.get("error")), None)

    return {
        "id": source_record.get("id"),
        "type": source_record.get("type"),
        "index": source_record.get("index"),
        "question": source_record.get("question"),
        "model": model,
        "weak_model": weak_model,
        "latency_seconds": latency_seconds,
        "generated_sql": _candidate_sql_for_id(state, selected_candidate_id) or (candidate_sql[-1] if candidate_sql else None),
        "generated_sql_candidates": candidate_sql,
        "executed_sql": selected_result.get("sql") if selected_result else None,
        "reference_sql": source_record.get("pandas_sql"),
        "previous_sql_rag_sql": source_record.get("sql_rag_candidate_sql", []),
        "row_count": selected_result.get("row_count") if selected_result else 0,
        "execution_error": selected_result.get("error") if selected_result else error or first_execution_error,
        "agent_errors": state.get("errors", []),
        "final_answer": state.get("final_answer"),
        "trace_id": state.get("trace_id") or fallback_trace_id,
        "trace_path": state.get("trace_path") or fallback_trace_path,
    }


def _ranked_successful_execution_result(state: dict[str, Any]) -> dict[str, Any] | None:
    execution_results = [item for item in state.get("execution_results", []) if not item.get("error")]
    if not execution_results:
        return None
    by_candidate_id = {
        item.get("candidate_id"): item
        for item in execution_results
        if item.get("candidate_id")
    }
    for ranked in state.get("ranked_results", []):
        candidate_id = ranked.get("candidate_id")
        if candidate_id in by_candidate_id:
            return by_candidate_id[candidate_id]
    return execution_results[0]


def _candidate_sql_for_id(state: dict[str, Any], candidate_id: str | None) -> str | None:
    if not candidate_id:
        return None
    for candidate in state.get("candidate_sql", []):
        if candidate.get("candidate_id") == candidate_id:
            return candidate.get("sql")
    return None


def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=True, default=str)
    return str(value)


def _safe_label(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._-") or "model"


if __name__ == "__main__":
    main()
