"""Central blackboard state for orchestrator runtime."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class BlackboardState:
    """
    Shared mutable orchestrator state.
    This is intentionally minimal and mirrors existing orchestrator fields.
    """

    technical_architecture: Optional[Dict[str, Any]] = None
    plan: List[str] = field(default_factory=list)
    sadt_plan: Optional[List[str]] = None
    planner_source: Optional[str] = None
    files: Dict[str, Any] = field(default_factory=dict)
    run_command: str = ""
    last_completed_task_index: int = -1
    task_checkpoints: Dict[int, Any] = field(default_factory=dict)

