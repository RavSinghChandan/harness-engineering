"""Crash a run halfway through, resume it, and refund the customer exactly once.

    python demo.py

The scenario below is the one that costs real money: a worker dies after the
payment went out but before anything recorded that it did.
"""
import tempfile
from pathlib import Path

from minihar import Checkpoint, IdempotencyLedger, RunStore


def rule(label):
    print(f"\n{'─' * 68}\n  {label}\n{'─' * 68}")


# --- the world, and how many times money actually moved ---------------------

PAYMENTS: list[str] = []


def issue_refund(order_id: str, amount: float) -> str:
    PAYMENTS.append(order_id)
    return f"refunded {amount:.2f} for {order_id}"


class WorkerCrash(Exception):
    """Stands in for SIGKILL, an OOM, or a deploy."""


def demo_checkpoint_roundtrip():
    rule("1. A checkpoint holds enough to continue")
    with tempfile.TemporaryDirectory() as tmp:
        store = RunStore(directory=Path(tmp))

        cp = Checkpoint(
            run_id="run-001",
            task="Refund the blender order",
            turn=3,
            messages=[{"role": "user", "content": "refund my blender"}],
            tokens_used=4_200,
            cost_usd=0.013,
            completed_actions=["search_orders", "get_order"],
        )
        path = store.save(cp)
        print(f"  saved            : {path.name}")

        back = store.load("run-001")
        print(f"  turn             : {back.turn}")
        print(f"  spent so far     : ${back.cost_usd:.3f}, {back.tokens_used:,} tokens")
        print(f"  actions done     : {back.completed_actions}")
        print(f"  resumable        : {back.resumable}")

        print("\n  note : the budget spent so far travels with the checkpoint.")
        print("         Resume without it and every restart hands the run a")
        print("         fresh budget -- a crash loop then bills without limit.")


def demo_finished_runs_are_not_resumable():
    rule("2. A finished run is not resumable, whatever the outcome")
    with tempfile.TemporaryDirectory() as tmp:
        store = RunStore(directory=Path(tmp))
        for run_id, reason in [("done-1", "completed"),
                               ("dead-1", "budget_exceeded"),
                               ("live-1", "interrupted"),
                               ("live-2", "")]:
            store.save(Checkpoint(run_id=run_id, task="t", turn=1, stop_reason=reason))

        print(f"  all runs        : done-1, dead-1, live-1, live-2")
        print(f"  resumable       : {store.resumable_runs()}")
        print("\n  note : 'budget_exceeded' is finished, not paused. Resuming it")
        print("         would restart the exact loop that burned the budget.")


def demo_crash_and_resume():
    rule("3. The expensive crash — worker dies after the money moved")
    PAYMENTS.clear()

    with tempfile.TemporaryDirectory() as tmp:
        store = RunStore(directory=Path(tmp))
        ledger = IdempotencyLedger()
        args = {"order_id": "ORD-1234", "amount": 41.00}

        # ---- attempt 1: crashes right after the refund succeeds ----
        print("  attempt 1:")
        try:
            result = ledger.run_once("issue_refund", args, issue_refund)
            print(f"    refund call   → {result}")
            store.save(Checkpoint(run_id="run-crash", task="refund", turn=2,
                                  completed_actions=["issue_refund"],
                                  stop_reason="interrupted"))
            print(f"    checkpointed  → yes")
            raise WorkerCrash("SIGKILL: deploy rolled the worker")
        except WorkerCrash as exc:
            print(f"    CRASH         → {exc}")

        print(f"    payments so far: {PAYMENTS}")

        # ---- attempt 2: a new worker picks the run up ----
        print("\n  attempt 2 (new worker resumes):")
        cp = store.load("run-crash")
        print(f"    loaded turn   → {cp.turn}, actions {cp.completed_actions}")

        result = ledger.run_once("issue_refund", args, issue_refund)
        print(f"    refund call   → {result}")
        print(f"    (served from the ledger, the function did not run)")

        print(f"\n  payments actually made: {PAYMENTS}")
        assert len(PAYMENTS) == 1, "the customer was paid twice"
        print(f"  the customer was refunded exactly once ✓")

        print("\n  note : without the ledger this is a double refund, and the")
        print("         retry that caused it looks completely reasonable in")
        print("         the logs.")
        print()
        print("  HONEST CAVEAT: this ledger is a dict in memory, so a real")
        print("  SIGKILL would take it with the process and the resumed worker")
        print("  WOULD pay twice. The checkpoint survives (it is on disk); the")
        print("  ledger does not. Making it durable -- same directory, same")
        print("  atomic write -- is exercise 2 in the README, and it is the")
        print("  exercise that matters most.")


def demo_keys_are_derived():
    rule("4. The key comes from the action, not from a random id")
    ledger = IdempotencyLedger()
    a = ledger.key("issue_refund", {"order_id": "ORD-1", "amount": 41.0})
    b = ledger.key("issue_refund", {"amount": 41.0, "order_id": "ORD-1"})
    c = ledger.key("issue_refund", {"order_id": "ORD-2", "amount": 41.0})

    print(f"  refund ORD-1            : {a}")
    print(f"  same, keys reordered    : {b}   {'same ✓' if a == b else 'DIFFERENT'}")
    print(f"  refund ORD-2            : {c}   {'different ✓' if a != c else 'SAME'}")

    print("\n  note : argument order does not change the key, because the")
    print("         action is the same action. A uuid generated per attempt")
    print("         would be different on the retry -- which is precisely")
    print("         when you need it to match.")


def demo_different_actions_both_run():
    rule("5. Idempotency must not swallow legitimate repeats")
    PAYMENTS.clear()
    ledger = IdempotencyLedger()

    ledger.run_once("issue_refund", {"order_id": "ORD-1", "amount": 10.0}, issue_refund)
    ledger.run_once("issue_refund", {"order_id": "ORD-2", "amount": 10.0}, issue_refund)
    ledger.run_once("issue_refund", {"order_id": "ORD-1", "amount": 10.0}, issue_refund)

    print(f"  three calls, two distinct orders")
    print(f"  payments made : {PAYMENTS}")
    print(f"  ledger holds  : {len(ledger.actions)} distinct actions")
    print("\n  note : two different customers were both refunded. Only the")
    print("         exact repeat was suppressed. A cruder guard -- 'one refund")
    print("         per run' -- would have failed the second customer.")


def demo_atomic_write():
    rule("6. Checkpoints are written atomically")
    with tempfile.TemporaryDirectory() as tmp:
        store = RunStore(directory=Path(tmp))
        store.save(Checkpoint(run_id="atom-1", task="t", turn=1))
        leftovers = [p.name for p in Path(tmp).glob("*")]

        print(f"  files on disk : {leftovers}")
        print("\n  note : written to a .tmp then renamed. A crash mid-write leaves")
        print("         the old checkpoint intact rather than a truncated file")
        print("         that still parses as JSON and quietly loses the run.")


if __name__ == "__main__":
    print("\n  P07 — DURABLE RUNS")
    demo_checkpoint_roundtrip()
    demo_finished_runs_are_not_resumable()
    demo_crash_and_resume()
    demo_keys_are_derived()
    demo_different_actions_both_run()
    demo_atomic_write()
    print(f"\n{'─' * 68}")
    print("  A crash should cost you one turn, not the run -- and never a")
    print("  second payment.")
    print(f"{'─' * 68}\n")
