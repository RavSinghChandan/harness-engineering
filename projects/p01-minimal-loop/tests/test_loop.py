"""Every test here maps to a failure in 01-harness-fundamentals/failure-taxonomy.md."""
import pytest

from minihar import Harness, StopReason


def scripted(*replies):
    """A fake model that returns each reply in turn, then repeats the last."""
    box = list(replies)

    def model(messages):
        return box.pop(0) if len(box) > 1 else box[0]

    return model


def say(text):
    return {"role": "assistant", "content": text}


def call(name, **arguments):
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"id": "1", "name": name, "arguments": arguments}],
    }


def test_answers_without_tools():
    result = Harness(model=scripted(say("42"))).run("what is six times seven")
    assert result.output == "42"
    assert result.stop_reason is StopReason.COMPLETED
    assert result.turns == 1
    assert result.ok


def test_runs_a_tool_then_answers():
    result = Harness(
        model=scripted(call("add", a=2, b=3), say("5")),
        tools={"add": lambda a, b: a + b},
    ).run("add two and three")
    assert result.output == "5"
    assert result.turns == 2
    tool_messages = [m for m in result.messages if m["role"] == "tool"]
    assert tool_messages[0]["content"] == "5"


# ── F1: non-termination ──────────────────────────────────────────────────────

def test_turn_budget_stops_an_endless_loop():
    """A model that always calls a tool must still terminate."""
    result = Harness(
        model=scripted(call("tick")),
        tools={"tick": lambda: "tock"},
        max_turns=4,
        repeat_limit=99,           # isolate the turn budget
    ).run("loop forever")
    assert result.stop_reason is StopReason.TURN_BUDGET
    assert result.turns == 4
    assert not result.ok


def test_no_progress_detection_beats_the_turn_budget():
    """Repeating the identical call is stuck, not working."""
    result = Harness(
        model=scripted(call("tick")),
        tools={"tick": lambda: "tock"},
        max_turns=50,
        repeat_limit=3,
    ).run("loop forever")
    assert result.stop_reason is StopReason.NO_PROGRESS
    assert result.turns == 3


def test_time_budget_stops_a_slow_run():
    import time

    def slow(messages):
        time.sleep(0.05)
        return call("tick")

    result = Harness(
        model=slow,
        tools={"tick": lambda: "tock"},
        max_turns=100,
        max_seconds=0.1,
        repeat_limit=99,
    ).run("slowly")
    assert result.stop_reason is StopReason.TIME_BUDGET


# ── F3: tool misuse ──────────────────────────────────────────────────────────

def test_unknown_tool_is_reported_not_raised():
    result = Harness(
        model=scripted(call("teleport"), say("understood")),
        tools={"add": lambda a, b: a + b},
    ).run("teleport me")
    tool_reply = [m for m in result.messages if m["role"] == "tool"][0]["content"]
    assert "unknown tool" in tool_reply
    assert "add" in tool_reply, "the model should be told what it CAN call"
    assert result.ok, "a bad tool name must not end the run"


def test_wrong_arguments_are_reported_not_raised():
    result = Harness(
        model=scripted(call("add", a=1), say("fixed")),
        tools={"add": lambda a, b: a + b},
    ).run("add")
    tool_reply = [m for m in result.messages if m["role"] == "tool"][0]["content"]
    assert "wrong arguments" in tool_reply
    assert result.ok


def test_a_raising_tool_does_not_kill_the_run():
    def explode():
        raise ValueError("boom")

    result = Harness(
        model=scripted(call("explode"), say("recovered")),
        tools={"explode": explode},
    ).run("break it")
    tool_reply = [m for m in result.messages if m["role"] == "tool"][0]["content"]
    assert "ValueError: boom" in tool_reply
    assert result.ok


# ── F8: reproducibility ──────────────────────────────────────────────────────

def test_full_transcript_is_kept_for_debugging():
    result = Harness(
        model=scripted(call("add", a=1, b=1), say("2")),
        tools={"add": lambda a, b: a + b},
    ).run("add one and one")
    roles = [m["role"] for m in result.messages]
    assert roles == ["user", "assistant", "tool", "assistant"]


@pytest.mark.parametrize(
    ("reason", "expected_ok"),
    [
        pytest.param(StopReason.COMPLETED, True, id="completed-is-ok"),
        pytest.param(StopReason.TURN_BUDGET, False, id="turn-budget-is-not-ok"),
        pytest.param(StopReason.TIME_BUDGET, False, id="time-budget-is-not-ok"),
        pytest.param(StopReason.NO_PROGRESS, False, id="no-progress-is-not-ok"),
    ],
)
def test_only_completion_counts_as_success(reason, expected_ok):
    from minihar import TurnResult

    result = TurnResult("", reason, 1, [], 0.0)
    assert result.ok is expected_ok
