"""Shared context object passed to pipeline stages."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class StageContext:
    """Minimal context holder for stage extraction with no behavior changes."""

    orchestrator: Any

