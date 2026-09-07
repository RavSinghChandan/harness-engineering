# Harness Engineering — Module 1
# Topic: Anatomy of an Agent Turn

---

## 1. Intuition

People say "the agent did X" as if it were one action. It never is. It is a
sequence of small, boring steps, and **every incident you will ever debug
happened at one specific step**.

Knowing the steps by name turns "the agent went wrong" into "step 6 returned a
string the model misread", which is a bug you can actually fix.

---

## 2. The Nine Steps

```
   ┌──────────────────────────────────────────────┐
   │  1. ASSEMBLE   build the message list        │  ← harness
   │  2. BUDGET     will this fit? cost check     │  ← harness
   │  3. CALL       send to the model             │  ← harness
   │  4. DECIDE     model picks: answer or tools  │  ← MODEL
   │  5. VALIDATE   are these calls legal?        │  ← harness
   │  6. AUTHORISE  is this allowed? confirm?     │  ← harness
   │  7. EXECUTE    run the tools                 │  ← harness
   │  8. OBSERVE    record what happened          │  ← harness
   │  9. LOOP       append results, or stop       │  ← harness
   └──────────────────────────────────────────────┘
```

**Eight of the nine steps are yours.** Step 4 is the only one the model owns.
That ratio is the whole discipline in one picture.

### What each step is for

**1. Assemble** — system prompt, history, retrieved context, tool schemas. This
is where context engineering lives. Get it wrong and everything after is noise.

**2. Budget** — count tokens *before* sending. Check the cost ceiling. This is
the cheapest place to stop a runaway run.

**3. Call** — the network call. Timeouts, retries and rate-limit handling live
here, not in your business logic.

**4. Decide** — the model reads everything and emits either a final answer or a
list of tool calls. The only genuinely non-deterministic step.

**5. Validate** — does the tool exist? Do the arguments match the schema? Reject
early with a message the model can learn from.

**6. Authorise** — separate from validate. Validation asks *"is this
well-formed?"*; authorisation asks *"is this allowed?"* A perfectly-formed
`delete_all_users()` should still be refused.

**7. Execute** — run the tool. Timeouts, isolation, and never letting an
exception escape.

**8. Observe** — trace, metrics, cost. If you skip this you will hit F8
(non-reproducibility) and be unable to debug anything.

**9. Loop** — append results and go again, or stop with a named reason.

---

## 3. Minimal Implementation

The same loop as P01, written to make the nine steps visible:

```python
def turn(self, state: RunState) -> StepOutcome:
    # 1. ASSEMBLE
    messages = self.context.assemble(state)

    # 2. BUDGET
    if self.budget.would_exceed(messages):
        return StepOutcome.stop("token_budget")

    # 3. CALL
    reply = self.client.complete(messages, tools=self.registry.schemas())

    # 4. DECIDE  (the model's only step)
    calls = reply.tool_calls
    if not calls:
        return StepOutcome.done(reply.content)

    results = []
    for call in calls:
        # 5. VALIDATE
        problem = self.registry.validate(call)
        if problem:
            results.append(ToolResult.error(call, problem))
            continue

        # 6. AUTHORISE
        verdict = self.policy.check(call, state)
        if not verdict.allowed:
            results.append(ToolResult.denied(call, verdict.reason))
            continue

        # 7. EXECUTE
        results.append(self.registry.execute(call, timeout=self.tool_timeout))

    # 8. OBSERVE
    self.tracer.record(state.run_id, reply, results)

    # 9. LOOP
    state.append(reply, results)
    return StepOutcome.continue_()
```

Notice that steps 5 and 6 both produce a **result the model reads** rather than
an exception. A denial is information: the model can explain to the user why it
could not do the thing, which is far better than a stack trace.

---

## 4. Where Each Failure Lands

| Step | Failure that lives here |
|---|---|
| 1 Assemble | F4 overflow, F5 poisoning |
| 2 Budget | F9 cost blowout |
| 3 Call | Transient network errors, rate limits |
| 4 Decide | F3 tool misuse, F2 premature stop |
| 5 Validate | F3 tool misuse (caught) |
| 6 Authorise | **F6 excess authority** |
| 7 Execute | F11 partial writes, F10 concurrency |
| 8 Observe | F7 silent failure, F8 non-reproducibility |
| 9 Loop | F1 non-termination |

When something breaks, find the step first. It narrows the search enormously.

---

## 5. Trade-offs

**Validate and authorise as one step?** Tempting — both reject a call. Keep them
separate. Validation errors should teach the model to retry correctly;
authorisation denials should *not* be retried, they should be explained to the
user. Merging them produces agents that hammer a permission wall.

**Sequential vs parallel execution (step 7).** Parallel is faster and is what
users expect for independent reads. But two tools writing the same resource
concurrently is F10. Rule of thumb: parallelise reads freely, serialise writes.

---

## 6. Production Notes

- Give every run a `run_id` at step 1 and thread it through all nine steps. Every
  log line carries it. This one habit makes debugging tractable.
- Time each step separately. "The agent is slow" is unactionable; "step 7 p95 is
  4 seconds because of one tool" is a ticket.
- Steps 5 and 6 should be *fast and pure*. If authorisation needs a database
  call, cache it — you are on the hot path of every tool call.

---

## 7. What To Say Out Loud

> "A turn is nine steps, and only one of them belongs to the model. The harness
> assembles context, checks budget, calls, validates the tool request,
> authorises it, executes, observes, and decides whether to loop. I keep
> validation and authorisation separate on purpose: a validation error is
> something the model should retry, a permission denial is something it should
> explain to the user rather than retry. When something breaks, naming the step
> is most of the debugging."

---

## 8. Check Yourself

1. Which of the nine steps does the model own?
2. Why separate validation from authorisation?
3. A tool call succeeds but the agent reports the wrong result. Which steps?

→ Next: [`failure-taxonomy.md`](failure-taxonomy.md)
