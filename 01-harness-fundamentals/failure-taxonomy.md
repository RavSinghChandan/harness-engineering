# Harness Engineering — Module 1
# Topic: Failure Taxonomy

> This is the index of the whole repo. Every later module exists to prevent one
> of these failures. When something breaks in your own system, start here.

---

## 1. Intuition

Agent failures feel chaotic and one-off. They are not. After you have debugged
twenty of them you notice there are about a dozen shapes, and each has a known
harness-level fix.

Learning the taxonomy converts "the agent did something weird" into "that is an
F3, we need a turn budget."

---

## 2. The Taxonomy

### F1 — Non-termination
The loop never ends. The model keeps calling tools, or two agents keep handing
work to each other.

**Smell:** cost graph goes vertical; a request never returns.
**Fix:** turn budget, wall-clock deadline, token budget, no-progress detection.
**Module:** `02-agent-loop-engineering/termination-and-budgets.md`

### F2 — Premature termination
The agent stops while the task is unfinished and reports success.

**Smell:** confident summaries of work that did not happen.
**Fix:** explicit completion criteria; verify before reporting done.
**Module:** `02/the-core-loop.md`

### F3 — Tool misuse
Right tool, wrong arguments. Or the wrong tool entirely.

**Smell:** validation errors in tool logs; nonsense parameters.
**Fix:** tight schemas, enums over free strings, error messages that teach.
**Module:** `03-tool-design/tool-schema-design.md`

### F4 — Context overflow
The conversation outgrows the window. Early instructions fall out silently.

**Smell:** agent "forgets" its brief on long runs; quality decays with length.
**Fix:** token budgeting, compaction, tiered memory.
**Module:** `04-context-and-memory/compaction-and-summarisation.md`

### F5 — Context poisoning
Something untrusted enters context and is treated as instruction — a web page,
a file, a tool result, another user's data.

**Smell:** agent follows instructions nobody in your product wrote.
**Fix:** treat all tool output as data; never as instruction. Provenance tags.
**Module:** `05-permissions-and-safety/prompt-injection-through-tools.md`

### F6 — Excess authority
The agent could do something it should never have been able to do.

**Smell:** a destructive action nobody approved. Usually discovered late.
**Fix:** least privilege per tool, confirmation gates, sandboxing.
**Module:** `05/permission-models.md`

### F7 — Silent failure
A step failed, the run continued, the output looks fine and is wrong.

**Smell:** users report bad results; your logs show a clean run.
**Fix:** errors as visible messages, assertions on tool results, health checks.
**Module:** `06-observability-and-eval/tracing-an-agent-run.md`

### F8 — Non-reproducibility
It failed once and you cannot make it happen again.

**Smell:** "works on my machine" for agents.
**Fix:** persist the full message list, seed where possible, replay harness.
**Module:** `06/replay-and-debugging.md`

### F9 — Cost blowout
The run completes correctly and costs far more than the task is worth.

**Smell:** unit economics upside down.
**Fix:** prompt caching, cheaper model for cheap steps, token budgets.
**Module:** `08-production-harness/cost-control.md`

### F10 — Concurrency corruption
Two runs touch the same state and interleave badly.

**Smell:** intermittent, load-dependent, unreproducible in dev.
**Fix:** per-run isolation, idempotency keys, optimistic locking.
**Module:** `08/concurrency-and-queueing.md`

### F11 — Partial-write damage
The agent died halfway through a multi-step change and left the system broken.

**Smell:** inconsistent state after a crash or timeout.
**Fix:** idempotent tools, transactions, compensating actions, checkpoints.
**Module:** `02/retry-backoff-and-idempotency.md`

### F12 — Delegation drift
A subagent solves a subtly different problem than the one delegated.

**Smell:** multi-agent output that does not fit together.
**Fix:** explicit contracts, structured returns, verification by the supervisor.
**Module:** `07-multi-agent-harness/delegation-and-subagents.md`

---

## 3. Severity Ranking

If you are prioritising work on a young system, this is the order:

| Rank | Failure | Why first |
|---|---|---|
| 1 | **F6 excess authority** | Unrecoverable. Deleted data stays deleted. |
| 2 | **F5 context poisoning** | Security boundary; grows worse with integrations. |
| 3 | **F1 non-termination** | Immediate, visible, expensive. |
| 4 | **F11 partial-write** | Corrupts state silently. |
| 5 | **F7 silent failure** | Erodes trust invisibly. |

F9 (cost) feels urgent but is usually survivable. F6 is not.

---

## 4. Using This In An Incident

1. **Classify** — which F is this? Usually obvious once you know the list.
2. **Contain** — is authority bounded? If not, that is the first fix.
3. **Reproduce** — do you have the message list? If not, that is F8, fix it next.
4. **Fix at the harness layer** — resist "let's improve the prompt". Prompts
   are not a control mechanism; they are a suggestion mechanism.

That last point is the one people get wrong. If a prompt says "never delete
without asking" and the tool *can* delete without asking, you have an F6, and no
amount of prompt tuning closes it.

---

## 5. What To Say Out Loud

> "I classify agent failures into about a dozen shapes. The two that worry me
> most are excess authority and context poisoning, because they are the ones you
> cannot undo. Non-termination is the most common and the easiest to fix — a
> turn budget and a wall-clock deadline. The important discipline is fixing at
> the harness layer rather than the prompt layer: a prompt is a suggestion, a
> permission check is a control."

---

## 6. Check Yourself

1. Your agent summarised a file it was never given. Which failure?
2. Why is F6 ranked above F1 despite F1 being more common?
3. A prompt says "always confirm before deleting". Is that a control? Why not?

→ Next: [`when-not-to-use-an-agent.md`](when-not-to-use-an-agent.md)
