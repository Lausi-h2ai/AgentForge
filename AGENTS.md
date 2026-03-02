# AGENTS.md

## Project Summary
Multi-agent coding orchestrator with a blackboard-style workflow. The system runs specialized agents (requirements, architecture, planning, development, review, testing, docs) to convert a high-level prompt into incremental code changes with retries, validation, checkpoints, and trace logging.

## Canonical Scope
- This repository's identity is the orchestrator itself.
- Sample generated applications are outputs of orchestrator runs, not project identity.

## Core Runtime
- Main entrypoint: `orchestrator.py`.
- Core package: `orchestrator_core/` (contracts, blackboard state, pipeline stages).
- Agent implementations: `agents/`.
- Tool surface for agents: `orchestrator_tools.py`.
- Per-project state/checkpoints: `projects/<project>/state.json`, `projects/<project>/checkpoints.json`.
- Prompt sets: `prompts/<agent>/<version>/...`.

## Agent Roles
- `agents/product_owner_agent.py`
- `agents/requirements_analyst_agent.py`
- `agents/software_architect_agent.py`
- `agents/sadt_sart_planner_agent.py`
- `agents/developer_agent.py`
- `agents/code_reviewer_agent.py`
- `agents/tester_agent.py`
- `agents/unit_test_agent.py`
- `agents/documentation_agent.py`

## Execution Flow
1. Requirements analysis.
2. Architecture generation.
3. SADT/SART planning into atomic tasks.
4. Development + review loop per task.
5. Optional tests.
6. Documentation and final reporting.

## Key Capabilities
- Prompt routing/versioning per agent and task/profile overlays.
- Reviewer circuit breaker, dynamic timeout, confidence score.
- Task-level model escalation for developer/reviewer when retries indicate loop + no-progress.
- Planner model escalation after configurable planning failures.
- Planner correction pass that patches invalid parseable plans before full regeneration.
- Local memory integration (HippocampAI) with project/agent/user scopes.

## Recent Notable Changes
- Removed hard planner action cap by default (optional `SADT_MAX_ACTIONS` env cap).
- Added task-level escalation policy and planner escalation config.
- Added `recall_memory` tool for developer/reviewer.
- Improved developer no-tool-call guard to avoid premature breaker trips on fragmented streaming outputs.
