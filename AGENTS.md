# AGENTS.md

## Project Summary
Smart Pantry & Recipe App (Paintroo): a single-user MVP that manages pantry items, parses receipts via OCR, and generates recipes using local Ollama LLMs. Backend is Python/FastAPI with PostgreSQL; frontend is React + TypeScript + Tailwind. Goals are end-to-end flow (pantry CRUD, recipe generation, receipt upload/parse/apply, meal history) with strong validation, error handling, and responsive UI.

## Core Logic
- Pantry items are stored in DB, normalized for search/autocomplete, and merged on duplicates.
- Recipe generation uses pantry items + user preferences to prompt an Ollama model, returning structured JSON.
- Receipt flow: upload file -> OCR text -> regex parse (fast) or Ollama parse (accurate) -> user selection -> apply to pantry.
- Meal history tracks cooked recipes and computes diversity metrics to avoid repetition.

## How It Works Together
- Orchestrator coordinates agents, planning, development, review, tests, and state persistence.
- Planner (SADTSARTPlannerAgent) turns requirements + architecture into atomic tasks.
- Developer agent implements tasks; reviewer agent performs fast checks and returns structured issues.
- State is saved in `projects/<project>/state.json` and checkpoints in `projects/<project>/checkpoints.json`.

## Key Files and Responsibilities
- `orchestrator.py`: Main workflow engine; manages planning, task execution, review, retries, logging, and state.
- `orchestrator_tools.py`: Tooling interface for agents (read/write/submit_review), with review schema definitions.
- `agents/sadt_sart_planner_agent.py`: Generates hierarchical plan and flattens to atomic actions.
- `agents/code_reviewer_agent.py`: Fast reviewer with timeout, circuit breaker, and confidence scoring.
- `smart_pantry_ollama_prompt_IMPROVED.txt`: Full requirements/spec used for planning.
- `projects/paintroo/state.json`: Current plan, architecture, run command, and planner metadata.

## Agent Roles (Key Files)
- `agents/product_owner_agent.py`: Clarifies product goals and scope.
- `agents/requirements_analyst_agent.py`: Refines requirements into actionable specs.
- `agents/software_architect_agent.py`: Produces technical architecture and file structure.
- `agents/sadt_sart_planner_agent.py`: Generates hierarchical workplans and atomic tasks.
- `agents/developer_agent.py`: Implements tasks by modifying code.
- `agents/code_reviewer_agent.py`: Fast review with circuit breaker and confidence.
- `agents/tester_agent.py`: Runs quality gates when enabled.
- `agents/unit_test_agent.py`: Produces unit tests.
- `agents/documentation_agent.py`: Generates README/docs.

## Skills System
- Skills are modular instruction bundles stored under `skills/` and injected by `SkillManager`.
- Orchestrator injects skills into agents? system prompts based on task description and token budget.
- Skills are not global; they are applied per task to keep context small and relevant.
- Architecture integration: skills influence planning, coding, and review behavior without changing code directly.

## Runtime Flow (High Level)
1. Load requirements + architecture.
2. Generate plan (SADT planner).
3. For each task: developer edits files -> reviewer checks -> optional tests -> state saved.
4. Final documentation generated on success.

﻿# AGENTS.md

## Memory (2026-02-05)
- Investigated missing plan steps in `projects/paintroo/state.json`. Found `plan` and `sadt_plan` were exactly 100 tasks and lacked OCR/Ollama/Tesseract/LLM tasks.
- Root cause: `agents/sadt_sart_planner_agent.py` capped `max_total_actions` to 100 for complex projects. Updated it to remove the hard cap and allow unlimited actions by default. Added optional env cap `SADT_MAX_ACTIONS` (positive integer) to re-enable a budget if desired. Log now reports “no action budget limit” when unset.
- Regeneration approach: user requested manual planning (no scripts). Used `smart_pantry_ollama_prompt_IMPROVED.txt` and `technical_architecture` from `projects/paintroo/state.json` to create a new untruncated plan (140 tasks) explicitly including OCR + Ollama integration.
- Wrote the new plan into `projects/paintroo/state.json` (`plan` and `sadt_plan`), set `planner_source` to `sadt`, and reset `last_completed_task_index` to `-1`.
- Current state: `state.json` now has 140 tasks including OCR/Ollama tasks; planner code no longer truncates unless `SADT_MAX_ACTIONS` is set.

## Memory (2026-02-05) - Reviewer Circuit Breaker + Confidence
- Added circuit breaker to CodeReviewerAgent tool calls: wraps reviewer tools and raises CircuitBreakerError if same tool call repeats 3x. Review returns a major integration_issue when tripped.
- Reviewer timeouts now dynamic: added REVIEW_TIMEOUT_CONFIG and heuristics in orchestrator; timeout set per task based on file count/diff size.
- Added review findings validation in orchestrator: currently filters false-positive Python syntax errors using compile() check.
- Updated reviewer prompt to match dynamic timeout using a template with runtime substitution.
- Added reviewer confidence scores: ReviewReport now accepts optional confidence (0.0–1.0). submit_review outputs confidence. Reviewer tool wrapper auto-injects confidence if missing (simple heuristic based on tool usage).
- Updated allowed review issue types to include syntax_error.

## Memory (2026-02-17) - Prompt Routing v2
- Added rule-based task-type prompt routing in `agents/prompt_router.py` with task classes:
  `create_file`, `modify_file`, `bugfix`, `refactor`, `test_write`, `review`.
- Developer and reviewer now load base + enhanced/system prompts plus task-type overlays from:
  `prompts/developer/<version>/task_types/*.md` and `prompts/reviewer/<version>/task_types/*.md`.
- Added prompt set `v2` with stronger reliability rules (canonical tool-call format, anti-loop guidance, explicit done criteria) and code-quality focus.
- `.env.example` now defaults to `PROMPT_DEVELOPER_VERSION=v2` and `PROMPT_REVIEWER_VERSION=v2`.

## Memory (2026-02-13) - HippocampAI Local Memory Integration
- Added local HippocampAI memory wrapper under `memory/` with safe imports and scoped user IDs (project, agent, global).
- Orchestrator now injects memory context into requirements, architecture, planning, developer, and reviewer prompts.
- Memory writes on requirements/architecture, task completion summaries, and retry failures to reduce repeated errors and invalid tool calls.
- Default local configuration expects Qdrant at `http://localhost:6333` and Ollama model `gemma3:4b`.
