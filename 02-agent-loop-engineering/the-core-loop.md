# Harness Engineering — Module 2
# Topic: The Core Loop

---

## 1. Intuition

Every agent, in every framework, is the same eight lines:

```
ask the model
  → did it want tools?
      no  → done, return the answer
      yes → run them, append results, ask again
```

That is it. LangGraph, the OpenAI Agents SDK, Claude Code — all of them are this
loop plus opinions about state, persistence and control flow.

Understanding the loop in its naked form means you can read any framework's
source and know what you are looking at, and you can debug your own without
guessing.

---

## 2. Core Concept

### The loop, honestly

```python
messages = [user_task]

while True:
    reply = model(messages)         # non-deterministic step
    messages.append(reply)

    if not reply.tool_calls:        # the ONLY natural exit
        return reply.content

    for call in reply.tool_calls:
        messages.append(run(call))  # feed results back
```

Notice `while True`. The loop has exactly **one** natural exit: the model chose
to answer instead of calling a tool. Everything else — budgets, deadlines,
cancellation — is a guard you add, because that single exit is entirely at the
model's discretion.

That is the whole reason this module exists.

### Why the model stops (or does not)

The model emits an answer instead of a tool call when it believes the task is
done. "Believes" is doing heavy lifting there. It stops too early when the task
is ambiguous, and never when it is stuck in a plan that is not working.

You cannot fix either from inside the loop. You fix the first with clearer
completion criteria in the prompt, and the second with a budget in the harness.

### State: what actually persists

```python
@dataclass
class RunState:
    run_id: str                  # threads through every log line
    messages: list[Message]      # the entire transcript
    turn: int = 0
    tokens_used: int = 0
    started_at: float = 0.0
    stop_reason: StopReason | None = None
```

The transcript is the state. There is no hidden memory in the model — if it is
not in `messages`, the model does not know it. That single fact explains most
"why did it forget?" bugs.

---

## 3. Minimal Implementation

The loop with its guards made explicit and separable:

```python
def run(self, task: str) -> RunState:
    state = RunState(run_id=new_id(), messages=[user(task)], started_at=now())

    while True:
        stop = self._should_stop(state)          # all guards in one place
        if stop:
            state.stop_reason = stop
            return state

        state.turn += 1
        reply = self.model(state.messages)
        state.messages.append(reply)
        state.tokens_used += reply.usage.total

        if not reply.tool_calls:                 # the natural exit
            state.stop_reason = StopReason.COMPLETED
            return state

        for call in reply.tool_calls:
            state.messages.append(self.tools.execute(call))

def _should_stop(self, state: RunState) -> StopReason | None:
    if state.turn >= self.max_turns:
        return StopReason.TURN_BUDGET
    if now() - state.started_at > self.max_seconds:
        return StopReason.TIME_BUDGET
    if state.tokens_used > self.max_tokens:
        return StopReason.TOKEN_BUDGET
    if self.cancelled.is_set():
        return StopReason.CANCELLED
    return None
```

Putting every guard in one function is a deliberate choice. Guards scattered
through the loop body always grow a path that skips one.

---

## 4. Premature Termination (F2)

The opposite failure, and a nastier one: the agent stops and *reports success*
while the work is unfinished.

You will not catch this with a budget. Two things help:

**Completion criteria in the prompt.** Vague briefs produce vague stopping.

```
Task complete when: the test suite passes AND you have explained the fix.
If you cannot complete it, say so explicitly and describe what is blocking you.
```

**Verification before returning.** For anything checkable, check it:

```python
if not reply.tool_calls:
    ok, reason = self.verify(state)         # run the tests, check the file exists
    if not ok:
        state.messages.append(user(
            f"That does not look complete: {reason}. Please continue."
        ))
        continue                            # push it back into the loop
    return state
```

Use this sparingly — it costs a turn and can nag an agent that was actually
right. Reserve it for tasks with a cheap, objective completion test.

---

## 5. Trade-offs

**Fixed budget vs. adaptive.** A flat `max_turns=12` is simple and sometimes cuts
off legitimate long work. Adaptive budgets (more turns for harder tasks) are
better and require you to judge difficulty up front, which is its own problem.
Start fixed; measure the distribution of turn counts; then decide.

**Fail loud vs. return partial.** When a budget trips, do you return nothing or
what you have? Usually return partial work *clearly labelled as incomplete* —
half a research summary has value; a silently truncated one is a lie.

**One loop vs. plan-then-execute.** The plain loop decides one step at a time,
which is flexible and can wander. Planning first is more directed and brittle
when the plan meets reality. The plain loop is the right default.

---

## 6. Production Notes

- **Emit an event per turn**, not just at the end. A run that has been going for
  four minutes should be visible while it is happening, not afterwards.
- **`max_turns` is per run, not per user.** One runaway run is the incident.
- **Log `stop_reason` as a metric.** The ratio of `COMPLETED` to everything else
  is the single best health indicator you have for an agent.
- **Make cancellation real.** A user who clicks stop should stop the loop before
  the next model call, not after the current one finishes. Check the flag at the
  top of `_should_stop`.

---

## 7. What To Say Out Loud

> "Every agent is the same loop: call the model, run the tools it asks for, feed
> the results back, repeat. The important detail is that the loop has exactly
> one natural exit — the model choosing to answer instead of calling a tool —
> and that exit is entirely at the model's discretion. So every other stopping
> condition is a guard I add: turn budget, wall clock, token budget,
> cancellation. I keep them in one function because scattered guards always grow
> a path that skips one. And I track stop reason as a metric — the ratio of
> completed to budget-exhausted tells me more about agent health than anything
> else."

---

## 8. Check Yourself

1. What is the loop's only natural exit, and who controls it?
2. Why will a turn budget not catch premature termination?
3. Why keep all stop conditions in a single function?
4. Your agent returns a half-finished answer. Return it or fail loudly?

→ Next: [`termination-and-budgets.md`](termination-and-budgets.md)
