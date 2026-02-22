"""Planning-phase extraction from Orchestrator.run (behavior-preserving)."""
from __future__ import annotations

import json
import os

from .context import StageContext


def _create_plan_with_escalation(orch, planning_prompt_with_memory: str, architecture: dict):
    """
    Run SADT planning with optional model escalation after repeated failures.
    Returns (plan, run_command_from_plan).
    Raises the last planner exception if all attempts fail.
    """
    max_attempts = max(1, int(getattr(orch, "planning_max_attempts", 1)))
    escalation_enabled = bool(getattr(orch, "planning_escalation_enabled", False))
    threshold = max(1, int(getattr(orch, "planning_escalation_failure_threshold", 1)))
    provider = str(getattr(orch, "provider", "")).strip().lower()
    escalation_models = getattr(orch, "planning_escalation_models", {}) or {}
    escalation_model = escalation_models.get(provider)

    failures = 0
    last_error = None
    for attempt in range(1, max_attempts + 1):
        try:
            return orch.sadt_sart_agent.create_plan(
                planning_prompt_with_memory,
                architecture,
                orch.logger
            )
        except Exception as e:
            last_error = e
            failures += 1
            if orch.logger:
                orch.logger.log("WARNING", f"Planner attempt {attempt}/{max_attempts} failed: {e}")

            should_escalate = (
                escalation_enabled
                and failures >= threshold
                and escalation_model
            )
            if should_escalate:
                orch._ensure_planning_model(escalation_model)
                if orch.logger:
                    orch.logger.log(
                        "WARNING",
                        f"Planner escalation triggered after {failures} failures -> model {escalation_model}",
                    )
            elif escalation_enabled and failures >= threshold and not escalation_model and orch.logger:
                orch.logger.log(
                    "WARNING",
                    f"Planner escalation eligible but no model configured for provider '{provider}'",
                )

            if attempt >= max_attempts:
                raise

    if last_error:
        raise last_error
    raise RuntimeError("Planner failed unexpectedly")


def execute_planning_stage(ctx: StageContext) -> str:
    """
    Execute requirements + architecture + planning phases.
    Returns clarified prompt used for downstream finalization behavior.
    """
    orch = ctx.orchestrator

    if orch.is_resuming and orch._has_valid_saved_state():
        print("\nResuming from saved state. Skipping requirements, architecture, and planning.")
        clarified_prompt = orch.user_prompt
        return clarified_prompt

    if orch.is_resuming:
        print("\nSaved state incomplete or invalid. Re-running requirements, architecture, and planning.")

    # --- Phase 1: Requirements Analysis ---
    orch.logger.log_phase("Requirements Analysis")
    print("\n=== Phase 1: Requirements Analysis ===")

    req_memory = orch._get_memory_context(
        orch.user_prompt,
        agent_name="RequirementsAnalystAgent"
    )
    requirements_output = orch.requirements_agent.analyze_requirements(
        orch.user_prompt, req_memory
    )
    orch.cost_tracker.calculate_and_print_cost(orch.model_name)

    clarified_prompt = requirements_output.get("refined_prompt", orch.user_prompt)
    if not isinstance(clarified_prompt, str):
        try:
            clarified_prompt = json.dumps(clarified_prompt, ensure_ascii=False, indent=2)
        except Exception:
            clarified_prompt = str(clarified_prompt)

    questions = requirements_output.get("questions", [])
    if questions:
        print(f"\nRequirements analyst has {len(questions)} clarifying questions:")
        for i, q in enumerate(questions, 1):
            print(f"  {i}. {q}")
        clarification_notes = orch._collect_clarifications(questions)
        if clarification_notes:
            clarified_prompt = f"{clarified_prompt}\n\nCLARIFICATIONS:\n{clarification_notes}"

    os.makedirs(orch.project_path, exist_ok=True)
    with open(orch.requirements_file, 'w', encoding='utf-8') as f:
        f.write(clarified_prompt)

    print(f"Requirements analyzed and saved {clarified_prompt}")
    orch._remember_memory(
        content=orch._truncate_text(clarified_prompt, 1800),
        agent_name="RequirementsAnalystAgent",
        memory_type="context",
        tags=["phase:requirements", f"project:{orch.project_name}"],
        importance=0.7,
    )

    planning_prompt = clarified_prompt
    if orch.user_prompt and orch.user_prompt not in clarified_prompt:
        planning_prompt = f"{clarified_prompt}\n\nFULL SPECIFICATION:\n{orch.user_prompt}"

    # --- Phase 2: Architecture Design ---
    orch.logger.log_phase("Architecture Design")
    print("\n=== Phase 2: Architecture Design ===")

    arch_memory = orch._get_memory_context(
        planning_prompt,
        agent_name="SoftwareArchitectAgent"
    )
    planning_prompt_with_memory = f"{planning_prompt}\n\n{arch_memory}"
    architecture = orch.architect_agent.design_architecture(
        planning_prompt_with_memory,
        orch.logger
    )
    orch.cost_tracker.calculate_and_print_cost(orch.model_name)

    if not architecture:
        raise ValueError("Architecture design failed")

    orch.technical_architecture = architecture
    orch.run_command = architecture.get("run_command", "")

    print("Architecture designed")
    print(f"   Stack: {architecture.get('technology_stack', 'Unknown')}")
    print(f"   Files: {len(architecture.get('file_structure', []))}")

    try:
        arch_summary = {
            "technology_stack": architecture.get("technology_stack"),
            "run_command": architecture.get("run_command"),
            "file_count": len(architecture.get("file_structure", [])),
        }
        orch._remember_memory(
            content=orch._truncate_text(json.dumps(arch_summary, ensure_ascii=False), 1200),
            agent_name="SoftwareArchitectAgent",
            memory_type="context",
            tags=["phase:architecture", f"project:{orch.project_name}"],
            importance=0.7,
        )
    except Exception:
        pass

    # --- Phase 3: Planning ---
    orch.logger.log_phase("Task Planning")
    print("\n=== Phase 3: Task Planning ===")

    plan_memory = orch._get_memory_context(
        planning_prompt,
        agent_name="SADTSARTPlannerAgent"
    )
    planning_prompt_with_memory = f"{planning_prompt}\n\n{plan_memory}"

    if orch.sadt_sart_agent:
        try:
            orch.plan, run_cmd_from_plan = _create_plan_with_escalation(
                orch,
                planning_prompt_with_memory,
                architecture,
            )
            orch.sadt_plan = list(orch.plan)
            orch.planner_source = "sadt"
            if run_cmd_from_plan:
                orch.run_command = run_cmd_from_plan
        except Exception as e:
            print(f"SADT planner failed: {e}, using simple planner")
            orch.plan = orch._create_simple_plan(architecture)
            orch.sadt_plan = None
            orch.planner_source = "simple"
    else:
        orch.plan = orch._create_simple_plan(architecture)
        orch.sadt_plan = None
        orch.planner_source = "simple"

    orch.cost_tracker.calculate_and_print_cost(orch.model_name)

    if not orch.plan:
        raise ValueError("Planning failed - no tasks generated")

    print(f"Plan created with {len(orch.plan)} tasks")
    return clarified_prompt
