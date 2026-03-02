"""Task-level model escalation policy."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Optional, Set

from orchestrator_core.model_config import resolve_model_config


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _normalize_agent_name(agent_name: str) -> str:
    normalized = (agent_name or "").strip().lower().replace("agent", "")
    if "developer" in normalized:
        return "developer"
    if "review" in normalized:
        return "reviewer"
    if "planner" in normalized:
        return "planner"
    return normalized


@dataclass
class TaskEscalationState:
    """Mutable per-task state for loop detection/escalation."""

    repeat_count: int = 0
    no_progress_count: int = 0
    is_escalated: bool = False
    last_signature: Optional[str] = None
    triggering_agent: Optional[str] = None
    escalation_reason: Optional[str] = None
    escalated_attempt: Optional[int] = None


@dataclass
class TaskEscalationPolicy:
    """Policy rules for task-level model escalation."""

    enabled: bool
    repeat_threshold: int
    no_progress_threshold: int
    enabled_agents: Set[str]
    escalation_models: Dict[str, str]

    @classmethod
    def from_env(cls) -> "TaskEscalationPolicy":
        agents_raw = os.getenv("ESCALATION_AGENTS", "developer,reviewer")
        enabled_agents = {
            _normalize_agent_name(agent.strip())
            for agent in agents_raw.split(",")
            if agent.strip()
        }
        escalation_models = {}
        for provider in ("ollama", "google"):
            _, _, provider_models = resolve_model_config(provider)
            escalation_models.update(provider_models)

        return cls(
            enabled=_env_bool("ESCALATION_ENABLED", False),
            repeat_threshold=_env_int("ESCALATION_REPEAT_THRESHOLD", 3),
            no_progress_threshold=_env_int("ESCALATION_NO_PROGRESS_THRESHOLD", 2),
            enabled_agents=enabled_agents,
            escalation_models=escalation_models,
        )

    def new_task_state(self) -> TaskEscalationState:
        return TaskEscalationState()

    def is_agent_eligible(self, agent_name: str) -> bool:
        if not self.enabled:
            return False
        return _normalize_agent_name(agent_name) in self.enabled_agents

    def observe_attempt(
        self,
        state: TaskEscalationState,
        agent_name: str,
        action_signature: str,
        *,
        progress_made: bool,
    ) -> None:
        if not self.is_agent_eligible(agent_name):
            return

        if action_signature and action_signature == state.last_signature:
            state.repeat_count += 1
        else:
            state.repeat_count = 1 if action_signature else 0
        state.last_signature = action_signature or None

        if progress_made:
            state.no_progress_count = 0
        else:
            state.no_progress_count += 1

    def should_escalate(self, state: TaskEscalationState) -> bool:
        if not self.enabled or state.is_escalated:
            return False
        return (
            state.repeat_count >= self.repeat_threshold
            and state.no_progress_count >= self.no_progress_threshold
        )

    def try_escalate(
        self,
        state: TaskEscalationState,
        *,
        provider: str,
        agent_name: Optional[str] = None,
        attempt_number: Optional[int] = None,
    ) -> bool:
        if not self.should_escalate(state):
            return False
        if not self.get_escalation_model(provider):
            return False

        state.is_escalated = True
        state.triggering_agent = agent_name
        state.escalation_reason = "combined_signal"
        state.escalated_attempt = attempt_number
        return True

    def get_escalation_model(self, provider: str) -> Optional[str]:
        return self.escalation_models.get((provider or "").strip().lower())

    def resolve_model(
        self,
        state: TaskEscalationState,
        *,
        provider: str,
        default_model: Optional[str],
    ) -> Optional[str]:
        if state.is_escalated:
            return self.get_escalation_model(provider) or default_model
        return default_model
