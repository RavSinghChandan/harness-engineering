"""Observability tests. These guard F7 (silent failure) and F8 (non-reproducibility)."""
import json

import pytest

from minihar import (
    EventType, Recording, RecordingModel, ReplayExhausted, ReplayModel, Tracer,
)


def traced_run() -> Tracer:
    t = Tracer(run_id="a7f3")
    t.record(1, EventType.RUN_START, name="run")
    t.record(1, EventType.MODEL_CALL, name="deepseek", tokens=1240,
             cost_usd=0.004, duration_ms=1200)
    t.record(1, EventType.TOOL_CALL, name="search", input="refund policy",
             output="3 results", duration_ms=300)
    t.record(2, EventType.MODEL_CALL, name="deepseek", tokens=2890,
             cost_usd=0.009, duration_ms=2100)
    t.record(2, EventType.TOOL_CALL, name="read_doc", input="doc_92",
             error="not found", duration_ms=100)
    t.record(3, EventType.MODEL_CALL, name="deepseek", tokens=3100,
             cost_usd=0.011, duration_ms=1800)
    return t


# ── the questions you get asked ──────────────────────────────────────────────

def test_cost_is_attributable():
    assert traced_run().cost() == pytest.approx(0.024)


def test_cost_breaks_down_by_model():
    assert traced_run().cost_by_model() == {"deepseek": pytest.approx(0.024)}


def test_slowest_steps_answer_why_was_it_slow():
    slowest = traced_run().slowest(2)
    assert slowest[0].duration_ms == 2100
    assert slowest[1].duration_ms == 1800


def test_tool_counts_find_the_repeated_call():
    assert traced_run().tool_counts() == {"search": 1, "read_doc": 1}


def test_errors_are_never_swallowed():
    errors = traced_run().errors()
    assert len(errors) == 1
    assert errors[0].name == "read_doc"


# ── the tree a human reads ───────────────────────────────────────────────────

def test_tree_marks_the_failing_step():
    tree = traced_run().as_tree()
    assert "ERROR" in tree
    assert "turn 2" in tree
    assert "a7f3" in tree


def test_trace_serialises_for_a_log_pipeline():
    parsed = json.loads(traced_run().to_json())
    assert len(parsed) == 6
    assert all(e["run_id"] == "a7f3" for e in parsed)


# ── truncation and redaction ─────────────────────────────────────────────────

def test_long_values_keep_head_and_tail():
    """The start says what a thing was; the end is usually where it failed."""
    t = Tracer(truncate_at=100)
    e = t.record(1, EventType.TOOL_CALL, name="read",
                 output="START" + "x" * 5_000 + "END")
    assert e.output.startswith("START")
    assert e.output.endswith("END")
    assert "omitted" in e.output


def test_short_values_are_untouched():
    e = Tracer().record(1, EventType.TOOL_CALL, name="read", output="small")
    assert e.output == "small"


@pytest.mark.parametrize(
    "secret",
    [
        pytest.param("password=hunter2", id="password"),
        pytest.param("api_key=sk-abc123", id="api-key"),
        pytest.param("token=eyJhbGci", id="token"),
    ],
)
def test_secrets_are_redacted_at_the_tracer(secret):
    """Redact here, not at the sink -- sinks get misconfigured."""
    e = Tracer().record(1, EventType.TOOL_CALL, name="login", input=secret)
    assert "REDACTED" in e.input
    assert "hunter2" not in e.input
    assert "sk-abc123" not in e.input
    assert "eyJhbGci" not in e.input


# ── replay: F8 ───────────────────────────────────────────────────────────────

def scripted(*replies):
    box = list(replies)

    def model(messages):
        return box.pop(0)

    return model


def test_recording_captures_every_model_reply():
    rec = Recording(run_id="r1", task="do a thing")
    model = RecordingModel(inner=scripted({"content": "a"}, {"content": "b"}), recording=rec)
    model([]); model([])
    assert [r["content"] for r in rec.model_replies] == ["a", "b"]


def test_replay_returns_the_same_replies_in_order():
    rec = Recording(run_id="r1", task="t",
                    model_replies=[{"content": "first"}, {"content": "second"}])
    replay = ReplayModel(recording=rec)
    assert replay([])["content"] == "first"
    assert replay([])["content"] == "second"


def test_replay_is_deterministic_across_runs():
    rec = Recording(run_id="r1", task="t", model_replies=[{"content": "x"}])
    assert ReplayModel(recording=rec)([]) == ReplayModel(recording=rec)([])


def test_replay_exhaustion_is_a_finding_not_a_crash():
    """If the harness now needs more turns, that is the thing you changed."""
    rec = Recording(run_id="r1", task="t", model_replies=[{"content": "only one"}])
    replay = ReplayModel(recording=rec)
    replay([])
    with pytest.raises(ReplayExhausted, match="more calls than the recording"):
        replay([])


def test_a_recording_survives_a_round_trip(tmp_path):
    rec = Recording(run_id="a7f3", task="refund the order",
                    model_replies=[{"content": "hi"}], stop_reason="completed")
    path = rec.save(tmp_path, label="refund_without_confirmation")

    assert "refund_without_confirmation" in path.name, "name it for what it proves"
    loaded = Recording.load(path)
    assert loaded.task == "refund the order"
    assert loaded.model_replies == [{"content": "hi"}]
    assert loaded.stop_reason == "completed"
