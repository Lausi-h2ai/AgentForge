# Quick Reference

## Install

```bash
pip install -e .[dev]
pip install -e .[ollama,memory,tester]
```

## Configure

```bash
cp .env.example .env
```

Key variables:

- `LLM_PROVIDER`
- `LLM_MODEL`
- `LLM_ESCALATION_MODEL`
- `REVIEW_TIMEOUT_SIMPLE`
- `REVIEW_TIMEOUT_MEDIUM`
- `REVIEW_TIMEOUT_COMPLEX`
- `ESCALATION_ENABLED`
- `PLANNER_ESCALATION_ENABLED`

## Run

```bash
python orchestrator.py demo_project --prompt examples/prompts/demo_prompt.txt --new
python orchestrator.py demo_project --prompt examples/prompts/demo_prompt.txt --new --with-tests
python orchestrator.py demo_project --prompt examples/prompts/demo_prompt.txt --new --google
```

## Test

```bash
pytest -q
```

## Explore the graph

```bash
npx -y -p rpg-encoder rpg-encoder info
npx -y -p rpg-encoder rpg-encoder search "planning stage"
```
