# Harness Engineering — Module 8
# Topic: Cost Control

> **F9 — cost blowout.** The run completes correctly and costs more than the
> task is worth.

---

## 1. Intuition

An agent's cost is not the cost of one call. It is the cost of every call, and
each call carries the whole conversation so far.

```
turn 1:  2,000 tokens in
turn 2:  4,500 tokens in     (turn 1 is still there)
turn 3:  8,000 tokens in     (turns 1 and 2 are still there)
turn 8: 40,000 tokens in
```

Input cost grows roughly quadratically with turns. Eight turns is not eight
times one turn — it is closer to twenty. This is why agents surprise people on
the bill.

---

## 2. Core Concept

### Where the money actually goes

| Driver | Share | Lever |
|---|---|---|
| Re-sent context | usually the largest | Prompt caching, compaction |
| Tool schemas | 5–20% on tool-heavy agents | Fewer tools, terser descriptions |
| Retrieved documents | varies | Fewer chunks, better ranking |
| Output tokens | small but priced higher | Ask for shorter answers |
| Retries and loops | 0% or catastrophic | Budgets, no-progress detection |

The first row is the one to attack first, and prompt caching is the single
biggest lever available.

### Prompt caching

Providers cache a prompt **prefix** and charge a fraction for the cached part —
often around 10% of the input price. The rules:

1. The prefix must be **byte-identical** between calls.
2. It must be **at the start**.
3. Order matters: stable content first, volatile content last.

```python
# BREAKS the cache on every single turn.
system = f"You are an assistant. Current time: {datetime.now()}."

# CACHEABLE.
system = "You are an assistant."
messages.append({"role": "user", "content": f"Current time: {now}. {question}"})
```

That timestamp is a real and common mistake. One volatile token at position zero
invalidates the entire prefix, every turn, for the life of the run.

### Model routing

Not every step needs your best model:

| Step | Model |
|---|---|
| Classify intent | Cheapest |
| Summarise for compaction | Mid — this becomes the agent's memory |
| Plan and decide tools | Best |
| Format a final answer | Mid |

A router can cut spend 40–60% on multi-step agents. The risk is a cheap model
making a poor tool choice that costs three extra turns — so route the *edges* of
the loop, not the decision at its centre.

---

## 3. Minimal Implementation

```python
from dataclasses import dataclass, field

# Per million tokens. Keep this in config, not in code -- prices change.
PRICES = {
    "small": {"in": 0.15, "out": 0.60, "cached_in": 0.015},
    "large": {"in": 3.00, "out": 15.00, "cached_in": 0.30},
}


@dataclass
class CostMeter:
    """Tracks spend and stops the run before it becomes an incident."""

    ceiling_usd: float = 1.00
    spent_usd: float = 0.0
    by_model: dict[str, float] = field(default_factory=dict)
    cached_tokens: int = 0
    fresh_tokens: int = 0

    def charge(self, model: str, tokens_in: int, tokens_out: int,
               cached_in: int = 0) -> float:
        price = PRICES[model]
        fresh_in = tokens_in - cached_in

        cost = (
            fresh_in / 1e6 * price["in"]
            + cached_in / 1e6 * price["cached_in"]
            + tokens_out / 1e6 * price["out"]
        )
        self.spent_usd += cost
        self.by_model[model] = round(self.by_model.get(model, 0) + cost, 6)
        self.cached_tokens += cached_in
        self.fresh_tokens += fresh_in
        return cost

    @property
    def cache_hit_rate(self) -> float:
        total = self.cached_tokens + self.fresh_tokens
        return self.cached_tokens / total if total else 0.0

    def exceeded(self) -> bool:
        return self.spent_usd >= self.ceiling_usd

    def remaining(self) -> float:
        return max(0.0, self.ceiling_usd - self.spent_usd)
```

### Using it

```python
if meter.exceeded():
    return stop(StopReason.COST_BUDGET, partial=state.best_so_far())

if meter.remaining() < 0.05:
    messages.append(system(
        "You are nearly out of budget. Give your best answer now."
    ))
```

`cache_hit_rate` is the metric to watch. If it drops, something volatile crept
into your prefix, and you will see it in the bill before you see it anywhere else.

---

## 4. The Cheapest Wins, In Order

1. **Fix your cache prefix.** Often 50–80% off input cost, one afternoon of work.
2. **Compact aggressively.** Quadratic growth is the enemy; cut it early.
3. **Trim tool schemas.** Twenty tools with paragraph descriptions is thousands
   of tokens on every call.
4. **Route cheap steps to cheap models.**
5. **Cap output length.** "Answer in under 200 words" is free to add.
6. **Cache tool results within a run.** The same file read three times should
   cost one read.

Do them in that order. The first two usually make the rest unnecessary.

---

## 5. Trade-offs

**Cost ceiling vs. completion.** A tight ceiling produces more partial results,
and a partial result still has cost with no value. Set the ceiling from the
observed distribution, not from a guess.

**Cheap models vs. extra turns.** A cheap model that picks the wrong tool costs
three extra turns of the expensive one. Measure end-to-end cost per *completed
task*, never cost per call.

**Caching vs. freshness.** A long cached prefix is cheap and can hold stale
instructions if your prompt changes mid-session. Version the prefix.

---

## 6. Production Notes

- **Cost per completed task** is the only metric that matters. Cost per call
  hides the loops.
- **Alert on p95, not the mean.** The mean hides the runaway.
- **Emit cost per run into your trace** (Module 6) so any expensive run is
  immediately explainable.
- **Keep prices in config.** They change, and a hardcoded price becomes a
  silently wrong dashboard.
- **Test the ceiling.** A cost cap nobody has exercised is a cap that does not work.

---

## 7. What To Say Out Loud

> "Agent cost grows quadratically with turns, because every call re-sends the
> whole conversation. So the first lever is prompt caching — the stable prefix
> has to be byte-identical, which means never interpolating a timestamp into the
> system prompt, a mistake I have seen multiply a bill several times over. After
> that it is aggressive compaction to stop the quadratic growth, then trimming
> tool schemas, then routing cheap steps to cheap models. I watch cache hit rate
> and cost per completed task — cost per call hides the loops. And the ceiling
> is enforced in code with a partial result returned, not hoped for."

---

## 8. Check Yourself

1. Why does cost grow faster than linearly with turn count?
2. Why does a timestamp in the system prompt cost real money?
3. Why is cost per *completed task* better than cost per call?
4. Your cache hit rate drops from 80% to 5%. What happened?

→ Next: [`concurrency-and-queueing.md`](concurrency-and-queueing.md)
