"""Thin CLI compatibility shim for the packaged orchestrator runtime."""

from aidev_orchestrator.orchestrator import Orchestrator, execute_planning_stage, main

__all__ = ["Orchestrator", "execute_planning_stage", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
