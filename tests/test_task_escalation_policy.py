import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from orchestrator_core.pipeline.task_escalation import TaskEscalationPolicy


def _policy(**overrides):
    base = {
        "enabled": True,
        "repeat_threshold": 3,
        "no_progress_threshold": 2,
        "enabled_agents": {"developer", "reviewer"},
        "escalation_models": {"ollama": "strong-model"},
    }
    base.update(overrides)
    return TaskEscalationPolicy(**base)


def test_policy_requires_combined_signal_to_escalate():
    policy = _policy()
    state = policy.new_task_state()

    policy.observe_attempt(state, "DeveloperAgent", "write_file:a.py", progress_made=False)
    policy.observe_attempt(state, "DeveloperAgent", "write_file:a.py", progress_made=False)
    assert policy.should_escalate(state) is False

    policy.observe_attempt(state, "DeveloperAgent", "write_file:a.py", progress_made=False)
    assert policy.should_escalate(state) is True


def test_policy_does_not_escalate_when_only_one_signal_crosses_threshold():
    policy = _policy()
    state = policy.new_task_state()

    policy.observe_attempt(state, "DeveloperAgent", "sig-1", progress_made=False)
    policy.observe_attempt(state, "DeveloperAgent", "sig-2", progress_made=False)
    policy.observe_attempt(state, "DeveloperAgent", "sig-3", progress_made=False)
    assert policy.should_escalate(state) is False


def test_policy_marks_state_escalated_once_triggered():
    policy = _policy()
    state = policy.new_task_state()

    for _ in range(3):
        policy.observe_attempt(state, "DeveloperAgent", "same", progress_made=False)

    assert policy.try_escalate(state, provider="ollama") is True
    assert state.is_escalated is True
    assert policy.resolve_model(state, provider="ollama", default_model="base-model") == "strong-model"


def test_policy_ignores_non_scoped_agents():
    policy = _policy()
    state = policy.new_task_state()

    for _ in range(5):
        policy.observe_attempt(state, "PlannerAgent", "same", progress_made=False)

    assert policy.should_escalate(state) is False
    assert policy.try_escalate(state, provider="ollama") is False


def test_policy_missing_provider_model_does_not_escalate():
    policy = _policy(escalation_models={})
    state = policy.new_task_state()

    for _ in range(3):
        policy.observe_attempt(state, "CodeReviewerAgent", "same", progress_made=False)

    assert policy.should_escalate(state) is True
    assert policy.try_escalate(state, provider="ollama") is False
    assert state.is_escalated is False
