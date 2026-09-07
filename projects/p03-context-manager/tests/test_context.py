"""Context tests. These guard F4 (overflow) and F9 (cost)."""
import pytest

from minihar import Compactor, ContextAssembler, ContextBudget, Section


def assembler(window=4_000, reserve=500):
    return ContextAssembler(budget=ContextBudget(window=window, reserve_for_response=reserve))


# ── ordering, which drives caching and attention ─────────────────────────────

def test_system_prompt_is_first_for_prefix_caching():
    messages = assembler().assemble(system="You are helpful.", current={"role": "user", "content": "hi"})
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == "You are helpful."


def test_current_request_is_last_where_attention_is_strongest():
    messages = assembler().assemble(
        system="sys",
        current={"role": "user", "content": "the actual question"},
        history=[{"role": "user", "content": "older"}],
    )
    assert messages[-1]["content"] == "the actual question"


def test_retrieved_content_is_fenced_as_data():
    messages = assembler().assemble(
        system="sys", current={"role": "user", "content": "q"}, retrieved="a document"
    )
    fenced = [m for m in messages if "Reference material" in m["content"]][0]
    assert "not instructions" in fenced["content"]


# ── budgets ──────────────────────────────────────────────────────────────────

def test_response_headroom_is_never_spent():
    budget = ContextBudget(window=10_000, reserve_for_response=2_000)
    assert budget.usable == 8_000


@pytest.mark.parametrize(
    ("section", "share"),
    [
        pytest.param(Section.SYSTEM, 0.10, id="system-10pc"),
        pytest.param(Section.MEMORY, 0.05, id="memory-5pc"),
        pytest.param(Section.RETRIEVED, 0.30, id="retrieved-30pc"),
        pytest.param(Section.HISTORY, 0.45, id="history-45pc"),
    ],
)
def test_each_section_gets_its_share(section, share):
    budget = ContextBudget(window=10_000, reserve_for_response=0)
    assert budget.allowance(section) == int(10_000 * share)


def test_oversized_retrieved_text_is_trimmed_with_a_marker():
    a = assembler(window=2_000, reserve=0)
    messages = a.assemble(
        system="sys", current={"role": "user", "content": "q"}, retrieved="x" * 20_000
    )
    fenced = [m for m in messages if "Reference material" in m["content"]][0]
    assert "trimmed to fit" in fenced["content"]


def test_history_drops_whole_messages_never_partial():
    """Half a tool result is worse than none -- the model reasons over it."""
    a = assembler(window=1_000, reserve=0)
    history = [{"role": "user", "content": "x" * 800} for _ in range(6)]
    messages = a.assemble(system="s", current={"role": "user", "content": "q"}, history=history)

    for m in messages[1:-1]:
        assert m["content"] == "x" * 800, "a kept message must be whole"
    assert a.dropped, "dropped messages should be recorded for debugging"


def test_newest_history_survives_when_space_is_tight():
    a = assembler(window=1_200, reserve=0)
    history = [{"role": "user", "content": f"turn {i} " + "x" * 300} for i in range(6)]
    messages = a.assemble(system="s", current={"role": "user", "content": "q"}, history=history)
    kept = [m["content"] for m in messages if m["content"].startswith("turn")]
    assert "turn 5" in kept[-1], "the most recent turn must survive"


# ── compaction ───────────────────────────────────────────────────────────────

def fake_summariser(messages):
    return "The user asked for a report. Decided to use Python. Found 3 sources."


def transcript(n=12):
    out = [
        {"role": "system", "content": "You are an agent."},
        {"role": "user", "content": "Write me a report."},
    ]
    for i in range(n):
        out.append({"role": "assistant", "content": f"step {i} " + "detail " * 40})
    return out


def test_compaction_triggers_before_the_window_is_full():
    c = Compactor(model=fake_summariser, trigger_ratio=0.75)
    assert c.needs_compaction([{"role": "user", "content": "x" * 4_000}], usable=1_000)
    assert not c.needs_compaction([{"role": "user", "content": "x" * 40}], usable=1_000)


def test_compaction_reduces_size():
    c = Compactor(model=fake_summariser)
    before = transcript()
    after = c.compact(before)
    assert len(after) < len(before)
    assert c.log[0]["tokens_after"] < c.log[0]["tokens_before"]


def test_system_prompt_and_task_are_never_summarised():
    """Structural, not a hope in a prompt."""
    c = Compactor(model=fake_summariser)
    after = c.compact(transcript())
    assert after[0]["content"] == "You are an agent."
    assert after[1]["content"] == "Write me a report."


def test_recent_turns_stay_verbatim():
    c = Compactor(model=fake_summariser, keep_recent=4)
    before = transcript()
    after = c.compact(before)
    assert after[-4:] == before[-4:]


def test_the_summary_is_inserted_and_labelled():
    c = Compactor(model=fake_summariser)
    after = c.compact(transcript())
    summary = [m for m in after if "Summary of earlier work" in m["content"]]
    assert len(summary) == 1


def test_short_transcripts_are_left_alone():
    """Not worth a model call."""
    c = Compactor(model=fake_summariser)
    short = transcript(n=1)
    assert c.compact(short) == short
    assert c.compactions == 0


def test_the_summary_text_is_logged_for_debugging():
    """When an agent 'forgets', this is the first thing you need to read."""
    c = Compactor(model=fake_summariser)
    c.compact(transcript())
    assert "Found 3 sources" in c.log[0]["summary"]
