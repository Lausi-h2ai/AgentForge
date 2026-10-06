import os
import sys
import asyncio
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from orchestrator_core.pipeline.context import StageContext
from orchestrator_core.pipeline.development_stage import execute_development_stage
from orchestrator_core.pipeline.finalization_stage import execute_finalization_stage
from orchestrator_core.pipeline.testing_stage import execute_testing_stage


@dataclass
class _DummyDevResult:
    success: bool
    output: str = "ok"
    tool_calls: list = None

    def __post_init__(self):
        if self.tool_calls is None:
            self.tool_calls = []


@dataclass
class _DummyToolCall:
    tool_name: str
    tool_args: dict

    def to_legacy(self):
        return {"tool_name": self.tool_name, "tool_args": self.tool_args}


class _DummyConversation:
    def __init__(self):
        self.history = []

    def add_message(self, role, content):
        self.history.append((role, content))


class _DummyAgent:
    def __init__(self):
        self._conversations = {}

    def _get_or_create_conversation(self, name):
        if name not in self._conversations:
            self._conversations[name] = _DummyConversation()
        return self._conversations[name]

    def clear_conversation(self, name):
        self._conversations.pop(name, None)

    def get_stats(self):
        return {"call_count": 0, "error_count": 0, "error_rate": 0.0, "active_conversations": len(self._conversations)}


class _DummyLogger:
    def __init__(self):
        self.events = []

    def log(self, level, msg):
        self.events.append((level, msg))

    def log_phase(self, phase):
        self.events.append(("PHASE", phase))

    def log_final_summary(self, cost, metrics):
        self.events.append(("SUMMARY", (cost, metrics)))

    def write_to_file(self):
        self.events.append(("WRITE", "ok"))


class _DummyTester:
    def __init__(self, ok=True):
        self.ok = ok

    def run_quality_gate(self, architecture, logger):
        return self.ok, "tests-output"


class _DummyDocAgent:
    def write_documentation(self, project_name, project_structure, run_command, requirements_txt, logger):
        return f"# {project_name}\n\nRun: `{run_command}`"


class _DummyTracker:
    def calculate_and_print_cost(self, model):
        return None

    def get_summary(self):
        return "summary"


class _DummyCheckpoint:
    def __init__(self):
        self.retry_count = 0
        self.files_modified = []
        self.status = "pending"
        self.development_output = None
        self.test_results = None
        self.review_feedback = []

    def add_retry(self, error_type, msg):
        self.retry_count += 1


class _DummyOrch:
    def __init__(self, tmpdir):
        self.project_name = "p"
        self.project_dir = str(tmpdir)
        self.enable_file_verification = False
        self.model_name = "m"
        self.logger = _DummyLogger()
        self.dev_agent = _DummyAgent()
        self.reviewer_agent = _DummyAgent()
        self.architect_agent = _DummyAgent()
        self.requirements_agent = _DummyAgent()
        self.tester_agent = None
        self.run_tests_enabled = False
        self.technical_architecture = {}
        self.doc_agent = _DummyDocAgent()
        self.run_command = "python app.py"
        self.user_prompt = "u"
        self.files = {}
        self.task_checkpoints = {}
        self.plan = ["t1"]
        self.cost_tracker = _DummyTracker()
        self.metrics_tracker = _DummyTracker()
        self.saved = 0
        self.remembered = 0

    def _get_rag_context(self, task):
        return ""

    def _build_retry_context_from_conversations(self, checkpoint, task):
        return ""

    def _get_memory_context(self, query, agent_name=None):
        return ""

    async def _run_developer_agent(self, enhanced_task):
        return _DummyDevResult(success=True, output="done", tool_calls=[_DummyToolCall("write_file", {"filename": "a.py"})])

    def extract_filenames_from_task(self, task):
        return []

    def _save_checkpoint(self, checkpoint):
        self.saved += 1

    def _remember_memory(self, **kwargs):
        self.remembered += 1

    def _get_available_files(self):
        return None

    def _rollback_to_savepoint(self, savepoint):
        return True

    def _get_project_structure_string(self):
        return "files"

def _mk_tmp_dir(name: str) -> Path:
    base = ROOT / ".test_tmp"
    base.mkdir(exist_ok=True)
    d = base / name
    d.mkdir(exist_ok=True)
    return d


def test_development_stage_success():
    tmp_path = _mk_tmp_dir("dev")
    orch = _DummyOrch(tmp_path)
    cp = _DummyCheckpoint()
    ctx = StageContext(orch, task="make a.py", checkpoint=cp, current_task_index=0, savepoint=None)
    result = asyncio.run(execute_development_stage(ctx))
    assert result.should_retry is False
    assert result.success is True
    assert cp.status == "developed"
    assert "a.py" in cp.files_modified


def test_development_preserves_requirements_when_plan_details_drift():
    orch = _DummyOrch(_mk_tmp_dir("dev_requirements"))
    orch.user_prompt = "Retain ASCII letters and digits; replace underscores with hyphens."
    captured = []

    async def run_developer(task):
        captured.append(task)
        return _DummyDevResult(success=True, tool_calls=[_DummyToolCall(
            "write_file", {"filename": "slugify.py"}
        )])

    orch._run_developer_agent = run_developer
    asyncio.run(execute_development_stage(StageContext(
        orch, task="Implement a Unicode slugifier", checkpoint=_DummyCheckpoint(),
        current_task_index=0
    )))
    assert orch.user_prompt in captured[0]
    assert "take precedence" in captured[0]
    from agents.prompt_router import detect_task_type

    wrapped = (
        "PROJECT REQUIREMENTS: Write tests and fix errors.\n"
        "CURRENT TASK (implement only this task now):\nCreate slugify.py"
    )
    assert detect_task_type(wrapped) == "create_file"


def test_testing_stage_retry_on_failure():
    tmp_path = _mk_tmp_dir("test")
    orch = _DummyOrch(tmp_path)
    orch.tester_agent = _DummyTester(ok=False)
    orch.run_tests_enabled = True
    cp = _DummyCheckpoint()
    ctx = StageContext(orch, task="t", checkpoint=cp, current_task_index=0, savepoint="s")
    result = execute_testing_stage(ctx)
    assert result.should_retry is True
    assert cp.status == "pending"
    assert cp.retry_count == 1


def test_finalization_writes_readme_on_success():
    tmp_path = _mk_tmp_dir("final")
    orch = _DummyOrch(tmp_path)
    execute_finalization_stage(StageContext(orch), project_completed_successfully=True, clarified_prompt="req")
    readme = tmp_path / "README.md"
    assert readme.exists()
    assert "p" in readme.read_text(encoding="utf-8")
