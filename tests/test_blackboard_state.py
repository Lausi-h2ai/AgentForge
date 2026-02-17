import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
ORCH_DIR = ROOT / "orchestrator"
if str(ORCH_DIR) not in sys.path:
    sys.path.insert(0, str(ORCH_DIR))

from orchestrator import Orchestrator
from blackboard import BlackboardState


def test_orchestrator_properties_proxy_to_blackboard():
    orch = Orchestrator.__new__(Orchestrator)
    orch.blackboard = BlackboardState()

    orch.plan = ["a", "b"]
    orch.run_command = "python app.py"
    orch.last_completed_task_index = 3
    orch.files = {"x.py": "print(1)"}
    orch.task_checkpoints = {1: {"status": "done"}}

    assert orch.blackboard.plan == ["a", "b"]
    assert orch.blackboard.run_command == "python app.py"
    assert orch.blackboard.last_completed_task_index == 3
    assert orch.blackboard.files["x.py"] == "print(1)"
    assert 1 in orch.blackboard.task_checkpoints
