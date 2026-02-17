"""Execution-stage typed contracts."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ToolCallRecord:
    """Normalized representation of a tool call."""

    tool_name: str
    tool_args: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_legacy(cls, raw: Any) -> "ToolCallRecord":
        if isinstance(raw, dict):
            return cls(
                tool_name=str(raw.get("tool_name", "")),
                tool_args=raw.get("tool_args", {}) or {},
            )
        return cls(tool_name="", tool_args={})

    def to_legacy(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "tool_args": self.tool_args,
        }


@dataclass
class DeveloperRunResult:
    """Typed output from developer execution."""

    success: bool
    output: Optional[str]
    tool_calls: List[ToolCallRecord] = field(default_factory=list)

    @classmethod
    def from_legacy(
        cls,
        success: bool,
        output: Optional[str],
        tool_calls: Optional[List[Any]],
    ) -> "DeveloperRunResult":
        normalized = [ToolCallRecord.from_legacy(tc) for tc in (tool_calls or [])]
        return cls(success=bool(success), output=output, tool_calls=normalized)


@dataclass
class ReviewRunResult:
    """Typed output from reviewer execution."""

    issues: List[Dict[str, Any]] = field(default_factory=list)
    history: List[Dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_legacy(
        cls,
        issues: Optional[List[Dict[str, Any]]],
        history: Optional[List[Dict[str, Any]]],
    ) -> "ReviewRunResult":
        return cls(issues=issues or [], history=history or [])

