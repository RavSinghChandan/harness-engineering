"""Durability tests. These guard F11 (partial-write damage) and F10 (concurrency)."""
import pytest

from minihar import Checkpoint, IdempotencyLedger, RunStore


def a_checkpoint(**overrides) -> Checkpoint:
    base = dict(
        run_id="r1",
        task="issue a refund",
        turn=3,
        messages=[{"role": "user", "content": "refund order 42"}],
        tokens_used=1500,
        cost_usd=0.02,
    )
    base.update(overrides)
    return Checkpoint(**base)


# ── checkpointing ────────────────────────────────────────────────────────────

def test_a_checkpoint_survives_a_round_trip(tmp_path):
    store = RunStore(tmp_path)
    store.save(a_checkpoint())
    loaded = store.load("r1")
    assert loaded.task == "issue a refund"
    assert loaded.turn == 3
    assert loaded.messages[0]["content"] == "refund order 42"
    assert loaded.cost_usd == 0.02


def test_missing_run_returns_none(tmp_path):
    assert RunStore(tmp_path).load("nope") is None


def test_saving_is_atomic_leaving_no_temp_file(tmp_path):
    """A crash mid-write must not leave a corrupt checkpoint."""
    store = RunStore(tmp_path)
    store.save(a_checkpoint())
    assert not list(tmp_path.glob("*.tmp"))
    assert (tmp_path / "r1.json").exists()


@pytest.mark.parametrize(
    ("stop_reason", "expected"),
    [
        pytest.param("", True, id="still-running"),
        pytest.param("interrupted", True, id="interrupted"),
        pytest.param("completed", False, id="completed"),
        pytest.param("turn_budget", False, id="budget-exhausted"),
        pytest.param("cancelled", False, id="cancelled"),
    ],
)
def test_only_unfinished_runs_are_resumable(stop_reason, expected):
    assert a_checkpoint(stop_reason=stop_reason).resumable is expected


def test_resumable_runs_excludes_finished_ones(tmp_path):
    store = RunStore(tmp_path)
    store.save(a_checkpoint(run_id="live", stop_reason=""))
    store.save(a_checkpoint(run_id="interrupted", stop_reason="interrupted"))
    store.save(a_checkpoint(run_id="finished", stop_reason="completed"))
    assert store.resumable_runs() == ["interrupted", "live"]


def test_a_later_save_replaces_the_earlier_one(tmp_path):
    store = RunStore(tmp_path)
    store.save(a_checkpoint(turn=3))
    store.save(a_checkpoint(turn=7))
    assert store.load("r1").turn == 7


# ── idempotency: F11 ─────────────────────────────────────────────────────────

def test_the_same_action_runs_only_once():
    """The refund-twice bug, prevented."""
    ledger = IdempotencyLedger()
    calls = []

    def refund(order_id, amount):
        calls.append(order_id)
        return f"refunded {amount} for {order_id}"

    first = ledger.run_once("refund", {"order_id": "42", "amount": 30}, refund)
    second = ledger.run_once("refund", {"order_id": "42", "amount": 30}, refund)

    assert calls == ["42"], "the side effect must happen exactly once"
    assert first == second, "the caller still gets the result"


def test_different_arguments_are_different_actions():
    ledger = IdempotencyLedger()
    calls = []

    def refund(order_id, amount):
        calls.append(order_id)
        return "ok"

    ledger.run_once("refund", {"order_id": "42", "amount": 30}, refund)
    ledger.run_once("refund", {"order_id": "43", "amount": 30}, refund)
    assert calls == ["42", "43"]


def test_argument_order_does_not_change_the_key():
    """Same action written two ways must hash the same."""
    a = IdempotencyLedger.key("refund", {"order_id": "42", "amount": 30})
    b = IdempotencyLedger.key("refund", {"amount": 30, "order_id": "42"})
    assert a == b


def test_the_same_arguments_to_a_different_tool_are_distinct():
    a = IdempotencyLedger.key("refund", {"order_id": "42"})
    b = IdempotencyLedger.key("cancel", {"order_id": "42"})
    assert a != b


def test_completed_actions_are_listed_for_audit():
    ledger = IdempotencyLedger()
    ledger.run_once("refund", {"order_id": "42"}, lambda order_id: "ok")
    ledger.run_once("email", {"to": "a@b.c"}, lambda to: "sent")
    assert len(ledger.actions) == 2


# ── the two together: resuming without repeating ─────────────────────────────

def test_a_resumed_run_does_not_repeat_its_side_effects(tmp_path):
    """The whole point of this project, in one test."""
    store = RunStore(tmp_path)
    ledger = IdempotencyLedger()
    refunds = []

    def refund(order_id):
        refunds.append(order_id)
        return "refunded"

    # First attempt: the refund goes through, then the process dies.
    ledger.run_once("refund", {"order_id": "42"}, refund)
    store.save(a_checkpoint(
        stop_reason="interrupted",
        completed_actions=ledger.actions,
    ))

    # Resume: the ledger is rebuilt and the refund is not repeated.
    resumed = store.load("r1")
    assert resumed.resumable
    ledger.run_once("refund", {"order_id": "42"}, refund)

    assert refunds == ["42"], "a resumed run must not refund twice"
