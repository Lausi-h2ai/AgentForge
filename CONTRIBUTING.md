# Contributing

## Getting started

1. Create a virtual environment.
2. Install the project in editable mode:
   `pip install -e .[dev]`
3. If you want to run the orchestrator against Ollama, add:
   `pip install -e .[ollama,memory,tester]`
4. Copy `.env.example` to `.env` and set only the variables you need.

## Before opening a PR

- Run `pytest -q`
- Keep changes scoped and reversible.
- Update documentation when behavior or setup changes.
- Prefer adding or adjusting tests when fixing regressions.

## Repo conventions

- The repository itself is the orchestrator.
- Generated project output belongs under ignored runtime directories such as `projects/`.
- Public examples belong under `examples/`, not `project_prompts/`.
- Keep prompt templates general-purpose and avoid local paths or private data.
