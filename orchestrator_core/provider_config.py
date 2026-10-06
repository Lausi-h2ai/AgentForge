"""Provider configuration without importing optional SDKs or exposing credentials."""

from __future__ import annotations

import json
import math
import os
from urllib.parse import urlsplit

PROVIDERS = ("openai", "ollama", "google")


def resolve_provider(provider: str | None = None) -> str:
    value = (provider or os.getenv("LLM_PROVIDER") or "openai").strip().lower()
    if value in {"openai-compatible", "openai_compatible"}:
        value = "openai"
    if value not in PROVIDERS:
        raise ValueError(f"Unsupported LLM provider: {value}; choose {', '.join(PROVIDERS)}")
    return value


def api_base(name: str, fallback: str | None = None) -> str:
    value = (os.getenv(name) or fallback or "").strip().rstrip("/")
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(f"{name} must be an HTTP(S) API root URL, without credentials or query")
    if parsed.path.endswith(("/chat/completions", "/embeddings", "/responses")):
        raise ValueError(f"{name} must be the API root (usually ending in /v1), not an endpoint")
    return value


def positive_number(name: str, default: int | float, *, integer: bool = False):
    raw = os.getenv(name, str(default))
    try:
        value = int(raw) if integer else float(raw)
    except ValueError:
        raise ValueError(
            f"{name} must be a positive {'integer' if integer else 'number'}"
        ) from None
    if value <= 0 or not math.isfinite(value):
        raise ValueError(f"{name} must be positive and finite")
    return value


def openai_llm_args(model: str | None = None) -> dict:
    selected_model = (model or os.getenv("LLM_MODEL") or "").strip()
    if not selected_model:
        raise ValueError(
            "LLM_MODEL or a model override is required for the OpenAI-compatible provider"
        )
    base = api_base("OPENAI_BASE_URL")
    try:
        additional = json.loads(os.getenv("OPENAI_ADDITIONAL_KWARGS", "{}"))
    except json.JSONDecodeError:
        raise ValueError("OPENAI_ADDITIONAL_KWARGS must be a JSON object") from None
    if not isinstance(additional, dict):
        raise ValueError("OPENAI_ADDITIONAL_KWARGS must be a JSON object")
    if {"model", "messages", "stream", "api_key", "api_base"} & additional.keys():
        raise ValueError(
            "OPENAI_ADDITIONAL_KWARGS cannot override model, messages, stream, or credentials"
        )
    return {
        "model": selected_model,
        "api_base": base,
        "api_key": os.getenv("OPENAI_API_KEY") or "not-required",
        "is_chat_model": True,
        # ReAct uses textual Action/Action Input; native function calling is not required.
        "is_function_calling_model": False,
        "context_window": positive_number("LLM_CONTEXT_WINDOW", 32768, integer=True),
        "max_tokens": positive_number("LLM_MAX_TOKENS", 4096, integer=True),
        "timeout": positive_number("LLM_REQUEST_TIMEOUT", 300),
        "max_retries": 2,
        "additional_kwargs": additional,
    }


def embedding_provider(provider: str) -> str:
    selected = (
        (os.getenv("EMBEDDING_PROVIDER") or ("none" if provider == "openai" else provider))
        .strip()
        .lower()
    )
    if selected not in (*PROVIDERS, "none"):
        raise ValueError("EMBEDDING_PROVIDER must be none, openai, ollama, or google")
    return selected
