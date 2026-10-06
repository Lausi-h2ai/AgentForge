"""Public package entrypoints for the orchestrator runtime."""


def __getattr__(name):
    # Agent modules import package utilities during initialization. Avoid importing
    # the orchestrator (and all agents) until an entrypoint is actually requested.
    if name in {"Orchestrator", "main"}:
        from . import orchestrator

        return getattr(orchestrator, name)
    raise AttributeError(name)


__all__ = ["Orchestrator", "main"]
