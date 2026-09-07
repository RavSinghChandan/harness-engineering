# P05 — Observability

**Builds:** run tracing, cost and time attribution, and offline replay.
**Prevents:** F7 (silent failure), F8 (non-reproducibility).
**Read first:** [`06-observability-and-eval/tracing-an-agent-run.md`](../../06-observability-and-eval/tracing-an-agent-run.md) and [`replay-and-debugging.md`](../../06-observability-and-eval/replay-and-debugging.md)

---

## Run it

```bash
cd projects/p05-observability
python -m pytest tests/ -q      # 17 tests
```

---

## What is here

```
minihar/tracing.py   Tracer, Event — the run as a tree
minihar/replay.py    Recording, ReplayModel — deterministic re-runs
tests/               17 tests
```

---

## The tree is the point

```
run a7f3  $0.0240  7230 tokens
|-- turn 1
|   |-- model_call   deepseek 1240tok 1200ms
|   |-- tool_call    search 0tok 300ms
|-- turn 2
|   |-- model_call   deepseek 2890tok 2100ms
|   |-- tool_call    read_doc 0tok 100ms  <-- ERROR
```

The bug is visible in three seconds. `as_tree()` exists so you can paste this
into a bug report rather than sending someone a dashboard link.

Four questions the tracer answers directly:

| Question | Method |
|---|---|
| Why did this cost $2? | `cost_by_model()` |
| Why did it take 90s? | `slowest(3)` |
| Which tool is being hammered? | `tool_counts()` |
| What actually failed? | `errors()` |

---

## Two details that matter

**Truncate from both ends.**

```python
return f"{text[:half]}\n...[{omitted} chars omitted]...\n{text[-half:]}"
```

The start of a value tells you what it was; the end is usually where the error
appeared. Cutting only the tail throws away half the evidence.

**Redact at the tracer, not at the sink.** Sinks get misconfigured, and a secret
that reached the event lives as long as the log. Three parametrised tests cover
password, api_key and token.

---

## Replay: making agent bugs fixable

The model samples, so re-running an input gives a different run. The trick is
that you do not need a deterministic *model* — you need to replay the **harness**
with the model's decisions held fixed:

```python
harness = Harness(model=ReplayModel(recording), policy=Policy(...))
result = harness.run(recording.task)
assert "Denied" in result.transcript_text()
```

That test runs in milliseconds, costs nothing, needs no API key, and fails if
someone removes the fix.

**`ReplayExhausted` is a finding, not a crash.** If your harness now asks for
more turns than the recording holds, that *is* the change you made — the
exception says so in words.

**What replay cannot do:** test a prompt change. That alters what the model would
say, so it needs live evaluation instead.

---

## Exercises

1. **Wire it into P01.** Record every model reply and tool result during a real
   run, save it, then replay. Does the outcome match?
2. **Sampling.** Trace 100% of failures and 1% of successes. Where does that
   decision live — in the tracer or the caller?
3. **A cost alert.** Compute p95 cost across many traces and alert on a doubling.
   Why is that better than alerting on one expensive run?
4. **Keep a regression suite.** Save three recordings that each prove a
   different bug is fixed. Name them for what they prove.

→ Next: [`p06-subagents`](../p06-subagents/) — delegation and isolation.
