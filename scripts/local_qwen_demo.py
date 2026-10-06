"""Run a real local-model AgentForge case and publish sanitized README evidence.

The GIF is a replay of measured events, not a screen recording. No agent responses
are scripted. Raw traces and downloaded weights stay in ignored directories.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import textwrap
import time
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
MODEL = "qwen3.5-9b-q4_k_m"
OUTPUT = ROOT / "docs/evidence/local-qwen-demo"


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def hardware_info():
    info = {"cpu": "unknown", "system_ram_gib": None, "gpu": "unknown", "gpu_vram_gib": None}
    if os.name == "nt":
        command = (
            "$cpu=Get-CimInstance Win32_Processor; "
            "$system=Get-CimInstance Win32_ComputerSystem; "
            "@{cpu=$cpu.Name; system_ram_gib=[math]::Round($system.TotalPhysicalMemory/1GB)}"
            " | ConvertTo-Json -Compress"
        )
        info.update(
            json.loads(
                subprocess.check_output(
                    ["powershell.exe", "-NoProfile", "-Command", command], text=True, timeout=30
                )
            )
        )
    try:
        gpu = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            text=True,
            timeout=10,
        ).splitlines()[0]
        name, memory = gpu.rsplit(",", 1)
        info.update(gpu=name.strip(), gpu_vram_gib=float(memory) / 1024)
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    return info


def tool_counts(value):
    counts = Counter()
    if isinstance(value, dict):
        if value.get("type") == "tool_call" and value.get("tool_name"):
            counts[value["tool_name"]] += 1
        for child in value.values():
            counts.update(tool_counts(child))
    elif isinstance(value, list):
        for child in value:
            counts.update(tool_counts(child))
    return counts


def restore_check(project, state, checkpoints):
    from aidev_orchestrator.orchestrator import Orchestrator
    from orchestrator_core.blackboard import BlackboardState

    restored = Orchestrator.__new__(Orchestrator)
    restored.blackboard = BlackboardState()
    restored.state_file = str(project / "state.json")
    restored.checkpoint_file = str(project / "checkpoints.json")

    class QuietLogger:
        def log(self, *_args):
            pass

    restored.logger = QuietLogger()
    with contextlib.redirect_stdout(io.StringIO()):
        restored._load_state()
        restored._load_checkpoints()
    return (
        restored.last_completed_task_index == state["last_completed_task_index"]
        and len(restored.task_checkpoints) == len(checkpoints)
        and all(
            restored.task_checkpoints[int(key)].status == cp["status"]
            and restored.task_checkpoints[int(key)].retry_count == cp.get("retry_count", 0)
            for key, cp in checkpoints.items()
        )
    )


def publish(evaluation_path):
    evaluation = read_json(evaluation_path)
    if evaluation["mode"] != "live-model" or evaluation["execution_model"] != MODEL:
        raise ValueError("Expected a live local Qwen evaluation")
    case = next(c for c in evaluation["cases"] if c["case"] == "slugify")
    project = ROOT / "projects" / case["project"]
    if not (project / "state.json").exists():
        print(f"Run did not reach development; inspect {evaluation_path.parent}")
        return 1
    state = read_json(project / "state.json")
    checkpoints = read_json(project / "checkpoints.json")
    runtime = (evaluation_path.parent / "slugify-runtime.txt").read_text(encoding="utf-8")
    trace_matches = re.findall(r"Execution trace will be saved to: (.+\.json)", runtime)
    repair_logs = [evaluation_path.parent / "validation-repair-runtime.txt"]
    repair_logs += sorted(evaluation_path.parent.glob("validation-repair-*-runtime.txt"))
    for repair_log in repair_logs:
        if not repair_log.exists():
            continue
        repair_runtime = repair_log.read_text(encoding="utf-8")
        runtime += "\n" + repair_runtime
        trace_matches += re.findall(r"Execution trace will be saved to: (.+\.json)", repair_runtime)
    if not trace_matches:
        raise ValueError("Evaluation did not capture an execution trace")
    trace = []
    for match in trace_matches:
        trace_path = (ROOT / match.strip()).resolve()
        if not trace_path.is_relative_to(ROOT / "logs"):
            raise ValueError("Trace must be inside the repository logs directory")
        trace.extend(read_json(trace_path))
    restored = restore_check(project, state, checkpoints)
    # Re-run external acceptance rather than relying only on a recorded boolean.
    acceptance = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/portfolio_acceptance.py"),
            "slugify",
            str(project / "workspace"),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    generated_tests = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=project / "workspace",
        capture_output=True,
        text=True,
        timeout=60,
    )
    passed = case["passed"] and acceptance.returncode == 0 and restored
    passed = passed and generated_tests.returncode == 0
    events = [
        {"timestamp": entry["timestamp"], "event": entry["name"]}
        for entry in trace
        if entry.get("type") == "phase"
    ]
    counts = tool_counts(trace)
    # The current runtime prints developer tool results outside nested trace steps.
    developer_counts = Counter(re.findall(r"\[Developer\][^\n]*?\b(\w+)\(\{", runtime))
    for key, cp in checkpoints.items():
        for retry in cp.get("retry_history", []):
            timestamp = datetime.fromisoformat(retry["timestamp"]).astimezone(timezone.utc)
            events.append(
                {
                    "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
                    "event": f"Task {int(key)+1} retry: {retry['error_type']}",
                }
            )
        events.append(
            {
                "timestamp": datetime.fromisoformat(cp["timestamp"])
                .astimezone(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
                "event": f"Checkpoint {int(key)+1}: {cp['status']}",
            }
        )
    events.sort(key=lambda event: event["timestamp"])
    report = {
        "mode": "live-model",
        "presentation": "Replay of captured events; not a screen recording",
        "model": MODEL,
        "model_source": "https://huggingface.co/unsloth/Qwen3.5-9B-GGUF",
        "model_file": "Qwen3.5-9B-Q4_K_M.gguf",
        "model_bytes": 5680522464,
        "model_sha256": "03b74727a860a56338e042c4420bb3f04b2fec5734175f4cb9fa853daf52b7e8",
        "llama_cpp_build": "b11438",
        "hardware": hardware_info(),
        "gpu_layers": 28,
        "inference_slots": 1,
        "context_tokens": int(evaluation["explicit_environment_overrides"]["LLM_CONTEXT_WINDOW"]),
        "started_at_utc": evaluation["started_at_utc"],
        "git_revision": evaluation["git_revision"],
        "working_tree_dirty": evaluation["working_tree_dirty"],
        "case": "slugify",
        "generation_seconds": case["generation_seconds"],
        "planned_tasks": case["planned_tasks"],
        "completed_tasks": case["completed_tasks"],
        "retries": case["retries"],
        "acceptance_passed": acceptance.returncode == 0,
        "checkpoint_restored": restored,
        "generated_tests_passed": generated_tests.returncode == 0,
        "generated_tests_summary": (
            generated_tests.stdout.strip().splitlines()[-1]
            if generated_tests.stdout.strip()
            else "No test output"
        ),
        "passed": passed,
        "recorded_tool_calls": dict(counts),
        "developer_tool_results_in_runtime": dict(developer_counts),
        "planner_source": state.get("planner_source"),
        "validation_repair": evaluation.get("validation_repair"),
        "unexpected_generated_files": sorted(
            path.name
            for path in (project / "workspace").iterdir()
            if path.is_file()
            and not path.name.startswith(".")
            and path.name not in {"slugify.py", "test_slugify.py", "README.md"}
        ),
        "events": events,
        "tasks": [
            {"index": int(k), "status": cp["status"], "retries": cp.get("retry_count", 0)}
            for k, cp in checkpoints.items()
        ],
        "scope": (
            "One local coding case with real requirements, architecture, planning, "
            "developer, reviewer and documentation agents"
        ),
        "limitations": (
            "One run is not a benchmark. Optional Docker testing, embeddings "
            "and persistent memory were disabled."
        ),
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    artifacts = []
    for path in sorted((project / "workspace").rglob("*")):
        if not path.is_file() or path.suffix not in {".py", ".md"}:
            continue
        relative = path.relative_to(project / "workspace")
        if any(part.startswith(".") for part in relative.parts):
            continue
        # Text snapshots preserve exact generated bytes without being collected
        # as repository tests (their imports belong to the generated workspace).
        target = OUTPUT / "generated" / relative.with_suffix(relative.suffix + ".txt")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())
        artifacts.append(
            {
                "file": f"generated/{relative.as_posix()}",
                "snapshot": target.relative_to(OUTPUT).as_posix(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    report["generated_artifacts"] = artifacts
    (OUTPUT / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    render(report)
    print(f"Published {OUTPUT / 'report.json'}; passed={passed}")
    return 0 if passed else 1


def render(report):
    from PIL import Image, ImageDraw, ImageFont

    def font(size):
        for candidate in ("C:/Windows/Fonts/consola.ttf", "DejaVuSansMono.ttf"):
            try:
                return ImageFont.truetype(candidate, size)
            except OSError:
                pass
        return ImageFont.load_default(size=size)

    lines = [f"{e['timestamp'][11:19]}  {e['event']}" for e in report["events"]]
    lines += [
        f"Checkpoints: {report['completed_tasks']}/{report['planned_tasks']} completed; "
        f"{report['retries']} " + ("retry" if report["retries"] == 1 else "retries"),
        "Independent acceptance: " + ("PASS" if report["acceptance_passed"] else "FAIL"),
        "Generated tests: "
        + ("PASS" if report["generated_tests_passed"] else "FAIL")
        + " | "
        + report["generated_tests_summary"],
        "Checkpoint restoration: " + ("PASS" if report["checkpoint_restored"] else "FAIL"),
    ]
    frames = []
    for index in range(1, len(lines) + 1):
        frame = Image.new("RGB", (1200, 720), "#0b1220")
        draw = ImageDraw.Draw(frame)
        draw.rounded_rectangle((28, 24, 1172, 696), radius=18, fill="#111c30", outline="#253754")
        draw.text((56, 46), "AgentForge / local coding run", font=font(32), fill="#f1f5f9")
        draw.text(
            (56, 100),
            "LIVE MODEL  |  Qwen3.5-9B Q4_K_M  |  llama.cpp CUDA",
            font=font(21),
            fill="#5eead4",
        )
        draw.text(
            (56, 142),
            "RTX 3070 8 GB  /  16K context  /  one request at a time",
            font=font(20),
            fill="#94a3b8",
        )
        draw.line((56, 188, 1144, 188), fill="#253754", width=2)
        y = 211
        for line in lines[:index][-10:]:
            for part in textwrap.wrap(line, width=85):
                draw.text(
                    (56, y),
                    part,
                    font=font(21),
                    fill="#5eead4" if line == lines[index - 1] else "#cbd5e1",
                )
                y += 32
        draw.text(
            (56, 585),
            f"{report['generation_seconds']:.1f}s measured end-to-end | slugify.py + tests",
            font=font(21),
            fill="#f1f5f9",
        )
        draw.text(
            (56, 630),
            "Captured-event replay. Real model + tools. One case, not a benchmark.",
            font=font(19),
            fill="#94a3b8",
        )
        frames.append(frame.convert("P", palette=Image.Palette.ADAPTIVE, colors=64))
    frames[0].save(
        OUTPUT / "demo.gif",
        save_all=True,
        append_images=frames[1:],
        duration=[1400] * (len(frames) - 1) + [5000],
        loop=0,
        disposal=2,
    )
    frames[-1].save(OUTPUT / "demo.png")


def repair_project(project_name, feedback_path):
    from dotenv import dotenv_values

    os.environ.update(
        {k: v for k, v in dotenv_values(ROOT / "examples/local-qwen.env").items() if v is not None}
    )
    from aidev_orchestrator.orchestrator import Orchestrator

    orch = Orchestrator(
        project_name, provider="openai", planning_model=MODEL, execution_model=MODEL
    )
    # Stack-trace paths are diagnostics, not files the developer must create.
    feedback = "\n".join(
        line for line in feedback_path.read_text(encoding="utf-8").splitlines() if ".py" not in line
    )[-2500:]
    task = (
        "Fix existing test_slugify.py using read_file and replace_text. Independent execution "
        "found a syntax or assertion failure. Preserve its test coverage and the correct "
        "slugify.py implementation. Respect the ASCII contract: non-ASCII characters are "
        "separators, not transliterated letters; "
        "slugify('h\u00e9llo w\u00f6rld') must be 'h-llo-w-rld'. "
        "Keep backslash escapes in Python string literals and write valid UTF-8 source. "
        "Do not run commands; the demo runner executes tests independently.\n\n"
        "EXTERNAL VALIDATION FEEDBACK:\n" + feedback
    )
    index = orch.last_completed_task_index + 1
    if index < len(orch.plan):
        orch.plan[index] = task
        if index in orch.task_checkpoints:
            cp = orch.task_checkpoints[index]
            cp.task_description = task
            orch._save_checkpoint(cp)
    else:
        orch.plan.append(task)
    orch._save_state(orch.last_completed_task_index)
    asyncio.run(orch.run())
    return 0 if all(cp.status == "completed" for cp in orch.task_checkpoints.values()) else 1


def validate_and_repair(evaluation_path, env):
    """Run a bounded corrective task; retain every validation attempt."""
    from evaluate_portfolio import summarize

    report = read_json(evaluation_path)
    case = report["cases"][0]
    previous = report.get("validation_repair", {})
    if not case["passed"] and not previous:
        return False
    project = ROOT / "projects" / case["project"]
    tests = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=project / "workspace",
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if tests.returncode == 0 and case["passed"]:
        return False
    print(
        "Independent tests failed; adding one corrective task with real agent feedback.", flush=True
    )
    first_pass = evaluation_path.parent / "first-pass-report.json"
    if not first_pass.exists():
        first_pass.write_bytes(evaluation_path.read_bytes())
    feedback_path = evaluation_path.parent / "validation-feedback.txt"
    feedback_path.write_text(tests.stdout + tests.stderr, encoding="utf-8")
    start = time.perf_counter()
    attempt = previous.get("attempts", 0) + 1
    with (evaluation_path.parent / f"validation-repair-{attempt}-runtime.txt").open(
        "w", encoding="utf-8"
    ) as log:
        repair = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--repair-project",
                case["project"],
                "--feedback-file",
                str(feedback_path),
            ],
            cwd=ROOT,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            timeout=600,
        )
    elapsed = time.perf_counter() - start
    acceptance = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/portfolio_acceptance.py"),
            "slugify",
            str(project / "workspace"),
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    case.update(
        summarize(
            read_json(project / "state.json"),
            read_json(project / "checkpoints.json"),
            repair.returncode,
            acceptance.returncode == 0,
        )
    )
    case["acceptance_passed"] = acceptance.returncode == 0
    case["generation_seconds"] = round(case["generation_seconds"] + elapsed, 3)
    report["case_pass_rate"] = float(case["passed"])
    history = previous.get("history", [])
    if previous and not history:
        history = [
            {
                "test_summary": previous["initial_test_summary"],
                "seconds": previous["seconds"],
                "exit_code": previous["exit_code"],
            }
        ]
    history.append(
        {
            "test_summary": tests.stdout.strip().splitlines()[-1],
            "seconds": round(elapsed, 3),
            "exit_code": repair.returncode,
        }
    )
    report["validation_repair"] = {
        "attempts": attempt,
        "trigger": "independent generated-test failure",
        "initial_test_summary": history[0]["test_summary"],
        "seconds": round(previous.get("seconds", 0) + elapsed, 3),
        "exit_code": repair.returncode,
        "history": history,
    }
    evaluation_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluation", type=Path, help="Publish an existing evaluation report")
    parser.add_argument("--repair-project", help=argparse.SUPPRESS)
    parser.add_argument("--feedback-file", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.repair_project:
        return repair_project(args.repair_project, args.feedback_file)
    if args.evaluation:
        return publish(args.evaluation.resolve())
    from dotenv import dotenv_values

    env = dict(os.environ)
    env.update(
        {k: v for k, v in dotenv_values(ROOT / "examples/local-qwen.env").items() if v is not None}
    )
    env.update(PYTHONIOENCODING="utf-8", PYTHONUTF8="1", PYTHONUNBUFFERED="1")
    with urllib.request.urlopen("http://127.0.0.1:8080/health", timeout=10) as response:
        if json.load(response).get("status") != "ok":
            raise RuntimeError("Start scripts/start_local_qwen.ps1 first")
    existing = set((ROOT / "artifacts/evaluations").glob("*/report.json"))
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/evaluate_portfolio.py"),
            "--provider",
            "openai",
            "--model",
            MODEL,
            "--case",
            "slugify",
            "--prompt",
            "examples/prompts/local_qwen_demo.txt",
            "--timeout",
            "1200",
        ],
        cwd=ROOT,
        env=env,
    )
    reports = set((ROOT / "artifacts/evaluations").glob("*/report.json")) - existing
    if len(reports) != 1:
        raise RuntimeError("Expected one evaluation report; inspect artifacts/evaluations")
    evaluation_path = reports.pop()
    for _ in range(2):
        if not validate_and_repair(evaluation_path, env):
            break
    published = publish(evaluation_path)
    return published


if __name__ == "__main__":
    raise SystemExit(main())
