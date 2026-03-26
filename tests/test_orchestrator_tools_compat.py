import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aidev_orchestrator.orchestrator_tools import OrchestratorTools


class _DummyOrchestrator:
    def __init__(self, project_dir):
        self.project_dir = str(project_dir)
        self.repo = None
        self.logger = None
        self.memory = None
        self.project_name = "demo"


def _mk_tmp_dir(name: str) -> Path:
    base = ROOT / ".test_tmp"
    base.mkdir(exist_ok=True)
    d = base / name
    d.mkdir(exist_ok=True)
    return d


def test_add_code_block_accepts_properties_wrapper():
    tmp_path = _mk_tmp_dir("tool_compat")
    orch = _DummyOrchestrator(tmp_path)
    tools = OrchestratorTools(orch)

    result = tools.add_code_block(properties={"filepath": "models.py", "new_code": "x=1"})
    assert result["success"] is False
    assert "does not exist" in result["error"].lower()


class _DummyMemory:
    enabled = True

    def recall_combined(self, query, project_name, agent_name=None, top_k=5, max_chars=2000):
        return f"MEMORY CONTEXT:\n- q={query}\n- project={project_name}\n- agent={agent_name}\n"


def test_recall_memory_returns_context_when_enabled():
    tmp_path = _mk_tmp_dir("tool_memory_ok")
    orch = _DummyOrchestrator(tmp_path)
    orch.memory = _DummyMemory()
    tools = OrchestratorTools(orch)

    result = tools.recall_memory(query="pantry model decisions", agent_name="DeveloperAgent")

    assert result["success"] is True
    assert "memory_context" in result
    assert "pantry model decisions" in result["memory_context"]


def test_recall_memory_reports_unavailable_when_memory_disabled():
    tmp_path = _mk_tmp_dir("tool_memory_disabled")
    orch = _DummyOrchestrator(tmp_path)
    tools = OrchestratorTools(orch)

    result = tools.recall_memory(query="anything", agent_name="CodeReviewerAgent")

    assert result["success"] is False
    assert "unavailable" in result["error"].lower()

