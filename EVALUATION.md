# AgentForge evaluation

Evidence is separated by what it establishes:

| Evidence | Establishes | Does not establish |
|---|---|---|
| Offline tests | Defined contracts, guards, stage behavior, persistence | Live model quality |
| Scripted demo | Real tools/stages, feedback transfer, checkpoint restoration | Autonomous reasoning, planning, rollback reliability |
| Live evaluation | Outcomes for a named model/configuration on external checks | Reliability across arbitrary projects |

## Current evidence

The [offline demo record](docs/evidence/offline-demo.json) shows a blocking review,
one retry, acceptance success, and restored completion/retry state. It explicitly
records `offline-scripted` mode and zero model calls.

Run `python -m pytest -q`. The suite includes the demo integration check and evaluator
tests rejecting false success from incomplete plans, process errors, timeouts, and
failed acceptance. See the [verification record](docs/evidence/verification.json).

The real adapter is checked against a local scripted HTTP server for sync/async chat,
fragmented SSE, developer/reviewer tools, and optional embeddings. This is protocol
verification, not a live model benchmark. Install `.[openai,dev]` to run this check;
base-only installations skip it.

**No live-model benchmark results are published yet.** The previous unqualified
end-to-end success claim has been removed until a measured run can support it.

## Reproducible live evaluation

Install a provider extra and configure it, then explicitly select your model:

```bash
python scripts/evaluate_portfolio.py --provider ollama --model YOUR_INSTALLED_MODEL
python scripts/evaluate_portfolio.py --provider openai --model YOUR_SERVED_MODEL
python scripts/evaluate_portfolio.py --provider google --model YOUR_CONFIGURED_MODEL
```

Use `--case slugify` for one case or `--timeout 1800` to change the default 1,200-second
generation timeout per case. Cases run sequentially in unique project directories;
both planning and execution model overrides are explicit.

| Case | Contract | External checks |
|---|---|---|
| Slugify | ASCII slug normalization | Punctuation, repeated separators, empty input, case, digits |
| Statistics | Count/min/max/arithmetic mean | Mixed values, negatives, singleton, empty input rejection |
| Inventory | Independent item quantities | Accumulation, removal, underflow, negative amounts, missing items |

Prompts live in [examples/evaluation/](examples/evaluation/). Acceptance checks in
[scripts/portfolio_acceptance.py](scripts/portfolio_acceptance.py) stay outside the
generated project. Correctness does not rely on model-written tests or review approval.
Generated modules run in a separate Python process with a 30-second acceptance timeout;
this is not an execution sandbox.

## Success definition and metrics

A case passes only if the generation process exits successfully, every planned task
has a completed checkpoint, and external checks pass. Missing state, empty plans,
skipped/failed tasks, and timeouts cannot count as success.

Reports record case pass rate, planned/completed tasks, task completion rate, retries,
generation wall time, process status, model/provider, Git revision, dirty-tree status,
Python/platform, and selected non-secret configuration overrides. Logs and resolved
dependencies accompany reports under ignored `artifacts/evaluations/<run>/`.

Tracker values are labeled comparative estimates: incomplete accounting, stale prices,
and attribution limitations can affect them. `actual_api_cost_usd` stays null until
independently verified. Local inference still has hardware/time costs.

Repeat the suite at least three times with identical configuration and publish all
outcomes before aggregating pass rates, retries, and time. Add multi-file dependency
cases and recovery fault injection before making broader capability claims.

## Known boundaries

Agent output varies with model quality. Reviewer validation independently checks only
some findings. Git stash recovery is best effort, and offline tests stub model
boundaries. The three cases cover small standard-library Python contracts.

## Publishing evidence

Review raw prompts, stdout, traces, and dependency metadata before sharing: they can
contain private content or local paths. Copy reviewed reports into `docs/evidence/`
with model, settings, revision, dates, and sample size. Keep runtime workspaces out
of the repository. Never label the scripted demo as live or replace unknown cost with zero.
