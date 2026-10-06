from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.code_reviewer_agent import CodeReviewerAgent
from aidev_orchestrator.orchestrator_tools import OrchestratorTools


def _make_reviewer_stub():
    agent = CodeReviewerAgent.__new__(CodeReviewerAgent)
    agent.last_tool_calls = []
    agent.tool_call_counts = {}
    agent.used_tools = set()
    return agent


def test_submit_review_is_a_terminal_tool(monkeypatch):
    from types import SimpleNamespace
    from agents import code_reviewer_agent as module

    tool_specs = []

    class FakeTool:
        @staticmethod
        def from_defaults(**kwargs):
            tool_specs.append(kwargs)
            return kwargs

    monkeypatch.setattr(module.BaseAgent, "__init__",
                        lambda self, *_args, **_kwargs: setattr(self, "llm", object()))
    monkeypatch.setattr(module, "FunctionTool", FakeTool)
    monkeypatch.setattr(module, "ReActAgent", lambda **kwargs: SimpleNamespace(**kwargs))
    tools = SimpleNamespace(**{name: (lambda *args, **kwargs: {}) for name in (
        "read_file", "list_files", "get_code_summary", "directory_exists",
        "recall_memory", "submit_review",
    )})
    module.CodeReviewerAgent(None, {}, tools, None)
    assert next(spec for spec in tool_specs if spec["name"] == "submit_review")["return_direct"]


def test_reviewer_normalizes_read_file_args_wrapper():
    agent = _make_reviewer_stub()

    args, kwargs = agent._normalize_tool_invocation(
        "read_file",
        (),
        {"args": ["workspace/hello_world.py"], "kwargs": {}},
    )

    assert args == ()
    assert kwargs["filename"] == "workspace/hello_world.py"


def test_reviewer_normalizes_submit_review_summary_payload():
    agent = _make_reviewer_stub()

    args, kwargs = agent._normalize_tool_invocation(
        "submit_review",
        (),
        {"summary": "looks good"},
    )

    assert args == ()
    assert "report" in kwargs
    assert kwargs["report"]["issues"] == []


def _mk_tmp_dir(name: str) -> Path:
    base = ROOT / ".test_tmp"
    base.mkdir(exist_ok=True)
    d = base / name
    d.mkdir(exist_ok=True)
    return d


def test_validate_file_path_accepts_workspace_prefix():
    class _DummyOrch:
        def __init__(self, project_dir):
            self.project_dir = str(project_dir)

    tmp_path = _mk_tmp_dir("reviewer_resilience_validate")
    tools = OrchestratorTools(_DummyOrch(tmp_path))
    assert tools._validate_file_path("workspace/hello_world.py") == "hello_world.py"
    assert tools._validate_file_path("workspace\\hello_world.py") == "hello_world.py"


def test_validate_file_path_blocks_workspace_parent_traversal():
    class _DummyOrch:
        def __init__(self, project_dir):
            self.project_dir = str(project_dir)

    tmp_path = _mk_tmp_dir("reviewer_resilience_traversal")
    tools = OrchestratorTools(_DummyOrch(tmp_path))
    with pytest.raises(ValueError):
        tools._validate_file_path("workspace/../outside.py")

