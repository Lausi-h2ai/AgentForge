# Autonomous AI Software Development Team (AiDevSquad)

This project implements a multi?agent AI system designed to autonomously develop, review, test, and document software projects from a high?level user prompt. It simulates a team of AI agents, each with a specialized role, working together to deliver a complete, version?controlled software application.

## Features

- **Multi?Agent Architecture:** Specialized agents for requirements, architecture, planning, development, review, testing, and documentation.
  - `SADTSARTPlannerAgent`: SADT/SART hierarchical planning ? atomic actions.
  - `ProductOwnerAgent`: Vision holder and requirements consultant.
  - `RequirementsAnalystAgent`: Refines requirements and asks clarifying questions.
  - `SoftwareArchitectAgent`: Produces technical architecture + file structure.
  - `DeveloperAgent`: Executes tasks using a ReAct tool suite.
  - `CodeReviewerAgent`: Fast review with **circuit breaker** and **confidence score**.
  - `UnitTestAgent`: Generates `pytest` unit tests.
  - `DocumentationAgent`: Writes final project `README.md`.
- **Skills System:** `SkillManager` loads `skills/*/SKILL.md` and injects relevant guidance per task to improve agent performance without bloating context.
- **Dynamic Review Timeout:** Review timeouts scale with change complexity (files/diff size).
- **Reviewer Guardrails:** Circuit breaker stops repeated tool loops; review output includes a confidence score; false?positive syntax errors are filtered.
- **Phase?Based Models:** Use one model for planning and another for execution (sequentially, no dual?model VRAM load).
- **RAG?Powered Context:** Uses LlamaIndex to provide relevant code context.
- **Pluggable LLM Providers:** Switch between local (Ollama) and cloud (Google Gemini).
- **Cost & Usage Tracking:** Tracks token usage and estimates cost per model.
- **Structured Trace Logging:** Markdown/JSON traces for debugging and monitoring.
- **Agent Memory (HippocampAI):** Local memory with Qdrant + Ollama to share decisions, constraints, and retry context.

## System Architecture

The system is orchestrated by a central `Orchestrator` class through these phases:

1. **Requirements Analysis**: `RequirementsAnalystAgent` refines the prompt and asks clarifying questions.
2. **Architecture Design**: `SoftwareArchitectAgent` defines stack, file structure, and components.
3. **Task Planning**: `SADTSARTPlannerAgent` produces a hierarchical plan and flattens to atomic actions.
4. **Development Loop**: `DeveloperAgent` executes each task using tools.
5. **Review Loop**: `CodeReviewerAgent` validates changes (with timeout/circuit breaker/validation).
6. **Testing (Optional)**: `UnitTestAgent` + `TesterAgent` run tests if enabled.
7. **Documentation**: `DocumentationAgent` generates final project docs.

## Setup & Installation

### Prerequisites
- Python 3.11+
- Git
- Docker (for `TesterAgent`)
- (Optional) [Ollama](https://ollama.com/) for local models

### Installation

```bash
git clone https://github.com/sancelot/AIdevSquad
cd AIdevSquad

python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### LLM Provider Configuration

Create `.env` from `.env.example` and set provider keys:

- **Google Gemini**: `GOOGLE_API_KEY="..."`
- **Ollama**: ensure `ollama serve` is running and models are pulled.

### Memory Configuration (Local Only)

This project uses HippocampAI memory with local Qdrant + Ollama. Set these in `.env`:

- `HIPPOCAMP_AI_ENABLED=true`
- `HIPPOCAMP_AI_LLM_PROVIDER=ollama`
- `HIPPOCAMP_AI_LLM_MODEL=gemma3:4b` (can be different from agent models)
- `HIPPOCAMP_AI_OLLAMA_BASE_URL=http://localhost:11434`
- `HIPPOCAMP_AI_VISIBILITY=private`
- `HIPPOCAMP_AI_RUN_ID=`
- `QDRANT_URL=http://localhost:6333`

Memory is scoped by project and agent, with an optional global scope for cross-project learnings.

## Model Selection (Planning vs Execution)

You can run **different models per phase** (sequentially, no dual load):

### CLI Flags
```bash
python orchestrator.py myproject --prompt myrequirements.txt \
  --planning-model qwen2.5:latest \
  --execution-model qwen3-coder:latest
```

### Environment Variables
For **Ollama**:
- `OLLAMA_PLANNING_MODEL`
- `OLLAMA_EXECUTION_MODEL`
- `OLLAMA_MODEL` (fallback)

For **Google**:
- `GOOGLE_PLANNING_MODEL`
- `GOOGLE_EXECUTION_MODEL`
- `GOOGLE_MODEL` (fallback)

Reviewer timeout tuning:
- `REVIEW_TIMEOUT_SIMPLE`
- `REVIEW_TIMEOUT_MEDIUM`
- `REVIEW_TIMEOUT_COMPLEX`

If no model is specified, the same model is used for all phases.

## How to Run

```bash
python orchestrator.py myproject --prompt myrequirements.txt
```

**Start a new project (clears workspace):**
```bash
python orchestrator.py myproject --new --prompt myrequirements.txt
```

**Enable tests:**
```bash
python orchestrator.py myproject --with-tests --prompt myrequirements.txt
```

**Use Google provider:**
```bash
python orchestrator.py myproject --google --prompt myrequirements.txt
```

Trace logs are saved in `logs/`, and generated projects live in `projects/<name>/workspace`.

## Skills System

Skills live under `skills/**/SKILL.md` and are loaded at startup. For each task, the orchestrator injects relevant skills into the agent prompt. Skills are **per?task** and do not persist across tasks.

## Testing

Run unit tests:
```bash
pytest -q
```

Included tests cover:
- SkillManager detection/injection
- Orchestrator pipeline (mocked smoke + minimal integration + contract checks)

## Monitoring UI

A Flask UI can visualize traces:

```bash
cd monitoring_ui
pip install -r requirements.txt
flask run --port=5001
```

Open `http://127.0.0.1:5001`.

## Contributing

Contributions welcome. Areas to improve:
- More skills and better skill targeting
- Enhanced reviewer heuristics
- Broader test coverage
- Monitoring UI enhancements

## License

MIT License. See `LICENSE`.
