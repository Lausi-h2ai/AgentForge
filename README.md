# AI Development Orchestrator

A blackboard-style multi-agent coding orchestrator that turns a high-level prompt into an implementation plan, code changes, review feedback, checkpoints, and final documentation.

This repository is the orchestrator itself. Generated applications under `projects/` are runtime artifacts and are intentionally ignored.

## Highlights

- Specialized agents for requirements, architecture, planning, development, review, testing, and documentation
- Extracted pipeline stages for planning, development, review, testing, and finalization
- Checkpointing and Git-based rollback per task
- Prompt routing and skill injection
- Optional memory integration with HippocampAI
- Prebuilt RPG graph committed under `.rpg/` for fast codebase exploration

## Repository layout

- `aidev_orchestrator/`: packaged runtime modules, entrypoint logic, tool surface, and support utilities
- `orchestrator.py`: thin root CLI shim for backwards-compatible invocation
- `orchestrator_core/`: blackboard state, contracts, pipeline stages, model config
- `agents/`: specialized agents
- `prompts/`: versioned prompt templates and task overlays
- `examples/prompts/`: sanitized public example prompts
- `.rpg/`: committed semantic code graph

See `ARCHITECTURE.md` for the high-level execution model.

## Requirements

- Python 3.11+
- Git
- Optional: Docker for `TesterAgent`
- Optional: Ollama or Google Gemini depending on the provider you want to use

## Installation

Create a virtual environment and install the repo in editable mode.

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .[dev]
```

If you want to run the default local-provider path, install the optional extras too:

```bash
pip install -e .[ollama,memory,tester]
```

For Google-backed runs:

```bash
pip install -e .[google]
```

## Configuration

Copy `.env.example` to `.env` and set only what you need.

Canonical runtime variables:

- `LLM_PROVIDER`
- `LLM_MODEL`
- `LLM_ESCALATION_MODEL`
- `PROMPT_*_VERSION`
- `REVIEW_TIMEOUT_*`
- `ESCALATION_*`
- `PLANNER_ESCALATION_*`

Memory is optional and disabled in `.env.example` by default. Enable it only if you are also running the local supporting services.

## Quickstart

Use the included demo prompt:

```bash
python orchestrator.py demo_project --prompt examples/prompts/demo_prompt.txt --new
```

Useful variants:

```bash
python orchestrator.py myproject --prompt examples/prompts/demo_prompt.txt --new --with-tests
python orchestrator.py myproject --prompt examples/prompts/demo_prompt.txt --new --planning-model qwen3-coder:latest --execution-model qwen3-coder:latest
python orchestrator.py myproject --prompt examples/prompts/demo_prompt.txt --new --google
```

Generated project files land under `projects/<name>/workspace/`. Logs and checkpoints remain in ignored runtime directories.

## Testing

Run the unit test suite with:

```bash
pytest -q
```

The committed test suite is designed to exercise orchestration logic and extracted stage behavior without requiring live model calls.

## RPG graph

This repository commits a prebuilt RPG graph under `.rpg/`. It is intentionally public because it makes the codebase easier to inspect.

Examples:

```bash
npx -y -p rpg-encoder rpg-encoder info
npx -y -p rpg-encoder rpg-encoder search "coordinate workflow"
```

The `.rpg/README.md` file has additional MCP and CLI usage examples.

For a related graph-oriented codebase effort, see [microsoft/RPG-ZeroRepo](https://github.com/microsoft/RPG-ZeroRepo).

## Contributing

See `CONTRIBUTING.md` for the contributor workflow and `SECURITY.md` for disclosure guidance.

## License

MIT



