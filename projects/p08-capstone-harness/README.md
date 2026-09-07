# P08 — Capstone Harness

**Builds:** every layer, wired together into a harness you could ship.
**Prevents:** all twelve failures in the taxonomy.

---

## Run it

```bash
cd projects/p08-capstone-harness
python -m pytest tests/ -q      # 16 end-to-end tests
```

---

## What is wired together

| Layer | From | What it contributes |
|---|---|---|
| Loop, budgets, termination | P01 | Turn, time, token, cost, no-progress |
| Tool dispatch and errors | P02 | Errors the model can act on |
| Context assembly | P03 | Cacheable prefix, budgeted sections |
| Permissions | P04 | Effect-based policy, injection containment |
| Tracing | P05 | Every step, cost attribution, printable tree |
| Delegation | P06 | Contracts with structured returns |
| Durability | P07 | Checkpoints and idempotency |

The tests exercise them **together**, because the interesting bugs live in the
seams — a denial that ends the run, a trace that misses a step, a budget that
does not fire when a tool is slow.

---

## The nine steps, visible in the code

```python
while True:
    stop = self._should_stop(...)      # 2. BUDGET  (and cancellation)
    if stop: return self._finish(stop, ...)

    reply = self.model(messages)       # 3. CALL
    tracer.record(...)                 # 8. OBSERVE

    if not reply.tool_calls:           # 4. DECIDE -- the model's only step
        return self._finish(COMPLETED, ...)

    for call in reply.tool_calls:
        result = self.tools.execute(...)   # 5. VALIDATE 6. AUTHORISE 7. EXECUTE
        messages.append(...)               # 9. LOOP
```

Eight of nine steps are the harness. That ratio is the discipline.

---

## Four invariants the tests pin down

**1. Every budget terminates.** A parametrised test covers turn, token, cost and
no-progress, and asserts `not result.ok` — a budget stop must never report
success.

**2. Cancellation costs nothing.** Checked *before* the model call:

```python
assert calls == [], "no model call should have happened"
```

**3. A denial does not end the run.**

```python
assert result.ok, "a denial must not end the run -- the agent explains itself"
```

**4. Untrusted content removes destructive tools** for the rest of the run — the
containment from Module 5, tested end to end.

---

## What is deliberately not here

- **No retries with backoff.** Real network handling belongs at the client.
- **No streaming.** It complicates the loop without teaching anything new.
- **No real model client.** Swap `model` for any callable that takes messages
  and returns a reply dict.

`minihar` is a teaching harness that happens to be correct, not a framework.
Read it, break it, then decide whether to adopt one — Module 9 covers that
decision.

---

## Exercises

1. **Wire in P03 and P07.** Call `assemble` at the top of the loop, checkpoint
   every turn. Which existing tests break, and why is that informative?
2. **Add a real client.** Point `model` at DeepSeek or Claude. What is the first
   thing that breaks, and which module covers it?
3. **Break it deliberately.** Remove the `repeat_limit` guard and watch a test
   fail. Do the same for each guard — that is the taxonomy made concrete.
4. **Measure it.** Run 50 tasks and plot the stop-reason distribution. If more
   than a few percent are not `COMPLETED`, what would you fix first?
