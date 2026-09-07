# P07 — Durable Runs

**Builds:** checkpointing, resumption, and idempotent side effects.
**Prevents:** F10 (concurrency corruption), F11 (partial-write damage).
**Read first:** [`02-agent-loop-engineering/retry-backoff-and-idempotency.md`](../../02-agent-loop-engineering/) and [`08-production-harness/incident-response.md`](../../08-production-harness/incident-response.md)

---

## Run it

```bash
cd projects/p07-durable-runs
python -m pytest tests/ -q      # 16 tests
```

---

## The bug this prevents

An agent issues a refund. The process dies before the run finishes. It resumes.

**Without a ledger it refunds again.** That is F11, and the customer notices
before you do.

```python
def test_a_resumed_run_does_not_repeat_its_side_effects():
    ledger.run_once("refund", {"order_id": "42"}, refund)
    # ... process dies, checkpoint saved, run resumes ...
    ledger.run_once("refund", {"order_id": "42"}, refund)

    assert refunds == ["42"], "a resumed run must not refund twice"
```

The key is `sha256(tool + sorted arguments)`, so the same action written two
ways still hashes the same — a test covers argument ordering explicitly.

---

## Atomic checkpoint writes

```python
temp = path.with_suffix(".tmp")
temp.write_text(...)
temp.replace(path)          # atomic rename
```

A crash mid-write must not leave a corrupt checkpoint, because that loses the
entire run rather than the last turn. Write then rename; never write in place.

---

## Only unfinished runs resume

```python
@property
def resumable(self) -> bool:
    return self.stop_reason in ("", "interrupted")
```

A run that hit its budget or was cancelled is *finished* — resuming it would
restart work the operator deliberately stopped. A parametrised test covers all
five stop reasons.

---

## Exercises

1. **Postgres store.** Swap the directory for a table. What does `save` need so
   two workers cannot resume the same run — and which failure is that?
2. **Ledger persistence.** The ledger is in memory, so a real restart loses it.
   Persist it, and decide whether it lives with the checkpoint or separately.
3. **Compensating actions.** Some effects cannot be made idempotent — a sent
   email. Design an "undo" record and say when it is worth the complexity.
4. **Checkpoint frequency.** Every turn is safe and slow. Every five is fast and
   loses work. Where do you land, and what decides it?

→ Next: [`p08-capstone-harness`](../p08-capstone-harness/) — all of it, wired together.
