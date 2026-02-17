"""Rule-based task-type routing for agent prompt variants."""
from __future__ import annotations

import re


TASK_TYPES = (
    "create_file",
    "modify_file",
    "bugfix",
    "refactor",
    "test_write",
    "review",
)


def detect_task_type(task_text: str, default: str = "modify_file") -> str:
    text = (task_text or "").lower()

    if _matches(text, r"\b(review|code review|submit_review|find issues?)\b"):
        return "review"
    if _matches(text, r"\b(test|pytest|unit test|integration test|spec)\b"):
        return "test_write"
    if _matches(text, r"\b(refactor|rename|restructure|cleanup|technical debt)\b"):
        return "refactor"
    if _matches(text, r"\b(fix|bug|error|exception|failing|regression|broken)\b"):
        return "bugfix"
    if _matches(text, r"\b(create|add|new file|scaffold|initialize)\b"):
        return "create_file"
    if _matches(text, r"\b(update|modify|change|edit|patch|adjust|improve)\b"):
        return "modify_file"
    return default


def detect_requirements_profile(text: str) -> str:
    lower = (text or "").lower()
    if _matches(lower, r"\b(hello world|simple script|minimal|single file)\b"):
        return "simple_app"
    if _matches(lower, r"\b(full[- ]stack|microservice|production|multi[- ]tenant|ocr|ollama)\b"):
        return "complex_app"
    return "standard_app"


def detect_architecture_profile(text: str) -> str:
    lower = (text or "").lower()
    if _matches(lower, r"\b(full[- ]stack|react|frontend|ui)\b"):
        return "fullstack"
    if _matches(lower, r"\b(api|fastapi|flask|backend|service)\b"):
        return "backend_api"
    return "general"


def _matches(text: str, pattern: str) -> bool:
    return re.search(pattern, text, flags=re.IGNORECASE) is not None
