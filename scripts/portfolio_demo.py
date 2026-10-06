"""Offline demonstration of real pipeline stages with scripted agent responses."""

# ruff: noqa: E402 -- repository imports follow the direct-script path setup

from __future__ import annotations

import argparse
import asyncio
import contextlib
import io
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agents.base_agent import ConversationHistory
from aidev_orchestrator.metrics_tracker import MetricsTracker
from aidev_orchestrator.orchestrator import Orchestrator, TaskCheckpoint
from aidev_orchestrator.orchestrator_tools import OrchestratorTools
from aidev_orchestrator.structured_logger import StructuredLogger
from orchestrator_core.blackboard import BlackboardState
from orchestrator_core.contracts.execution import DeveloperRunResult
from orchestrator_core.pipeline import StageContext, execute_development_stage, execute_review_stage


class ScriptedAgent:
    """Fixture boundary: no model, API, or framework agent is invoked."""

    def __init__(self, orch):
        self.orch = orch
        self.conversations = {}

    def _get_or_create_conversation(self, name):
        return self.conversations.setdefault(name, ConversationHistory())

    async def review_code(self, task, structure, diff, previous_feedback):
        result = self.orch.tools.read_file("greeting.py")
        compile(result["content"], "greeting.py", "exec")
        issues = []
        if "name.strip()" not in result["content"]:
            issues.append(
                {
                    "severity": "major",
                    "type": "logic_error",
                    "file": "greeting.py",
                    "line": 2,
                    "description": "Greeting preserves unwanted whitespace.",
                    "suggestion": "Strip the name before formatting the greeting.",
                }
            )
        return issues, [{"tool_name": "read_file", "result": result}]


class NoModelCost:
    def calculate_and_print_cost(self, model):
        pass

    def to_dict(self):
        return {"mode": "scripted", "api_cost_usd": 0}


class DemoOrchestrator(Orchestrator):
    """Only model, embedding, and memory boundaries are replaced by fixtures."""

    def __init__(self, directory):
        self.blackboard = BlackboardState()
        self.project_name = "offline-demo"
        self.project_dir = str(directory / "workspace")
        Path(self.project_dir).mkdir()
        self.state_file = str(directory / "state.json")
        self.checkpoint_file = str(directory / "checkpoints.json")
        self.logger = StructuredLogger(str(directory / "logs"))
        self.cost_tracker = NoModelCost()
        self.metrics_tracker = MetricsTracker()
        self.model_name = "scripted-fixture"
        self.repo = None
        self.memory = None
        self.enable_file_verification = True
        self.dev_agent = ScriptedAgent(self)
        self.reviewer_agent = ScriptedAgent(self)
        self.tools = OrchestratorTools(self)
        self.plan = ["Create greeting.py with greet(name), stripping surrounding whitespace."]

    def _get_rag_context(self, task):
        return ""

    def _get_memory_context(self, query, agent_name=None):
        return ""

    async def _run_developer_agent(self, task):
        retry = self.task_checkpoints[0].retry_count > 0
        if retry and "Greeting preserves unwanted whitespace" not in task:
            raise RuntimeError("Review feedback did not reach the retry prompt")
        if retry:
            tool_name = "replace_text"
            args = {"filename": "greeting.py", "old_text": "{name}", "new_text": "{name.strip()}"}
        else:
            tool_name = "write_file"
            args = {
                "filename": "greeting.py",
                "content": 'def greet(name):\n    return f"Hello, {name}!"\n',
            }
        result = getattr(self.tools, tool_name)(**args)
        if not result["success"]:
            raise RuntimeError(result)
        return DeveloperRunResult.from_legacy(
            True, "Scripted implementation", [{"tool_name": tool_name, "tool_args": args}]
        )


async def demonstrate(directory):
    orch = DemoOrchestrator(directory)
    checkpoint = TaskCheckpoint(0, orch.plan[0], "pending", datetime.now(timezone.utc).isoformat())
    orch.task_checkpoints[0] = checkpoint
    events = []
    for attempt in (1, 2):
        ctx = StageContext(orch, task=orch.plan[0], checkpoint=checkpoint, current_task_index=0)
        development = await execute_development_stage(ctx)
        if not development.success or development.should_retry:
            raise RuntimeError("Scripted development failed")
        tool_name = development.tool_calls[0]["tool_name"]
        events.append(
            f"Attempt {attempt}: real {tool_name} tool updates greeting.py; checkpoint developed"
        )
        review = await execute_review_stage(ctx)
        if attempt == 1:
            if not review.should_retry or checkpoint.retry_count != 1:
                raise RuntimeError("Expected blocking review to request one retry")
            events.append("Review blocks: whitespace bug; checkpoint pending; feedback retained")
        else:
            if review.should_retry:
                raise RuntimeError("Corrected implementation failed review")
            events.append(
                "Retry prompt contains reviewer feedback; corrected implementation passes review"
            )
    # Execute only the known scripted fixture, never arbitrary generated model output.
    namespace = {}
    exec(
        compile(Path(orch.project_dir, "greeting.py").read_text(), "greeting.py", "exec"), namespace
    )
    if namespace["greet"](" Ada ") != "Hello, Ada!":
        raise RuntimeError("Acceptance check failed")
    checkpoint.status = "completed"
    orch.last_completed_task_index = 0
    orch._save_checkpoint(checkpoint)
    orch._save_state(0)
    # A fresh object exercises the actual state/checkpoint deserialization methods.
    restored = Orchestrator.__new__(Orchestrator)
    restored.blackboard = BlackboardState()
    restored.state_file = orch.state_file
    restored.checkpoint_file = orch.checkpoint_file
    restored.logger = orch.logger
    restored._load_state()
    restored._load_checkpoints()
    if (
        restored.last_completed_task_index != 0
        or restored.task_checkpoints[0].status != "completed"
    ):
        raise RuntimeError("Checkpoint restoration failed")
    events.append("Acceptance: greet(' Ada ') == 'Hello, Ada!'")
    events.append("Fresh orchestrator restores completed task and retry history from disk")
    return {
        "mode": "offline-scripted",
        "live_model_calls": 0,
        "scope": (
            "Real tools, development/review stages, feedback, " "checkpoint and state restoration"
        ),
        "excluded": [
            "LLM quality",
            "planning",
            "Git rollback",
            "embedding retrieval",
            "persistent memory",
        ],
        "events": events,
        "attempts": 2,
        "retries": checkpoint.retry_count,
        "status": checkpoint.status,
        "acceptance_passed": True,
        "restored_retry_count": restored.task_checkpoints[0].retry_count,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "docs" / "evidence" / "offline-demo.json"
    )
    args = parser.parse_args()
    # Raw stage output can include temporary paths; only the curated event record is exported.
    with tempfile.TemporaryDirectory(prefix="agentforge-demo-") as directory:
        with contextlib.redirect_stdout(io.StringIO()):
            report = asyncio.run(demonstrate(Path(directory)))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("AgentForge | OFFLINE SCRIPTED DEMO | No model calls")
    for event in report["events"]:
        print(event)
    print(f"Evidence written: {args.output}")


if __name__ == "__main__":
    main()
