"""Shared model configuration helpers with lightweight env-only dependencies."""

import os
from typing import Dict, Optional, Tuple


def resolve_model_config(provider: str) -> Tuple[Optional[str], Optional[str], Dict[str, str]]:
    """
    Resolve canonical model configuration for the active provider.

    Canonical env vars:
      - LLM_MODEL
      - LLM_ESCALATION_MODEL
    """
    provider_key = (provider or "").strip().lower() or "ollama"

    base_model = (os.getenv("LLM_MODEL") or "").strip() or None
    escalation_model = (os.getenv("LLM_ESCALATION_MODEL") or "").strip() or None

    escalation_models = {}
    if escalation_model:
        escalation_models[provider_key] = escalation_model

    return base_model, base_model, escalation_models


def get_phase_model_overrides(provider: str) -> Tuple[Optional[str], Optional[str]]:
    """Backward-compatible wrapper around resolve_model_config()."""
    planning, execution, _ = resolve_model_config(provider)
    return planning, execution
