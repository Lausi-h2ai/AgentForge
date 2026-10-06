# Presenting AgentForge

## Suggested GitHub description

Multi-agent coding orchestrator with shared blackboard state, staged execution,
review-driven retries, checkpoint recovery, and model escalation.

## Interview walkthrough

1. Explain the architecture diagram: shared state and scheduling are distinct responsibilities.
2. Follow a task through development, blocking review, feedback injection, and retry.
3. Distinguish LlamaIndex's inner loop from the harness's outer control loop.
4. Show task-level checkpoint restoration and explain why it is not in-flight conversation resume.
5. Discuss correlated reviewer errors, best-effort recovery, and missing event-driven activation.
6. Show independent acceptance checks and distinguish offline verification from live results.

## Ownership and AI assistance

AI assistance was used for this portfolio documentation, demo, and evaluation update.
The repository alone cannot establish who originally authored every component.
Before using first-person claims in a CV, identify your own decisions and code changes
from project history. Describe what you designed, implemented, adapted from frameworks,
and validated with AI assistance. Credit upstream frameworks and tools.

Substantiate each ownership claim with a design decision, code, and a test or run.
For example, explain escalation thresholds, the no-progress signal, configuration,
and tests if you implemented that feature. Avoid presenting framework functionality
or scripted responses as original autonomous-agent capability.
