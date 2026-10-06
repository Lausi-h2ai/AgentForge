# AgentForge quick reference

## Offline demo

```bash
python scripts/portfolio_demo.py
```

See [DEMO.md](DEMO.md) for the scripted recording and live demo instructions.

## Live evaluation

```bash
python scripts/evaluate_portfolio.py --provider openai --model YOUR_SERVED_MODEL
```

See [EVALUATION.md](EVALUATION.md) for external checks, metrics, and evidence boundaries.

## Install

```bash
pip install -e .[dev]
pip install -e .[openai]
```

## Configure

```bash
cp .env.example .env
```

Key variables:

- `LLM_PROVIDER`
- `LLM_MODEL`
- `OPENAI_BASE_URL`
- `OPENAI_API_KEY`
- `EMBEDDING_PROVIDER`
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
