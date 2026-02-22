import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from orchestrator_core.pipeline.planning_stage import _create_plan_with_escalation


class _DummyLogger:
    def __init__(self):
        self.messages = []

    def log(self, level, msg):
        self.messages.append((level, msg))


class _DummyPlanner:
    def __init__(self, failures_before_success=0):
        self.calls = 0
        self.failures_before_success = failures_before_success

    def create_plan(self, prompt, architecture, logger):
        self.calls += 1
        if self.calls <= self.failures_before_success:
            raise RuntimeError("planner failed")
        return ["task-1"], "python app.py"


class _DummyOrch:
    def __init__(self, planner):
        self.sadt_sart_agent = planner
        self.planning_escalation_enabled = True
        self.planning_escalation_failure_threshold = 1
        self.planning_max_attempts = 2
        self.provider = "ollama"
        self.planning_escalation_models = {"ollama": "strong-planner"}
        self.logger = _DummyLogger()
        self.active_planning_model = "base-planner"
        self.switched_models = []

    def _ensure_planning_model(self, model_override=None):
        self.active_planning_model = model_override or self.active_planning_model
        self.switched_models.append(self.active_planning_model)


def test_create_plan_with_escalation_switches_model_after_threshold():
    orch = _DummyOrch(_DummyPlanner(failures_before_success=1))

    plan, run_cmd = _create_plan_with_escalation(orch, "prompt", {"x": 1})

    assert plan == ["task-1"]
    assert run_cmd == "python app.py"
    assert "strong-planner" in orch.switched_models


def test_create_plan_with_escalation_raises_after_max_attempts():
    orch = _DummyOrch(_DummyPlanner(failures_before_success=5))

    try:
        _create_plan_with_escalation(orch, "prompt", {"x": 1})
        assert False, "Expected planner to fail after max attempts"
    except RuntimeError:
        assert orch.sadt_sart_agent.calls == orch.planning_max_attempts
