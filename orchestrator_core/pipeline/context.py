"""Shared context object passed to pipeline stages."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class StageContext:
    """Minimal context holder for stage extraction with no behavior changes."""

    orchestrator: Any
    task: Optional[str] = None
    checkpoint: Optional[Any] = None
    current_task_index: Optional[int] = None
    savepoint: Optional[str] = None
