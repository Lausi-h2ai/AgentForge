"""Run three live-model cases and verify generated code against external checks."""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES = ("slugify", "statistics", "inventory")
CONFIG_KEYS = (
    "PROMPT_DEVELOPER_VERSION",
    "PROMPT_REVIEWER_VERSION",
    "PROMPT_PLANNER_VERSION",
    "PROMPT_REQUIREMENTS_ANALYST_VERSION",
    "PROMPT_SOFTWARE_ARCHITECT_VERSION",
    "ESCALATION_ENABLED",
    "LLM_ESCALATION_MODEL",
    "PLANNER_ESCALATION_ENABLED",
    "REVIEW_TIMEOUT_SIMPLE",
    "REVIEW_TIMEOUT_MEDIUM",
    "REVIEW_TIMEOUT_COMPLEX",
    "HIPPOCAMP_AI_ENABLED",
    "EMBEDDING_PROVIDER",
    "EMBEDDING_MODEL",
    "LLM_CONTEXT_WINDOW",
    "LLM_MAX_TOKENS",
    "LLM_REQUEST_TIMEOUT",
)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def summarize(state, checkpoints, exit_code, acceptance_passed, timed_out=False):
    """CLI exit zero alone is insufficient: the runtime can finish incomplete."""
    planned = len(state.get("plan", []))
    completed = sum(
        checkpoints.get(str(i), {}).get("status") == "completed" for i in range(planned)
    )
    all_complete = planned > 0 and completed == planned
    return {
        "planned_tasks": planned,
        "completed_tasks": completed,
        "task_completion_rate": completed / planned if planned else None,
        "retries": sum(cp.get("retry_count", 0) for cp in checkpoints.values()),
        "passed": exit_code == 0 and not timed_out and all_complete and acceptance_passed,
        "comparative_costs": state.get("cost_tracker_state", {}).get("total_costs_by_model", {}),
        # The existing tracker contains comparative estimates, not verified provider billing.
        "actual_api_cost_usd": None,
    }


def run_case(case, args, run_id, output_dir):
    project = f"eval_{run_id}_{case}"
    project_dir = ROOT / "projects" / project
    command = [
        sys.executable,
        str(ROOT / "orchestrator.py"),
        project,
        "--prompt",
        str(getattr(args, "prompt", None) or ROOT / "examples" / "evaluation" / f"{case}.txt"),
        "--new",
        "--planning-model",
        args.model,
        "--execution-model",
        args.model,
    ]
    command.extend(["--provider", args.provider])
    # Explicit model overrides avoid silently changing the model between runs.
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    start = time.perf_counter()
    timed_out = False
    with (output_dir / f"{case}-runtime.txt").open("w", encoding="utf-8") as log:
        try:
            result = subprocess.run(
                command,
                cwd=ROOT,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=args.timeout,
            )
            exit_code = result.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
            exit_code = None
    elapsed = time.perf_counter() - start
    state = read_json(project_dir / "state.json")
    checkpoints = read_json(project_dir / "checkpoints.json")
    acceptance = False
    acceptance_exit = None
    if not timed_out and exit_code == 0:
        with (output_dir / f"{case}-acceptance.txt").open("w", encoding="utf-8") as log:
            try:
                check = subprocess.run(
                    [
                        sys.executable,
                        str(ROOT / "scripts" / "portfolio_acceptance.py"),
                        case,
                        str(project_dir / "workspace"),
                    ],
                    cwd=project_dir / "workspace",
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=30,
                )
                acceptance_exit = check.returncode
                acceptance = check.returncode == 0
            except (subprocess.TimeoutExpired, OSError):
                acceptance = False
    return {
        "case": case,
        "project": project,
        "generation_seconds": round(elapsed, 3),
        "exit_code": exit_code,
        "timed_out": timed_out,
        "acceptance_passed": acceptance,
        "acceptance_exit_code": acceptance_exit,
        **summarize(state, checkpoints, exit_code, acceptance, timed_out),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=("openai", "ollama", "google"), required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--timeout", type=int, default=1200, help="Seconds per case")
    parser.add_argument("--case", choices=CASES, action="append", dest="cases")
    parser.add_argument("--prompt", type=Path, help="Override prompt for a single selected case")
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    if args.prompt and (not args.cases or len(args.cases) != 1 or not args.prompt.is_file()):
        parser.error("--prompt requires an existing file and exactly one --case")
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    output_dir = ROOT / "artifacts" / "evaluations" / run_id
    output_dir.mkdir(parents=True)
    # Match the runtime's dotenv precedence without recording secrets.
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
    except ImportError:
        pass
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()
    dirty = (
        subprocess.run(
            ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout
        != ""
    )
    report = {
        "mode": "live-model",
        "started_at_utc": run_id,
        "git_revision": revision,
        "working_tree_dirty": dirty,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "provider": args.provider,
        "planning_model": args.model,
        "execution_model": args.model,
        "timeout_seconds_per_case": args.timeout,
        "explicit_environment_overrides": {
            key: os.environ[key] for key in CONFIG_KEYS if key in os.environ
        },
        "cases": [],
        "prompt_override": args.prompt.as_posix() if args.prompt else None,
    }
    if args.provider == "openai":
        # Record only the credential-free endpoint, never API keys or custom request bodies.
        sys.path.insert(0, str(ROOT))
        from orchestrator_core.provider_config import api_base

        report["api_base"] = api_base("OPENAI_BASE_URL")
    for case in args.cases or CASES:
        print(f"Running {case} with {args.provider}/{args.model}...", flush=True)
        report["cases"].append(run_case(case, args, run_id, output_dir))
        report["case_pass_rate"] = sum(c["passed"] for c in report["cases"]) / len(report["cases"])
        (output_dir / "report.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
    with (output_dir / "dependencies.txt").open("w", encoding="utf-8") as dependencies:
        subprocess.run(
            [sys.executable, "-m", "pip", "freeze"], cwd=ROOT, stdout=dependencies, check=True
        )
    print(f"Report: {output_dir / 'report.json'}")
    return 0 if all(case["passed"] for case in report["cases"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
