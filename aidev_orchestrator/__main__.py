"""Module entrypoint for `python -m aidev_orchestrator`."""

import runpy


if __name__ == "__main__":
    runpy.run_module("aidev_orchestrator.orchestrator", run_name="__main__")
