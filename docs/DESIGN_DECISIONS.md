# Design decisions and tradeoffs

These notes explain the current code and its consequences. They do not claim a
benchmark comparison with alternative architectures.

| Decision | Benefit | Cost / boundary |
|---|---|---|
| Shared blackboard | Inspectable plan, files, progress, and checkpoints | Mutable coupling; concurrent writers would need arbitration |
| Central stage scheduling | Predictable ordering and explicit retry points | Less dynamic than fact-triggered blackboard activation |
| Separate developer/reviewer | Different prompts and tool permissions; defined feedback flow | More model calls and potentially correlated mistakes |
| LlamaIndex ReAct loop | Reuses tool execution machinery | Framework/version coupling; inner loop is partly external |
| Atomic tasks and checkpoints | Smaller context and task-level resume | Depends on plan quality; no in-flight continuation |
| Read-only reviewer tools | Reviewer cannot rewrite code under review | Findings are not proof of correctness |
| Local artifact validation | Catches missing files, zero-tool runs, placeholders, some false positives | Covers specific failure modes rather than every semantic defect |
| Conditional model escalation | Stronger fallback after repeated no-progress failures | More latency/cost; thresholds are heuristics |
| Optional persistent memory | Prior failures/tool rules inform later work | Service dependency and relevance/noise risks |
| Git stash recovery | Uses existing version-control machinery | Best effort; clean-start tasks lack stash savepoints |

## Why central scheduling?

Coding tasks have dependencies and acceptance gates. An explicit controller makes
retry, complete, and skip decisions visible and testable without an LLM. Shared
state provides continuity between stages. This fits a small orchestration harness,
while leaving room for state-triggered activation later.

## What would justify a more dynamic blackboard?

Independent discovery of new work, competing agents contributing to artifacts, or
agent selection from unmet facts would justify activation conditions, bounded task
creation, artifact ownership, and conflict handling. More roles alone would not
implement those capabilities.

## Evidence before additional features

Measure artifact correctness, retry overhead, and recovery behavior first. The
external acceptance suite checks three small contracts; it is a baseline rather
than evidence of broad autonomous software-development ability.
