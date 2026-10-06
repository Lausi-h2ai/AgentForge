"""Acceptance checks maintained outside model-generated projects."""

import importlib.util
import sys
from pathlib import Path


def check(case, workspace):
    path = workspace / f"{case}.py"
    spec = importlib.util.spec_from_file_location(case, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if case == "slugify":
        assert module.slugify("  Hello, WORLD!  ") == "hello-world"
        assert module.slugify("a---b___c") == "a-b-c"
        assert module.slugify("!!!") == ""
        assert module.slugify("version 2") == "version-2"
        assert module.slugify("") == ""
        assert module.slugify("A/B") == "a-b"
        assert module.slugify("h\u00e9llo w\u00f6rld") == "h-llo-w-rld"
        assert module.slugify("\u00e9") == ""
    elif case == "statistics":
        assert module.summarize([4, 1, 7]) == {"count": 3, "min": 1, "max": 7, "mean": 4.0}
        assert module.summarize([-3, -1]) == {"count": 2, "min": -3, "max": -1, "mean": -2.0}
        assert module.summarize([2.5]) == {"count": 1, "min": 2.5, "max": 2.5, "mean": 2.5}
        try:
            module.summarize([])
        except ValueError:
            pass
        else:
            raise AssertionError("Empty input must raise ValueError")
    elif case == "inventory":
        stock = module.Inventory()
        assert stock.quantity("apple") == 0
        stock.add("apple", 3)
        stock.add("apple", 2)
        stock.remove("apple", 4)
        assert stock.quantity("apple") == 1
        stock.add("pear", 2)
        assert stock.quantity("pear") == 2
        for operation, item, amount in (
            (stock.remove, "apple", 2),
            (stock.add, "apple", -1),
            (stock.remove, "apple", -1),
            (stock.remove, "missing", 1),
        ):
            try:
                operation(item, amount)
            except ValueError:
                pass
            else:
                raise AssertionError("Invalid inventory operation must raise ValueError")
        assert stock.quantity("apple") == 1
    else:
        raise ValueError(f"Unknown case: {case}")


if __name__ == "__main__":
    workspace = Path(sys.argv[2]).resolve()
    sys.path.insert(0, str(workspace))
    check(sys.argv[1], workspace)
    print(f"PASS: {sys.argv[1]} external acceptance checks")
