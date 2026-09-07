# Harness Engineering — Module 6
# Topic: Metrics That Matter

---

## 1. Intuition

Most agent dashboards measure the model: token counts, latency, maybe a
thumbs-up rate. None of those tell you whether the *harness* is working.

The metrics that matter are the ones that map to the failure taxonomy. If a
number cannot rise without one of F1–F12 having happened, it is a useful number.
If it can drift for a dozen unrelated reasons, it is decoration.

---

## 2. Core Concept

### The five that actually matter

**1. Completion rate** — runs that reached a real answer, as opposed to hitting
a budget or erroring out.

```python
completion_rate = runs_with(stop_reason="completed") / total_runs
```

Below about 80% something structural is wrong. But read it with the next metric,
because a run can "complete" by giving up.

**2. Stop-reason distribution** — *why* runs ended. This is the single most
informative chart in an agent system:

| Stop reason | What a spike means | Failure |
|---|---|---|
| `completed` | Healthy | — |
| `max_turns` | Looping, or tasks too big | F1 |
| `budget_exceeded` | Costs out of control | F9 |
| `tool_error` | A dependency is failing | F3 |
| `no_progress` | Stuck repeating itself | F1 |
| `user_cancelled` | Too slow, or wrong answers | — |

A shift from `completed` toward `max_turns` is the earliest warning you get of a
degraded harness, and it usually appears before anyone files a complaint.

**3. Turns to completion (p50 and p95)** — the p95 is the interesting one. A p50
of 4 with a p95 of 30 means most tasks are fine and a tail is looping. The mean
hides that entirely.

**4. Cost per successful run** — not cost per run. Failed runs still cost money,
so dividing by *successes* charges failure to the metric that should carry it:

```python
cost_per_success = total_spend / max(successful_runs, 1)
```

This is the number to put in front of a finance team, and the one that moves
when caching regresses.

**5. Tool error rate, per tool** — aggregate error rate hides everything. Per
tool it points at the exact thing to fix, and separates "the dependency is down"
from "the model keeps calling it wrongly".

### What not to measure

**Token count alone.** Tokens are an input to cost, not a goal. Fewer tokens
with a lower completion rate is a worse system.

**Average latency.** Agent latency is bimodal — quick answers and long
multi-turn runs. The average describes neither.

**Thumbs-up rate on its own.** Very low volume, heavily biased toward the
annoyed, and it moves for reasons unrelated to the harness.

---

## 3. Minimal Implementation

```python
from collections import Counter
from dataclasses import dataclass


@dataclass
class RunMetrics:
    run_id: str
    stop_reason: str
    turns: int
    cost_usd: float
    duration_s: float
    tool_errors: dict[str, int]


class MetricsAggregator:
    def __init__(self):
        self.runs: list[RunMetrics] = []

    def record(self, m: RunMetrics) -> None:
        self.runs.append(m)

    def report(self) -> dict:
        if not self.runs:
            return {}

        successes = [r for r in self.runs if r.stop_reason == "completed"]
        turns = sorted(r.turns for r in self.runs)

        errors: Counter = Counter()
        for r in self.runs:
            errors.update(r.tool_errors)

        return {
            "completion_rate": len(successes) / len(self.runs),
            "stop_reasons": dict(Counter(r.stop_reason for r in self.runs)),
            "turns_p50": turns[len(turns) // 2],
            "turns_p95": turns[int(len(turns) * 0.95)],
            "cost_per_success": sum(r.cost_usd for r in self.runs) / max(len(successes), 1),
            "tool_errors": dict(errors.most_common(10)),
        }
```

Note that `cost_per_success` divides total spend — including failures — by
successes. That is deliberate. A system that burns money failing should look
expensive.

---

## 4. Alerting

Alert on *changes*, not on absolute values. Absolute thresholds either fire
constantly or never:

```python
ALERTS = [
    ("completion_rate",  "drops below", 0.80),
    ("turns_p95",        "rises above", 2.0),   # multiple of last week
    ("cost_per_success", "rises above", 1.5),   # multiple of last week
    ("tool_error_rate",  "rises above", 0.10),
]
```

The two multiplier alerts catch the regressions that have no functional symptom
— a cache ordering change, a prompt edit that makes the model chattier. Nothing
breaks; things just cost more and take longer.

---

## 5. Trade-offs

**Per-tool metrics multiply cardinality.** Forty tools times several counters is
real storage. Cap to the top tools by volume, and roll up the rest.

**Completion rate can be gamed.** An agent that answers "I could not determine
that" completes every run. Pair it with a sampled quality check.

**Cost attribution across subagents is fiddly.** Parent runs must aggregate
child spend, or delegation looks free. See
[`../07-multi-agent-harness/delegation-and-subagents.md`](../07-multi-agent-harness/delegation-and-subagents.md).

---

## 6. Production Notes

- **Chart stop reasons over time.** It is the highest-signal view in the system.
- **Report p95, never the mean.** The tail is where the failures are.
- **Divide cost by successes**, so failure shows up as expense.
- **Break tool errors down per tool**, and separate dependency failures from
  wrong calls by the model.
- **Alert on week-over-week multiples**, because silent regressions do not trip
  absolute thresholds.

---

## 7. What To Say Out Loud

> "I measure the harness, not the model. The five numbers are completion rate,
> the distribution of stop reasons, p95 turns, cost per *successful* run, and
> tool error rate per tool. Stop reasons are the most useful chart in the
> system — a shift from completed toward max_turns is the earliest warning of a
> degraded harness, usually before anyone complains. I divide cost by successes
> so failed runs show up as expense, and I alert on week-over-week multiples
> rather than absolute thresholds, because the regressions that hurt most —
> a broken cache prefix, a chattier prompt — break nothing functionally."

---

## 8. Check Yourself

1. Why is the stop-reason distribution more useful than completion rate alone?
2. Why p95 rather than the mean?
3. Why divide cost by successful runs?
4. Why alert on multiples rather than absolute values?

→ Next: [`evaluating-agents.md`](evaluating-agents.md)
