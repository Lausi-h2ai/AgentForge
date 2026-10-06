# AgentForge

A multi-agent coding orchestrator using shared blackboard state and a centrally scheduled pipeline. AgentForge turns a high-level prompt into an implementation plan, code changes, review feedback, checkpoints, and final documentation.

The project demonstrates how agent tool loops fit into a larger workflow: what gets shared, how review feedback drives retries, and how progress survives a restart. LlamaIndex runs the inner ReAct loops; AgentForge controls planning, validation, retries, and persistence.

**Explore:** [Architecture](ARCHITECTURE.md) · [Design decisions](docs/DESIGN_DECISIONS.md) · [Providers](docs/PROVIDERS.md) · [Demo](DEMO.md) · [Evaluation](EVALUATION.md)

![AgentForge running local Qwen3.5-9B through llama.cpp](docs/evidence/local-qwen-demo/demo.gif)

This demo uses **Qwen3.5-9B Q4_K_M on an RTX 3070 with 8 GB VRAM**, served by
llama.cpp. Real agents plan, write files, review code, and persist checkpoints.
The animation replays captured events; the [run report](docs/evidence/local-qwen-demo/report.json)
records the measured outcome and independent acceptance checks. One small case is not a benchmark.

Recorded result: **3 tasks completed in 417.6 seconds, 1 retry, 10 generated tests
passed**, independent acceptance passed, and checkpoints restored successfully.

## Run with a local model

```powershell
./scripts/setup_local_qwen.ps1 -InstallPython
./scripts/start_local_qwen.ps1
```

In a second terminal:

```powershell
./.venv/Scripts/python.exe scripts/local_qwen_demo.py
```

The demo applies its local provider profile automatically. The server uses partial
CUDA offloading, 16K context, and one inference slot. See the [setup and restart
guide](docs/LOCAL_QWEN.md) to connect ordinary AgentForge runs or reduce memory use.

## Try it without a model

```bash
python -m pip install -e .[dev]
python scripts/portfolio_demo.py
python -m pytest -q
```

The offline demo uses scripted agents with real pipeline stages and file tools:
it creates a whitespace bug, fails review, transfers feedback into a retry, fixes
the file, and restores the completed checkpoint. It makes zero model calls.
See the [captured event record](docs/evidence/offline-demo.json).

This repository is the orchestrator itself. Generated applications under `projects/` are runtime artifacts and are intentionally ignored.

## Highlights

- Specialized agents for requirements, architecture, planning, development, review, testing, and documentation
- Extracted pipeline stages for planning, development, review, testing, and finalization
- Task checkpoints, resume support, and best-effort Git stash recovery
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

This is **blackboard-style orchestration**: explicit shared state with staged scheduling. General event-driven agent activation and concurrent blackboard writes are outside the current implementation.

## Requirements

- Python 3.11+
- Git
- Optional: Docker for `TesterAgent`
- A configured OpenAI-compatible chat endpoint (llama.cpp, vLLM, or a hosted provider)
- Optional legacy providers: Ollama or Google Gemini

## Installation

The distribution remains `aidev-orchestrator` and the Python package remains `aidev_orchestrator` for compatibility; AgentForge is the project name.

Create a virtual environment and install the repo in editable mode.

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .[dev]
```

For the default OpenAI-compatible provider:

```bash
pip install -e .[openai]
```

For Google-backed runs:

```bash
pip install -e .[google]
```

The legacy Ollama adapter is available with `pip install -e .[ollama]`.

## Configuration

Copy `.env.example` to `.env` and set only what you need.

Canonical runtime variables:

- `LLM_PROVIDER`
- `LLM_MODEL`
- `OPENAI_BASE_URL`
- `OPENAI_API_KEY`
- `LLM_ESCALATION_MODEL`
- `PROMPT_*_VERSION`
- `REVIEW_TIMEOUT_*`
- `ESCALATION_*`
- `PLANNER_ESCALATION_*`

Memory is optional and disabled in `.env.example` by default. Enable it only if you are also running the local supporting services.

For the generic provider, set the exact model ID and API root. Chat-only endpoints
work without embeddings; vector retrieval is opt-in. See [provider setup](docs/PROVIDERS.md).

## Quickstart

Use the included demo prompt:

```bash
python orchestrator.py demo_project --prompt examples/prompts/demo_prompt.txt --new
```

Useful variants:

```bash
python orchestrator.py myproject --prompt examples/prompts/demo_prompt.txt --new --with-tests
python orchestrator.py myproject --provider openai --prompt examples/prompts/demo_prompt.txt --new --planning-model your-planning-model --execution-model your-coding-model
python orchestrator.py myproject --prompt examples/prompts/demo_prompt.txt --new --google
```

Generated project files land under `projects/<name>/workspace/`. Logs and checkpoints remain in ignored runtime directories.

## Testing

Run the unit test suite with:

```bash
pytest -q
```

The committed test suite is designed to exercise orchestration logic and extracted stage behavior without requiring live model calls.

The [live evaluation suite](EVALUATION.md) measures completion, retries, time, and independent acceptance results for an explicitly selected model. Comparative cost estimates are distinguished from API billing.

## Project scope and authorship

AgentForge is an experimental orchestration harness. Review approval does not establish correctness, and generated-code execution is not fully sandboxed. See [architecture boundaries](ARCHITECTURE.md).

AI assistance was used for the portfolio documentation and evidence tooling. [Portfolio notes](docs/PORTFOLIO.md) explain how to discuss the design, credit framework functionality, and substantiate personal contributions.

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



