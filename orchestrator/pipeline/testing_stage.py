"""Testing stage extraction from Orchestrator.run (behavior-preserving)."""
from __future__ import annotations

from dataclasses import dataclass

from .context import StageContext


@dataclass
class TestingStageResult:
    """Result of testing stage execution for a single task."""

    should_retry: bool


def execute_testing_stage(ctx: StageContext) -> TestingStageResult:
    """
    Execute testing sub-stage for one task.
    Mirrors existing behavior and side effects from Orchestrator.run.
    """
    orch = ctx.orchestrator
    task = ctx.task
    checkpoint = ctx.checkpoint
    savepoint = ctx.savepoint

    if not orch.tester_agent or not orch.run_tests_enabled:
        return TestingStageResult(should_retry=False)

    print(f"\n🧪 Running tests...")

    try:
        test_success, test_output = orch.tester_agent.run_quality_gate(
            orch.technical_architecture,
            orch.logger
        )
        orch.cost_tracker.calculate_and_print_cost(orch.model_name)

        checkpoint.test_results = test_output

        if not test_success:
            print(f"❌ Tests failed:")
            print(test_output)

            if savepoint:
                print("⚠️ Rolling back changes...")
                orch._rollback_to_savepoint(savepoint)

            checkpoint.add_retry("test_failure", test_output[:500])
            orch._remember_memory(
                content=f"Tests failed for task '{task}'. Output: {test_output[:400]}",
                agent_name="TesterAgent",
                memory_type="event",
                tags=["retry", "test_failure", f"project:{orch.project_name}"],
                importance=0.7,
                store_global=False
            )
            checkpoint.status = "pending"
            orch._save_checkpoint(checkpoint)
            return TestingStageResult(should_retry=True)

        checkpoint.status = "tested"
        orch._save_checkpoint(checkpoint)
        print("✅ Tests passed")
        return TestingStageResult(should_retry=False)

    except Exception as e:
        orch.logger.log("WARNING", f"Testing failed: {e}")
        print(f"⚠️ Testing encountered error: {e}, proceeding anyway...")
        return TestingStageResult(should_retry=False)

