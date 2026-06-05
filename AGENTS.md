# Agent Instructions

- Use `uv` for Python environment and dependency management in this repository.
- Prefer `uv run ...` for Python commands, tests, and local scripts.
- Use the repo-local `.venv` created by `uv sync`.
- Do not recreate or reference the deleted `.venv_pandasai310` environment.
- Keep generated caches, LlamaIndex storage, and trace logs out of git.
