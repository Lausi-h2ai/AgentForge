import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.sadt_sart_planner_agent import SADTSARTPlannerAgent


class _DummyLogger:
    def __init__(self):
        self.messages = []

    def log(self, level, message):
        self.messages.append((level, message))


def _mk_planner():
    planner = SADTSARTPlannerAgent.__new__(SADTSARTPlannerAgent)
    return planner


def test_generate_workplan_uses_correction_pass_before_full_regen():
    planner = _mk_planner()
    logger = _DummyLogger()
    prompts = []

    bad_plan = {
        "project_title": "P",
        "context": "C",
        "tasks": [{"id": "T1", "title": "placeholder", "description": "create placeholder file"}],
    }
    fixed_plan = {
        "project_title": "P",
        "context": "C",
        "tasks": [{"id": "T1", "title": "real implementation", "description": "create real file with complete logic"}],
    }

    outputs = [json.dumps(bad_plan), json.dumps(fixed_plan)]

    planner._detect_project_complexity = lambda _ctx: "simple"

    def _fake_call_llm(system_message, prompt, _logger):
        prompts.append(prompt)
        return outputs.pop(0)

    planner._call_llm = _fake_call_llm

    plan = planner.generate_workplan("proj", "basic context", logger=logger)

    assert plan is not None
    assert len(prompts) == 2
    assert "EXISTING PLAN (JSON)" in prompts[1]


def test_generate_workplan_falls_back_to_regen_when_correction_fails():
    planner = _mk_planner()
    logger = _DummyLogger()
    prompts = []

    bad_plan = {
        "project_title": "P",
        "context": "C",
        "tasks": [{"id": "T1", "title": "placeholder", "description": "create placeholder file"}],
    }
    still_bad = {
        "project_title": "P",
        "context": "C",
        "tasks": [{"id": "T1", "title": "placeholder", "description": "placeholder"}],
    }
    final_good = {
        "project_title": "P",
        "context": "C",
        "tasks": [{"id": "T1", "title": "good", "description": "real implementation details"}],
    }

    outputs = [json.dumps(bad_plan), json.dumps(still_bad), json.dumps(final_good)]

    planner._detect_project_complexity = lambda _ctx: "simple"

    def _fake_call_llm(system_message, prompt, _logger):
        prompts.append(prompt)
        return outputs.pop(0)

    planner._call_llm = _fake_call_llm

    plan = planner.generate_workplan("proj", "basic context", logger=logger)

    assert plan is not None
    assert len(prompts) >= 3
    assert "EXISTING PLAN (JSON)" in prompts[1]


def test_required_topics_ignore_technical_architecture_noise():
    planner = _mk_planner()

    plan = {
        "project_title": "Hello",
        "context": "Hello context",
        "tasks": [
            {
                "id": "T1",
                "title": "Create hello world script",
                "description": "Add hello_world.py and tests/test_hello_world.py with pytest test",
            }
        ],
    }

    project_context = """Functional Requirements:

Implement a Hello World solution compatible with Python 3.14.
In-Scope:
- Create hello_world.py
- Create tests/test_hello_world.py

Technical Architecture:

{"legacy_note": "old pantry migration mention kept for audit"}
"""

    missing = planner._check_required_topics(plan, project_context)

    assert "Pantry CRUD" not in missing
