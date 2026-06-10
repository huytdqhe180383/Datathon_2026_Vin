# Results Layout

`results/` is split into two roles:

- `reference/`: curated, checked-in benchmark assets and analysis.
- `sessions/`: generated outputs grouped by session type and session id.

## Reference

Use `results/reference/` for stable assets that developers should treat as the benchmark ground truth or review layer:

- `benchmark_runs/`: source benchmark JSON/CSV inputs.
- `comparisons/`: curated reference comparison folders for `table/` and `value/`.
- `diagnosis_overrides/`: checked-in mismatch labels and short benchmark-specific diagnoses.
- `reviews/`: human-written benchmark analysis notes.
- `summaries/`: curated baseline summaries.

## Sessions

Use `results/sessions/<session_type>/<session_id>/` for generated artifacts from a single run family:

- `chunks/`: raw chunk outputs such as `full_rerun_phase3_chunk01_...json`.
- `merged/`: merged session payloads when a run is combined across chunks.
- `comparisons/table/` and `comparisons/value/`: per-question comparison folders.
- `summaries/summary.md`: the main report developers should read first.
- `manifest.json`: machine-readable inventory of the session.

Session types currently include `full_rerun`, `mismatch_rerun`, `smoke`, and `legacy_import`.

## Traces

Raw agent traces live outside `results/` under:

`logs/agent_traces/sessions/<session_type>/<session_id>/`

## Reading Order

When reviewing a run:

1. Open `results/sessions/<session_type>/<session_id>/summaries/summary.md`.
2. Use `manifest.json` to locate merged outputs, chunk files, and trace folders.
3. Drop into `comparisons/table/Q...` or `comparisons/value/Q...` only for case-level detail beyond the summary.
