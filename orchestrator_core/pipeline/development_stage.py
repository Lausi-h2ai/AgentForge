"""Development stage extraction from Orchestrator.run (behavior-preserving)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .context import StageContext


@dataclass
class DevelopmentStageResult:
    """Result of development stage execution for a single task."""

    should_retry: bool
    success: bool
    dev_output: Optional[str] = None
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)


async def execute_development_stage(ctx: StageContext) -> DevelopmentStageResult:
    """
    Execute the development sub-stage for one task.
    Mirrors existing behavior and side effects from Orchestrator.run.
    """
    orch = ctx.orchestrator
    task = ctx.task
    checkpoint = ctx.checkpoint
    current_task_index = ctx.current_task_index

    checkpoint.status = "in_progress"
    orch._save_checkpoint(checkpoint)

    print(f"\n🔧 Developer working on task...")

    rag_context = orch._get_rag_context(task)
    retry_context = orch._build_retry_context_from_conversations(checkpoint, task)

    if checkpoint.retry_count > 0:
        dev_reviewer_conv = orch.dev_agent._get_or_create_conversation("CodeReviewerAgent")
        if dev_reviewer_conv.history:
            print(f"💬 Loading conversation history: {len(dev_reviewer_conv.history)} messages")

    dev_memory = orch._get_memory_context(task, agent_name="DeveloperAgent")
    dev_tool_memory = orch._get_memory_context("tool usage rules", agent_name="DeveloperAgent")
    enhanced_task = f"{task}\n\n{rag_context}{retry_context}{dev_memory}{dev_tool_memory}"

    orchestrator_conv = orch.dev_agent._get_or_create_conversation("orchestrator")
    orchestrator_conv.add_message(
        "system",
        f"Starting task {current_task_index + 1}: {task[:100]}..."
    )

    dev_result = await orch._run_developer_agent(enhanced_task)
    success = dev_result.success
    dev_output = dev_result.output
    tool_calls = [tc.to_legacy() for tc in dev_result.tool_calls]

    orchestrator_conv.add_message(
        "assistant",
        f"Completed with {len(tool_calls)} tool calls. Files modified: {[tc.get('tool_args', {}).get('filename', '?') for tc in tool_calls if tc.get('tool_name') in ['write_file', 'replace_text']]}"
    )

    expected_files = orch.extract_filenames_from_task(task)
    if len(tool_calls) == 0:
        print("❌ DEVELOPMENT FAILED: No tool calls were executed.")
        checkpoint.add_retry("no_tool_calls", "Developer returned completion without using tools")
        orch._remember_memory(
            content=f"Developer used zero tools for task '{task}'. Force retry.",
            agent_name="DeveloperAgent",
            memory_type="event",
            tags=["retry", "no_tool_calls", f"project:{orch.project_name}"],
            importance=0.9,
            store_global=True
        )
        checkpoint.status = "pending"
        orch._save_checkpoint(checkpoint)
        return DevelopmentStageResult(
            should_retry=True,
            success=False,
            dev_output=dev_output,
            tool_calls=tool_calls,
        )

    if orch.enable_file_verification and expected_files:
        orch._get_available_files()
        missing = [f for f in expected_files if f not in orch.files]

        if missing:
            print(f"❌ VERIFICATION FAILED")
            print(f"❌ Task claims complete but these files missing: {missing}")

            dev_reviewer_conv = orch.dev_agent._get_or_create_conversation("CodeReviewerAgent")
            dev_reviewer_conv.add_message(
                "system",
                f"❌ File verification failed. Missing: {', '.join(missing)}"
            )

            checkpoint.add_retry("files_not_created", f"{len(missing)} files missing")
            orch._remember_memory(
                content=f"Retry needed: files not created for task '{task}'. Missing: {', '.join(missing)}",
                agent_name="DeveloperAgent",
                memory_type="event",
                tags=["retry", "files_not_created", f"project:{orch.project_name}"],
                importance=0.8,
                store_global=True
            )
            checkpoint.status = "pending"
            orch._save_checkpoint(checkpoint)
            return DevelopmentStageResult(
                should_retry=True,
                success=False,
                dev_output=dev_output,
                tool_calls=tool_calls,
            )

    orch.cost_tracker.calculate_and_print_cost(orch.model_name)
    if not success:
        raise Exception("Development failed")

    checkpoint.development_output = dev_output
    checkpoint.status = "developed"
    checkpoint.files_modified = [
        tc["tool_args"].get("filename", "")
        for tc in tool_calls
        if tc["tool_name"] in ["write_file", "replace_text", "insert_text"]
    ]
    orch._save_checkpoint(checkpoint)

    print("✅ Development complete")
    return DevelopmentStageResult(
        should_retry=False,
        success=True,
        dev_output=dev_output,
        tool_calls=tool_calls,
    )

