# Harness Engineering — Module 6
# Topic: Regression Suites

---

## 1. Intuition

An eval suite tells you how good the agent is. A regression suite tells you
whether you just broke it.

They sound the same and they are not. Evals are broad, slow and score quality.
A regression suite is narrow, fast, and answers one question before you merge:
*did this change break something that used to work?*

An agent has three things that change underneath it — your prompts, your tools,
and the model itself. Only the third is out of your hands, and it is the one
that ships without warning.

---

## 2. Core Concept

### Three layers, three cadences

| Layer | Runs | Speed | Needs a model? |
|---|---|---|---|
| Harness unit tests | Every commit | Seconds | No |
| Frozen-trace replay | Every commit | Seconds | No |
| Live agent runs | Nightly | Minutes, costs money | Yes |

The middle layer is the one most teams do not have, and it is the one that gives
deterministic coverage of agent behaviour.

### Frozen-trace replay

A recorded trace holds every model response from a real run. Replay feeds those
recorded responses back to your *current* harness code and asserts the harness
behaves the same. No model call, no cost, no flakiness:

```python
def test_frozen_trace(trace_file: Path):
    recorded = Trace.load(trace_file)

    harness = Harness(model=ReplayModel(recorded.model_responses))
    result = harness.run(recorded.task)

    assert result.tool_calls == recorded.tool_calls
    assert result.stop_reason == recorded.stop_reason
    assert result.final_state == recorded.final_state
```

This catches exactly the class of bug that live evals catch slowly and
expensively: a permission rule that now blocks a call it used to allow, a
budget that trips earlier, a compaction change that drops a required fact, a
tool whose error format changed.

The model's *decisions* are frozen. What is under test is your code — which is
the part you changed.

### What to freeze

Curate rather than record everything:

1. **One trace per failure mode you have fixed.** The permanent proof it stays
   fixed.
2. **One trace per major happy path.**
3. **One trace per safety boundary** — a run where a destructive call was
   correctly refused.

Twenty to fifty traces is a healthy suite. Beyond that maintenance cost exceeds
value, because every intentional behaviour change means re-recording.

### Handling intentional changes

Replay tests fail when you deliberately change behaviour, which is correct. The
workflow needs a blessing step:

```bash
pytest tests/replay/                       # fails: 3 traces differ
pytest tests/replay/ --update-traces       # re-record, then read the diff
git diff tests/traces/                     # is every change intended?
```

The `git diff` step is the point of the whole exercise. Re-recording without
reading the diff turns the suite into a rubber stamp — and a suite that always
goes green teaches the team to trust something that is no longer checking
anything.

---

## 3. Detecting Model Drift

The provider ships a new model version and your agent's behaviour shifts. No
code changed, so nothing in CI fires.

Run the same fixed tasks against the same model daily and track the numbers:

```python
def daily_drift_check() -> None:
    results = [evaluate(harness, t, runs=5) for t in CANARY_TASKS]

    today = {r.task_id: r.pass_rate for r in results}
    baseline = load_baseline()

    for task_id, rate in today.items():
        was = baseline.get(task_id, 1.0)
        if rate < was - 0.2:                       # a 20-point drop
            alert(f"{task_id}: {was:.0%} -> {rate:.0%} — possible model drift")

    save_history(today)
```

Ten canary tasks, five runs each, once a day. That is fifty runs — cheap, and it
is the only warning you will get that the ground moved.

Track cost and turns per task too. A model that answers as well but takes two
more turns is a drift you want to know about before the invoice tells you.

---

## 4. Trade-offs

**Replay tests are brittle by design.** They fail on any behaviour change,
intended or not. That is the feature; it needs the blessing workflow to stay
tolerable.

**Frozen traces encode old assumptions.** A trace recorded before a tool was
renamed tests a world that no longer exists. Prune as you go.

**Canary runs cost money daily.** Fifty runs a day is a real if small line. It is
cheaper than finding out from users.

---

## 5. Production Notes

- **Every fixed bug gets a frozen trace**, the same day.
- **Replay runs on every commit.** It is fast and free; there is no reason not to.
- **Never re-record without reading the diff.**
- **Run canaries daily** and alert on a drop of about 20 points.
- **Track cost and turns per canary**, not just pass rate.
- **Version traces with the harness.** A trace is only meaningful against the
  code shape that produced it.

---

## 6. What To Say Out Loud

> "Evals score quality; a regression suite answers whether I just broke
> something. The layer that does the real work is frozen-trace replay: recorded
> model responses fed back into the current harness, asserting the same tool
> calls, stop reason and final state. It costs nothing and is fully
> deterministic, because the model's decisions are frozen and what is under test
> is my code — which is the part I changed. Every fixed bug gets a trace the same
> day. Separately, canary tasks run daily against the live model, because the
> provider can ship a new version and nothing in CI will fire."

---

## 7. Check Yourself

1. What does frozen-trace replay test that a live eval does not?
2. Why is the `git diff` step essential when re-recording?
3. Why do canary runs need to be daily rather than in CI?
4. Why track turns and cost per canary, not only pass rate?

→ Next: [`../07-multi-agent-harness/when-multi-agent-helps.md`](../07-multi-agent-harness/when-multi-agent-helps.md)
