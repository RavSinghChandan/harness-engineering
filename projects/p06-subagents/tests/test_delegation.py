"""Delegation tests. These guard F12 (delegation drift) and capped fan-out."""
import json

import pytest

from minihar import Contract, Delegator


def fake_subagent(output: str):
    """A subagent that always returns the same thing."""
    class Sub:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def run(self, prompt):
            return output

    return lambda **kwargs: Sub(**kwargs)


FIND_TOKEN = Contract(
    goal="Find where the session token is validated.",
    context="Python FastAPI service. Auth lives under auth/.",
    constraints=("Read only. Do not modify any file.",),
    returns={"file": "path", "function": "name", "confidence": "high|medium|low"},
    tools=("read_file", "search"),
    max_turns=8,
)


# ── the contract carries everything ──────────────────────────────────────────

def test_prompt_contains_every_part_of_the_contract():
    prompt = FIND_TOKEN.as_prompt()
    assert "GOAL:" in prompt and "session token" in prompt
    assert "CONTEXT:" in prompt and "FastAPI" in prompt
    assert "CONSTRAINTS:" in prompt and "Read only" in prompt
    assert "RETURN exactly this JSON shape" in prompt
    assert "8 turns" in prompt


def test_prompt_tells_the_subagent_how_to_report_failure():
    """A subagent that cannot say 'I failed' will invent something instead."""
    assert 'confidence "low"' in FIND_TOKEN.as_prompt()


# ── isolation ────────────────────────────────────────────────────────────────

def test_subagent_receives_only_the_contract_tools():
    captured = {}

    class Sub:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def run(self, prompt):
            return json.dumps({"file": "a.py", "function": "f", "confidence": "high"})

    Delegator(build_subagent=lambda **kw: Sub(**kw)).run(FIND_TOKEN)
    assert captured["tools"] == ("read_file", "search")
    assert captured["max_turns"] == 8


# ── structured returns ───────────────────────────────────────────────────────

def test_a_matching_return_is_usable():
    good = json.dumps({"file": "auth/jwt.py", "function": "verify", "confidence": "high"})
    result = Delegator(build_subagent=fake_subagent(good)).run(FIND_TOKEN)
    assert result.usable
    assert result.data["file"] == "auth/jwt.py"


def test_prose_instead_of_json_is_caught():
    """Prose always looks plausible. Structure either matches or does not."""
    result = Delegator(
        build_subagent=fake_subagent("I looked and I think it is in the auth folder.")
    ).run(FIND_TOKEN)
    assert not result.usable
    assert "did not return the agreed shape" in result.error


def test_missing_keys_are_named():
    partial = json.dumps({"file": "auth/jwt.py"})
    result = Delegator(build_subagent=fake_subagent(partial)).run(FIND_TOKEN)
    assert not result.usable
    assert "function" in result.error and "confidence" in result.error


def test_json_embedded_in_prose_is_still_extracted():
    messy = 'Here is what I found:\n{"file": "a.py", "function": "f", "confidence": "high"}\nHope that helps.'
    result = Delegator(build_subagent=fake_subagent(messy)).run(FIND_TOKEN)
    assert result.usable and result.data["file"] == "a.py"


def test_low_confidence_is_not_usable_even_when_well_formed():
    """The subagent saying 'I am not sure' must reach the supervisor."""
    unsure = json.dumps({"file": "?", "function": "?", "confidence": "low"})
    result = Delegator(build_subagent=fake_subagent(unsure)).run(FIND_TOKEN)
    assert not result.usable


def test_contract_without_a_shape_returns_raw_output():
    free = Contract(goal="Summarise this.", tools=("read_file",))
    result = Delegator(build_subagent=fake_subagent("a summary")).run(free)
    assert result.data["output"] == "a summary"


# ── hard caps: a delegation loop is F1 with a multiplier ─────────────────────

def test_fan_out_is_capped():
    good = json.dumps({"file": "a", "function": "b", "confidence": "high"})
    d = Delegator(build_subagent=fake_subagent(good), max_subagents=3)
    for _ in range(3):
        assert d.run(FIND_TOKEN).usable
    blocked = d.run(FIND_TOKEN)
    assert not blocked.usable
    assert "subagent limit" in blocked.error


@pytest.mark.parametrize(
    ("depth", "expected_usable"),
    [
        pytest.param(0, True, id="top-level-allowed"),
        pytest.param(1, True, id="one-level-deep-allowed"),
        pytest.param(2, False, id="two-levels-deep-blocked"),
    ],
)
def test_depth_is_capped(depth, expected_usable):
    good = json.dumps({"file": "a", "function": "b", "confidence": "high"})
    d = Delegator(build_subagent=fake_subagent(good), max_depth=2)
    assert d.run(FIND_TOKEN, depth=depth).usable is expected_usable


def test_both_sides_are_logged_so_drift_is_visible():
    good = json.dumps({"file": "a.py", "function": "f", "confidence": "high"})
    d = Delegator(build_subagent=fake_subagent(good))
    d.run(FIND_TOKEN)
    entry = d.log[0]
    assert entry["goal"].startswith("Find where")
    assert entry["returned"]["file"] == "a.py"
