"""Versioned prompt loader with simple in-process caching."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Tuple


_PROMPT_CACHE: Dict[str, Tuple[float, str]] = {}


def _prompt_root() -> Path:
    return Path(__file__).resolve().parent / "prompts"


def _default_version(agent_key: str) -> str:
    env_key = f"PROMPT_{agent_key.upper()}_VERSION"
    return os.getenv(env_key, "v1")


def load_versioned_prompt(
    agent_key: str,
    prompt_name: str,
    default_text: str,
    version: str | None = None,
) -> str:
    """
    Load prompts/<agent_key>/<version>/<prompt_name>.md with mtime cache.
    Falls back to default_text when missing or unreadable.
    """
    ver = version or _default_version(agent_key)
    prompt_path = _prompt_root() / agent_key / ver / f"{prompt_name}.md"
    if not prompt_path.exists():
        return default_text

    cache_key = str(prompt_path)
    try:
        mtime = prompt_path.stat().st_mtime
    except Exception:
        return default_text

    cached = _PROMPT_CACHE.get(cache_key)
    if cached and cached[0] == mtime:
        return cached[1]

    try:
        text = prompt_path.read_text(encoding="utf-8")
    except Exception:
        return default_text

    _PROMPT_CACHE[cache_key] = (mtime, text)
    return text

