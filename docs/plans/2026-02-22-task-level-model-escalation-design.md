# Task-Level Model Escalation Design (V1)

Date: 2026-02-22  
Project: Multi-agent coding orchestrator with blackboard architecture  
Status: Approved for implementation planning

## Problem

Lower-capacity local models can get stuck in repeated failure loops for specific tasks. This causes wasted retries, slow progress, and avoidable run failures.

## Goal

Add a task-level fallback that temporarily elevates model quality when a task is demonstrably stuck, while preserving existing retry, timeout, and circuit-breaker safeguards.

## Confirmed V1 Decisions

- Escalation scope is task-level, not run-level or global agent-level.
- Trigger uses a combined signal only:
  - repeated behavior pattern count `>= 3`
  - no-progress retry count `>= 2`
- Once escalated, the stronger model remains active for that task until task completion or existing failure safeguards terminate the task.
- Model selection is static via environment configuration.
- V1 applies to `DeveloperAgent` and `CodeReviewerAgent` only.

## Architecture

Implement escalation policy in the orchestrator task loop so behavior is centralized and consistent across agents.

Add a module such as `orchestrator_core/pipeline/task_escalation.py` containing:

- `TaskEscalationConfig`
  - thresholds, enabled agents, feature flag, escalation model map by provider.
- `TaskEscalationState`
  - per-task counters and flags:
    - `repeat_count`
    - `no_progress_count`
    - `is_escalated`
    - `escalation_reason`
    - `escalated_at_attempt`
- `TaskEscalationPolicy`
  - `observe_attempt(...)`
  - `should_escalate(...)`
  - `resolve_model(...)`

Each task receives a fresh `TaskEscalationState`. Escalation state is not shared across tasks.

## Detection Heuristics (V1)

- Repeat signal:
  - Same normalized tool/action signature recurring across attempts.
- No-progress signal:
  - Attempt ends without accepted changes and task remains incomplete/failing.

Escalate only when both thresholds are crossed.

## Configuration

Add env vars:

- `ESCALATION_ENABLED=true|false`
- `ESCALATION_AGENTS=developer,reviewer`
- `ESCALATION_REPEAT_THRESHOLD=3`
- `ESCALATION_NO_PROGRESS_THRESHOLD=2`
- `ESCALATION_MODEL_OLLAMA=<model>`
- `ESCALATION_MODEL_GOOGLE=<model>`

Behavior if model config is missing:
- Do not escalate.
- Emit clear structured log indicating escalation was eligible but disabled due to missing model configuration.

## Control Flow Integration

Within the existing task retry loop:

1. Initialize `TaskEscalationState` at task start.
2. Before each attempt, call `resolve_model(...)` to choose default or escalated model.
3. Execute agent attempt.
4. On failure, call `observe_attempt(...)` and evaluate `should_escalate(...)`.
5. If escalation triggers and configured model exists:
   - set `is_escalated = true`
   - continue retries for this task using escalated model.
6. Task end resets escalation context for next task.

## Failure Modes

- Missing escalation model config:
  - Continue with default model and log explicit diagnostic.
- Escalated model provider error:
  - Count as normal failed attempt; existing retry/circuit-breaker logic remains authoritative.
- Non-scoped agent:
  - Never eligible for escalation in V1.

## Observability

Per attempt structured fields:

- `task_id`
- `agent`
- `attempt`
- `model_used`
- `repeat_count`
- `no_progress_count`
- `is_escalated`

Escalation event fields:

- `escalation_triggered=true`
- `trigger_reason=combined_signal`
- thresholds and current counters
- selected escalation model
- timestamp

Task summary fields:

- `task_escalated`
- `first_escalated_attempt`
- `task_outcome`

## Test Plan

Unit tests:

1. No escalation when only repeat threshold is met.
2. No escalation when only no-progress threshold is met.
3. Escalation when both thresholds are met.
4. Once escalated, model stays escalated for the task.
5. Non-scoped agents do not escalate.
6. Missing model config logs and does not escalate.

Integration tests (mocked orchestration loop):

1. Developer task escalates after combined trigger and switches model.
2. Reviewer task escalates after combined trigger and switches model.
3. Existing retry/circuit-breaker behavior remains unchanged.

## Deferred Architecture Note

Separate from this feature, there is a known efficiency issue: developer/reviewer context is reset per task attempt, forcing repeated rediscovery of workspace state. This should be addressed later as a dedicated persistent-context design effort.

## Implementation Checklist

1. Add escalation config parsing and defaults.
2. Implement `TaskEscalationPolicy` and state object.
3. Wire policy into developer/reviewer retry execution path.
4. Add structured logs and task summary fields.
5. Add unit tests for policy rules.
6. Add integration tests for orchestration behavior.
7. Update `.env.example` and README configuration docs.
