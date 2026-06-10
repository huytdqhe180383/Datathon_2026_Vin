# Agent Instructions

- Use `uv` for Python environment and dependency management in this repository.
- Prefer `uv run ...` for Python commands, tests, and local scripts.
- Use the repo-local `.venv` created by `uv sync`.
- Do not recreate or reference the deleted `.venv_pandasai310` environment.
- Keep generated caches, LlamaIndex storage, and trace logs out of git.

## Evaluation Artifacts

- Never write generated benchmark or evaluation files directly under `results/`.
- Use `results/reference/` only for curated, checked-in benchmark assets such as reference comparisons, benchmark inputs, diagnosis overrides, and human-written review notes.
- Use `results/sessions/<session_type>/<session_id>/` for generated run artifacts.
- Session folders should keep raw run outputs under `chunks/` or `merged/`, comparisons under `comparisons/`, manifests at `manifest.json`, and human-facing reports under `summaries/`.
- Raw agent traces for benchmark sessions belong under `logs/agent_traces/sessions/<session_type>/<session_id>/`.
- `summaries/summary.md` is the primary human-facing report for a session and must be detailed enough to review without opening each per-question folder.
- Every mismatch in `summary.md` must include an explicit diagnosis and a short evidence snippet.
- New evaluation or reporting scripts must use the shared results-layout helper instead of hardcoded root-level filenames or folder names.
