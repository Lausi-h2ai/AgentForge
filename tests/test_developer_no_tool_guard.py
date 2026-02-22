import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.developer_agent import DeveloperAgent


def _agent():
    agent = DeveloperAgent.__new__(DeveloperAgent)
    return agent


def test_no_tool_guard_does_not_trigger_too_early_on_event_count():
    agent = _agent()
    should_abort = agent._should_abort_for_no_tool_calls(
        elapsed=1.5,
        stream_event_count=200,
        tool_call_count=0,
        stream_buffer="Action: write_file\nAction Input: {\"filename\":\"a.py\"",
        timeout_seconds=45,
        max_stream_events=140,
        min_elapsed_for_event_guard=8,
    )
    assert should_abort is False


def test_no_tool_guard_triggers_after_elapsed_when_no_progress():
    agent = _agent()
    should_abort = agent._should_abort_for_no_tool_calls(
        elapsed=50,
        stream_event_count=10,
        tool_call_count=0,
        stream_buffer="just thinking without tool call",
        timeout_seconds=45,
        max_stream_events=140,
        min_elapsed_for_event_guard=8,
    )
    assert should_abort is True


def test_no_tool_guard_does_not_trigger_if_inflight_action_payload_detected():
    agent = _agent()
    should_abort = agent._should_abort_for_no_tool_calls(
        elapsed=10,
        stream_event_count=400,
        tool_call_count=0,
        stream_buffer="Action: add_code_block\nAction Input: {\"properties\":{\"filepath\":\"models.py\"",
        timeout_seconds=45,
        max_stream_events=140,
        min_elapsed_for_event_guard=8,
    )
    assert should_abort is False
