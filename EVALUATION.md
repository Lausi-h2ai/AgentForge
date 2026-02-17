# Evaluation Notes

This repo is a multi-agent LLM orchestration system with planning, development, review, and test phases.

## What Works Well
- Phase-based model selection (planning vs execution) without dual VRAM load.
- Reliable review loop: timeouts, circuit breaker, and confidence scoring.
- Skills injection per task to reduce context bloat and improve quality.
- Planner produces hierarchical plans and atomic actions.
- Pipeline tests exist (smoke + integration + contract checks).

## Known Limits / Risks
- Agents depend on external model quality; outputs vary by model.
- Reviewer validation only filters syntax-error false positives (conservative).
- Some tests stub external libs rather than running full LLM stack.

## Suggested Next Evaluations
- Add an evaluation harness for multiple prompts and track pass/fail.
- Measure task completion rate across 3–5 projects.
- Add unit tests for reviewer confidence scoring + circuit breaker.

## Sample Run Outcomes
- `pytest -q` passes in this repo with mocked pipeline tests.
- Demo project runs end-to-end and generates code, review, and README.
