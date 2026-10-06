"""Review stage extraction from Orchestrator.run (behavior-preserving)."""
from __future__ import annotations

from dataclasses import dataclass

from .context import StageContext


@dataclass
class ReviewStageResult:
    """Result of review stage execution for a single task."""

    should_retry: bool
    issue_summary: str
    updated_task: str


async def execute_review_stage(ctx: StageContext) -> ReviewStageResult:
    """
    Execute the review sub-stage for one task.
    Mirrors existing behavior and side effects from Orchestrator.run.
    """
    orch = ctx.orchestrator
    task = ctx.task
    checkpoint = ctx.checkpoint
    savepoint = ctx.savepoint

    print(f"\n🔍 Reviewer checking code...")

    project_structure = orch._get_project_structure_string()
    git_diff = orch._get_project_diff()

    review_timeout = orch._get_review_timeout(git_diff, checkpoint.files_modified)
    if orch.reviewer_agent:
        orch.reviewer_agent.review_timeout = review_timeout
    if orch.logger:
        orch.logger.log("INFO", f"Reviewer timeout set to {review_timeout}s")

    reviewer_dev_conv = orch.reviewer_agent._get_or_create_conversation("DeveloperAgent")
    if checkpoint.retry_count == 0:
        reviewer_dev_conv.add_message(
            "user",
            f"First review of: {task[:100]}...\nFiles: {', '.join(checkpoint.files_modified[:5])}"
        )
    else:
        reviewer_dev_conv.add_message(
            "user",
            f"Re-review (attempt {checkpoint.retry_count + 1}). Developer should have fixed previous issues."
        )

    review_memory = orch._get_memory_context(task, agent_name="CodeReviewerAgent")
    review_tool_memory = orch._get_memory_context("tool usage rules", agent_name="CodeReviewerAgent")
    review_task = f"{task}\n\n{review_memory}{review_tool_memory}"
    requirements = getattr(orch, "user_prompt", "")
    if requirements:
        review_task = (
            "PROJECT REQUIREMENTS (check relevant constraints; files assigned to later tasks "
            "are not missing-feature issues for this review):\n" + requirements
            + "\n\nCURRENT TASK (review only this task):\n" + review_task
        )
    raw_issues, raw_review_history = await orch.reviewer_agent.review_code(
        review_task,
        project_structure,
        git_diff,
        checkpoint.review_feedback
    )
    issues = raw_issues or []
    review_history = raw_review_history or []

    if issues:
        issue_summary = f"Found {len(issues)} issues: " + "; ".join(
            [f"{i.get('severity')}: {i.get('description', '')[:40]}" for i in issues[:3]]
        )
        if len(issues) > 3:
            issue_summary += f" and {len(issues)-3} more..."
    else:
        issue_summary = "✅ No issues found - code looks good!"

    reviewer_dev_conv.add_message("assistant", issue_summary)

    dev_reviewer_conv = orch.dev_agent._get_or_create_conversation("CodeReviewerAgent")
    dev_reviewer_conv.add_message("assistant", issue_summary)

    if checkpoint.retry_count > 0:
        checkpoint.add_agent_interaction(
            "DeveloperAgent",
            "CodeReviewerAgent",
            f"Task attempt {checkpoint.retry_count + 1}",
            issue_summary
        )

    orch.cost_tracker.calculate_and_print_cost(orch.model_name)

    if orch._detect_reviewer_tool_errors(review_history):
        issues = issues or []
        issues.append({
            "severity": "critical",
            "type": "integration_issue",
            "file": "N/A",
            "line": 0,
            "description": "Reviewer tool calls failed; review is invalid.",
            "suggestion": "Fix tool call format and re-run review."
        })

    placeholder_issues = orch._find_placeholders_in_files(checkpoint.files_modified)
    if placeholder_issues:
        if issues:
            issues.extend(placeholder_issues)
        else:
            issues = placeholder_issues
    issues = orch._validate_review_findings(issues, checkpoint.files_modified)

    checkpoint.review_feedback = issues
    checkpoint.status = "reviewed"
    orch._save_checkpoint(checkpoint)

    if issues and len(issues) > 0:
        blocking_issues = [i for i in issues if i.get("severity") in ["critical", "major"]]
        non_blocking_issues = [i for i in issues if i.get("severity") not in ["critical", "major"]]

        if blocking_issues:
            print(f"❌ Review found {len(blocking_issues)} blocking issues:")
            for issue in blocking_issues:
                severity = issue.get('severity', 'unknown').upper()
                file = issue.get('file', 'unknown')
                line = issue.get('line', 0)
                desc = issue.get('description', 'No description')
                print(f"  - [{severity}] {file}:{line} - {desc}")

            if savepoint:
                print("⚠️ Rolling back changes...")
                orch._rollback_to_savepoint(savepoint)

            detailed_issue_summary = "🔍 REVIEW FEEDBACK - Issues to fix:\n\n"
            for idx, issue in enumerate(blocking_issues, 1):
                detailed_issue_summary += f"{idx}. [{issue.get('severity', 'unknown').upper()}] "
                detailed_issue_summary += f"{issue.get('file', 'unknown')}:{issue.get('line', 0)}\n"
                detailed_issue_summary += f"   Problem: {issue.get('description', 'No description')}\n"
                if issue.get('suggestion'):
                    detailed_issue_summary += f"   Fix: {issue.get('suggestion')}\n"
                detailed_issue_summary += "\n"

            try:
                dev_reviewer_conv = orch.dev_agent._get_or_create_conversation("CodeReviewerAgent")
                dev_reviewer_conv.add_message("assistant", detailed_issue_summary)
            except Exception as e:
                print(f"⚠️ Could not add review feedback to conversation: {e}")

            checkpoint.add_retry(
                "review_blocking_issues",
                f"{len(blocking_issues)} blocking issues found"
            )
            orch._remember_memory(
                content=f"Blocking review issues on task '{task}'. Issues: {detailed_issue_summary}",
                agent_name="CodeReviewerAgent",
                memory_type="event",
                tags=["retry", "review_blocking", f"project:{orch.project_name}"],
                importance=0.8,
                store_global=True
            )
            checkpoint.status = "pending"
            orch._save_checkpoint(checkpoint)

            print("\n🔄 Retrying task with reviewer feedback...")
            return ReviewStageResult(
                should_retry=True,
                issue_summary=detailed_issue_summary,
                updated_task=task,
            )

        if non_blocking_issues:
            print(f"⚠️ Review found {len(non_blocking_issues)} non-blocking issues:")
            for issue in non_blocking_issues:
                severity = issue.get('severity', 'unknown')
                file = issue.get('file', 'unknown')
                desc = issue.get('description', 'No description')
                print(f"  - [{severity}] {file} - {desc}")
            print("   (Proceeding as issues are non-blocking)")
    else:
        print("✅ Review passed - no issues found")

    updated_task = task
    if checkpoint.retry_count >= 3:
        recent_errors = [r['error_type'] for r in checkpoint.retry_history[-3:]]
        if len(set(recent_errors)) == 1:
            print(f"⚠️ STUCK: Same error 3x - {recent_errors[0]}")
            if checkpoint.review_feedback:
                issues_text = "\n".join([
                    f"FIX THIS: {i['file']}:{i['line']} - {i['description']}"
                    for i in checkpoint.review_feedback
                ])
                updated_task = f"""{task}

                    🔴 CRITICAL - PREVIOUS {checkpoint.retry_count} ATTEMPTS FAILED:

                    {issues_text}

                    YOU MUST FIX THESE EXACT ISSUES LISTED ABOVE.
                    Read the error messages carefully and fix each one.
                    """

    return ReviewStageResult(
        should_retry=False,
        issue_summary=issue_summary,
        updated_task=updated_task,
    )
