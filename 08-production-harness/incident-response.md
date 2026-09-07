# Harness Engineering — Module 8
# Topic: Incident Response

---

## 1. Intuition

An agent incident is different from a normal outage. The service is up. Health
checks are green. Latency is fine. And the agent is doing something wrong to
real users, continuously, until someone notices.

The scariest property is that agents fail *while working*. A crashed service
stops hurting people. A confused agent keeps going.

So the first move in an agent incident is almost never "restart it". It is
**"reduce its authority"**.

---

## 2. Core Concept

### The four levers, in order of speed

| Lever | Effect | Reversible |
|---|---|---|
| **1. Kill switch** | All agent runs stop | Yes, instantly |
| **2. Read-only mode** | Agents run, cannot change anything | Yes |
| **3. Confirmation for everything** | Every write needs a human | Yes |
| **4. Tighten budgets** | Runs end sooner | Yes |

All four must be **runtime configuration**, not a deploy. If your only lever
requires a release, your incident lasts as long as your pipeline.

```python
@dataclass
class RuntimeControls:
    """Every field is remotely settable. No deploy required."""

    enabled: bool = True
    mode: Mode = Mode.ASK_FIRST
    max_turns: int = 15
    max_cost_usd: float = 1.00
    disabled_tools: frozenset[str] = frozenset()

    def gate(self) -> None:
        if not self.enabled:
            raise AgentsDisabled("Agent runs are paused by operator.")
```

Flipping `enabled` to false should take ten seconds and no code review.

### The response sequence

1. **Contain** — cut authority. Read-only mode is usually the right first move:
   it stops new damage while letting you observe what the agent is trying to do.
2. **Assess** — how many runs, which users, what did it change? This is where
   your traces earn their keep.
3. **Reverse** — undo what can be undone. This is why destructive tools should
   write an audit record *before* acting.
4. **Diagnose** — replay a failing run (Module 6).
5. **Fix at the harness layer** — resist "improve the prompt".
6. **Restore gradually** — a percentage of traffic, watching the stop-reason mix.

Step 1 before step 4. Understand later; stop the bleeding now.

### What "assess" needs

```python
def blast_radius(since: float) -> dict:
    """Answerable in one query, or your incident gets much longer."""
    return {
        "runs_affected": count_runs(since),
        "users_affected": distinct_users(since),
        "writes_performed": [
            e for e in events_since(since)
            if e.type is EventType.TOOL_CALL and e.effect is not Effect.READ
        ],
        "total_cost": sum_cost(since),
    }
```

If you cannot answer "what did it change?" in one query, build that before you
need it.

---

## 3. The Agent-Specific Incidents

**Runaway cost.** Cost graph vertical. → Kill switch, then find the loop in the
traces. Usually a tool that always fails plus no no-progress detection.

**Destructive action.** The one that ruins a week. → Read-only immediately, then
audit records to enumerate what was touched. Prevention is Module 5; there is no
good cure.

**Quality collapse.** Answers got worse with no deploy. → Usually the *provider*
changed a model, or your context grew past a threshold and compaction started
eating something important. Check cache hit rate and compaction counts.

**Injection in the wild.** An agent following instructions from content. → Cut
the tool that fetched it, then apply Module 5's containment.

**Silent wrongness.** Users report bad results; logs are clean. → The hardest.
You need evals (Module 6), because nothing in your monitoring will catch it.

---

## 4. Trade-offs

**Kill switch vs. read-only.** Killing stops everything including work that is
fine. Read-only keeps value flowing and keeps you exposed if the problem is a
*read* — an agent leaking data reads, it does not write. Match the lever to the
failure.

**Fast rollback vs. understanding.** Rolling back immediately loses the state
that would explain the bug. Capture traces first, then roll back — but do not
let that take more than a minute.

**Auto-mitigation vs. human judgement.** Automatic cost cut-offs are good.
Automatic *disabling* on an error-rate spike will fire on your busiest legitimate
day. Automate containment; keep shutdown human.

---

## 5. Production Notes

- **Write the audit record before the action, not after.** If the process dies
  mid-write you still know what it was attempting.
- **Rehearse the kill switch.** A lever nobody has pulled is a lever that does
  not work.
- **Keep a one-page runbook** with the four levers and where to flip them. In an
  incident nobody reads a wiki.
- **Alert on stop-reason distribution and cost p95**, not on individual runs.
- **Write the postmortem against the failure taxonomy.** Naming an incident "an
  F6 caused by a missing confirmation gate" makes the fix obvious and the
  pattern searchable.

---

## 6. What To Say Out Loud

> "Agent incidents are different because the service is healthy while the agent
> is doing the wrong thing — it fails while working, so it keeps hurting people
> until someone notices. My first move is never a restart, it is reducing
> authority: read-only mode, which stops new damage while I can still watch what
> it is attempting. All the levers are runtime config, never a deploy, because
> otherwise the incident lasts as long as my pipeline. Then I assess blast
> radius from traces, reverse what I can, replay to diagnose, and fix at the
> harness layer rather than the prompt. And I write audit records before the
> action, not after, so a process that dies mid-write still tells me what it was
> trying to do."

---

## 7. Check Yourself

1. Why is "restart the service" usually the wrong first move?
2. Why must the kill switch be config rather than a deploy?
3. When is read-only mode the *wrong* containment?
4. Why write the audit record before the action?

→ Next module: [`../09-frameworks-landscape/build-vs-adopt.md`](../09-frameworks-landscape/build-vs-adopt.md)
