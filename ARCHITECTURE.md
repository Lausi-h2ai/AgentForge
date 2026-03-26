# Architecture Overview

This repository is a multi-agent coding orchestrator, not a generated application.

## Core flow

1. Requirements analysis
2. Architecture generation
3. SADT/SART task planning
4. Development loop per task
5. Review loop per task
6. Optional testing
7. Finalization and documentation

## Main components

- `aidev_orchestrator/`: packaged runtime modules, entrypoint logic, tool surface, logging, and prompt/skill helpers
- `orchestrator_core/blackboard.py`: shared mutable state
- `orchestrator.py`: thin root CLI shim for backwards-compatible invocation`r`n- `orchestrator_core/pipeline/`: extracted stage logic for planning, development, review, testing, and finalization
- `agents/`: specialized agents for each phase
- `aidev_orchestrator/`: packaged runtime modules including the safe tool surface exposed to execution agents
- `memory/`: optional HippocampAI integration
- `prompts/`: versioned prompt templates and task-type overlays

## Design notes

- The orchestrator keeps per-project state and checkpoints under ignored runtime directories.
- Prompt routing and skill injection are part of the normal execution path.
- The reviewer and planner include retry and escalation behavior.
- The committed `.rpg/` directory provides a prebuilt semantic graph for code exploration.


