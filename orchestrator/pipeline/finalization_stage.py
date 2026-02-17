"""Finalization stage extraction from Orchestrator.run (behavior-preserving)."""
from __future__ import annotations

import os

from .context import StageContext


def execute_finalization_stage(
    ctx: StageContext,
    project_completed_successfully: bool,
    clarified_prompt: str,
) -> None:
    """Execute finalization phase with documentation and summary output."""
    orch = ctx.orchestrator

    orch.logger.log_phase("Finalization")
    print("\n=== 🏁 Finalization ===")

    if project_completed_successfully:
        print("\n📚 Generating documentation...")
        try:
            project_structure = orch._get_project_structure_string()
            requirements_txt = clarified_prompt if clarified_prompt else orch.user_prompt

            readme_content = orch.doc_agent.write_documentation(
                orch.project_name,
                project_structure,
                orch.run_command,
                requirements_txt,
                orch.logger
            )

            readme_path = os.path.join(orch.project_dir, "README.md")
            with open(readme_path, 'w', encoding='utf-8') as f:
                f.write(readme_content)
            orch.files["README.md"] = readme_content

            print("✅ Documentation generated")

        except Exception as e:
            print(f"❌ Documentation generation failed: {e}")

    print("\n" + "=" * 60)
    print("PROJECT SUMMARY")
    print("=" * 60)
    print(f"Project: {orch.project_name}")
    completed_count = sum(
        1 for cp in orch.task_checkpoints.values()
        if cp.status == "completed"
    )
    print(f"Tasks completed: {completed_count}/{len(orch.plan)}")
    print(f"Status: {'✅ SUCCESS' if project_completed_successfully else '❌ INCOMPLETE'}")

    print(f"\n📊 AGENT STATISTICS:")
    agents = [
        ("Developer", orch.dev_agent),
        ("Code Reviewer", orch.reviewer_agent),
        ("Architect", orch.architect_agent),
        ("Requirements", orch.requirements_agent),
    ]

    for agent_name, agent in agents:
        if agent:
            stats = agent.get_stats()
            print(f"\n  {agent_name}:")
            print(f"    Total Calls: {stats['call_count']}")
            print(f"    Errors: {stats['error_count']} ({stats['error_rate']:.1%})")
            print(f"    Conversations: {stats['active_conversations']}")

    total_retries = sum(cp.retry_count for cp in orch.task_checkpoints.values())
    tasks_with_retries = sum(1 for cp in orch.task_checkpoints.values() if cp.retry_count > 0)
    if tasks_with_retries > 0:
        print(f"\n  Retry Statistics:")
        print(f"    Total Retries: {total_retries}")
        print(f"    Tasks with Retries: {tasks_with_retries}/{len(orch.task_checkpoints)}")
        print(f"    Average Retries: {total_retries/len(orch.task_checkpoints):.1f}")

    cost_summary = orch.cost_tracker.get_summary()
    print(f"\n{cost_summary}")

    metrics_summary = orch.metrics_tracker.get_summary()
    print(f"\n{metrics_summary}")

    orch.logger.log_final_summary(cost_summary, metrics_summary)
    orch.logger.write_to_file()

    print("=" * 60)

