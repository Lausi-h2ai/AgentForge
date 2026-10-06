"""Protect the portfolio evaluator from reporting false success."""

import asyncio

import pytest

from scripts.evaluate_portfolio import summarize
from scripts.portfolio_acceptance import check
from scripts.portfolio_demo import demonstrate


def test_exit_zero_and_acceptance_do_not_hide_incomplete_tasks():
    result = summarize({"plan": ["a", "b"]}, {"0": {"status": "completed"}}, 0, True)
    assert result["passed"] is False
    assert result["task_completion_rate"] == 0.5
    assert summarize({}, {}, 0, True)["passed"] is False


def test_acceptance_and_timeout_are_independent_success_gates():
    state = {"plan": ["a"]}
    checkpoints = {"0": {"status": "completed", "retry_count": 2}}
    assert summarize(state, checkpoints, 0, False)["passed"] is False
    assert summarize(state, checkpoints, 0, True, timed_out=True)["passed"] is False
    assert summarize(state, checkpoints, 1, True)["passed"] is False
    result = summarize(state, checkpoints, 0, True)
    assert result["passed"] is True
    assert result["retries"] == 2
    assert result["actual_api_cost_usd"] is None


def test_offline_demo_transfers_feedback_and_restores_checkpoint(tmp_path):
    result = asyncio.run(demonstrate(tmp_path))
    assert result["status"] == "completed"
    assert result["retries"] == result["restored_retry_count"] == 1
    assert result["acceptance_passed"] is True
    assert result["live_model_calls"] == 0


@pytest.mark.parametrize(
    "case, source",
    [
        ("slugify", 'def slugify(text):\n    return text.lower().replace(" ", "-")\n'),
        (
            "statistics",
            "def summarize(values):\n"
            '    return {"count": len(values), "min": min(values), "max": max(values), '
            '"mean": sum(values) // len(values)}\n',
        ),
        (
            "inventory",
            "class Inventory:\n"
            "    def quantity(self, item): return 0\n"
            "    def add(self, item, amount): pass\n"
            "    def remove(self, item, amount): pass\n",
        ),
    ],
)
def test_external_checks_reject_incorrect_implementations(case, source, tmp_path):
    (tmp_path / f"{case}.py").write_text(source, encoding="utf-8")
    with pytest.raises((AssertionError, ValueError, ZeroDivisionError)):
        check(case, tmp_path)
