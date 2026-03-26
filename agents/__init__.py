"""Lazy package exports to avoid importing every optional dependency up front."""
from __future__ import annotations

from importlib import import_module

__all__ = [
    "configure_llm_and_embed",
    "get_phase_model_overrides",
    "parse_json_from_response",
    "resolve_model_config",
    "ProductOwnerAgent",
    "DeveloperAgent",
    "CodeReviewerAgent",
    "RequirementsAnalystAgent",
    "DocumentationAgent",
    "TesterAgent",
    "UnitTestAgent",
    "SoftwareArchitectAgent",
    "SADTSARTPlannerAgent",
]

_MODULE_BY_EXPORT = {
    "configure_llm_and_embed": ".utils",
    "get_phase_model_overrides": ".utils",
    "parse_json_from_response": ".utils",
    "resolve_model_config": ".utils",
    "ProductOwnerAgent": ".product_owner_agent",
    "DeveloperAgent": ".developer_agent",
    "CodeReviewerAgent": ".code_reviewer_agent",
    "RequirementsAnalystAgent": ".requirements_analyst_agent",
    "DocumentationAgent": ".documentation_agent",
    "TesterAgent": ".tester_agent",
    "UnitTestAgent": ".unit_test_agent",
    "SoftwareArchitectAgent": ".software_architect_agent",
    "SADTSARTPlannerAgent": ".sadt_sart_planner_agent",
}


def __getattr__(name: str):
    if name not in _MODULE_BY_EXPORT:
        raise AttributeError(name)
    module = import_module(_MODULE_BY_EXPORT[name], __name__)
    value = getattr(module, name)
    globals()[name] = value
    return value
