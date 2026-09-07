# P01 — Minimal Loop

**Builds:** the turn cycle that always terminates.
**Prevents:** F1 (non-termination), F2 (premature stop), F3 (tool misuse), F8 (non-reproducibility).
**Read first:** [`01-harness-fundamentals/what-is-a-harness.md`](../../01-harness-fundamentals/what-is-a-harness.md)

---

## Run it

```bash
cd projects/p01-minimal-loop
python -m pytest tests/ -q
```

No API key needed — the tests drive a scripted fake model, which is how you
should test a harness anyway. Model calls are slow, costly and
non-deterministic; the loop is none of those and deserves fast unit tests.

---

## What is here

```
minihar/loop.py     the Harness class — 120 lines, four guards
tests/test_loop.py  13 tests, one per failure mode
```

### The four guards

| Guard | Stops |
|---|---|
| `max_turns` | The model calling tools forever |
| `max_seconds` | A slow run hanging a request |
| `repeat_limit` | The model repeating an identical call — stuck, not working |
| `_invoke` catching everything | One bad tool ending the whole run |

### The design decision worth arguing about

`_invoke` never raises. Every error — unknown tool, wrong arguments, an
exception inside the tool — comes back as a **tool message the model reads**.

```python
except TypeError as exc:
    return f"Error: wrong arguments for {call['name']!r}: {exc}"
```

That turns a crash into a conversation. The model sees what went wrong and
usually fixes it on the next turn. Raising instead would end the run and lose
the work already done.

The cost: a model can now loop on an error it cannot fix, which is exactly why
`repeat_limit` exists.

---

## Exercises

1. **Add a token budget.** Stop when cumulative tokens exceed a limit. Which
   `StopReason` do you add, and does `ok` include it?
2. **Make `repeat_limit` smarter.** Right now identical calls trip it. Should
   *similar* calls count? What breaks if you get that wrong?
3. **Parallel tools.** The loop runs tool calls in sequence. Make them
   concurrent — then work out which tools must *not* run concurrently.

→ Next: [`p02-tool-registry`](../p02-tool-registry/) — making tools hard to call wrong.
