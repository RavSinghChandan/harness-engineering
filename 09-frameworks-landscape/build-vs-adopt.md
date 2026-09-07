# Harness Engineering — Module 9
# Topic: Build vs. Adopt

---

## 1. Intuition

Every framework in this space gives you the same loop from Module 2, plus a set
of opinions about state, persistence and control flow.

The question is never "is this framework good?" It is: **do its opinions match
my problem?** A framework whose opinions match saves you months. One whose
opinions do not becomes something you fight on every ticket.

---

## 2. Core Concept

### What a framework actually gives you

| You get | Worth it when |
|---|---|
| The loop | Always — but it is 40 lines |
| Tool schema plumbing | You have many tools |
| State persistence | Runs must survive restarts |
| Streaming | User-facing |
| Tracing integration | You have no observability yet |
| Community patterns | You are learning |

### What it costs you

| You pay | Bites when |
|---|---|
| Their state model | Yours does not fit theirs |
| Their control flow | You need a shape they did not anticipate |
| Debugging through layers | Something goes wrong deep inside |
| Upgrade churn | The field moves fast |
| Not understanding your own system | An incident at 3am |

That last one is the real risk. When your agent misbehaves in production and you
have never read the loop, you are debugging two unknowns at once.

### The honest decision

```
Are you learning how agents work?
  → BUILD. Forty lines teaches more than any tutorial.

Do you need durable, resumable, long-running workflows?
  → ADOPT. That machinery is genuinely hard and worth reusing.

Is your control flow unusual -- custom permissions, odd interruption,
strange delegation?
  → BUILD. You will fight the framework on every one of those.

Do you need to ship a standard tool-calling agent this week?
  → ADOPT. Do not rebuild the ordinary.

Are you at scale with strong opinions about cost and context?
  → BUILD the harness, adopt the pieces (SDK client, tracing, evals).
```

The last row is where most mature teams land: their own loop, other people's
components.

---

## 3. The Landscape, Honestly

**LangGraph** — models the agent as a state graph with checkpointing. Genuinely
good when your problem is a *workflow with cycles* and you need durability.
Heavier than you expect for a simple loop, and the graph abstraction has a real
learning curve.

**OpenAI Agents SDK** — light, close to the API, sensible defaults for handoffs
and guardrails. Good if you are on OpenAI models and want structure without much
ceremony. Less useful if you are multi-provider.

**Claude Agent SDK** — built around the harness patterns in this repo: tool
permissions, subagents, context compaction, hooks. Strong when you want
Claude-shaped agents with these behaviours out of the box.

**MCP (Model Context Protocol)** — not a harness. It is a *protocol* for exposing
tools and data to any agent. Complementary to all of the above: use MCP for the
tool boundary, whatever you use for the loop.

**Write your own** — 200–500 lines gets you everything in `minihar`. You will
understand every failure mode, which is worth a great deal at 3am.

---

## 4. Minimal Implementation

If you adopt, keep an escape hatch. Wrap the framework behind your own interface:

```python
from typing import Protocol


class AgentRunner(Protocol):
    """Your interface. The framework is an implementation detail behind it."""

    def run(self, task: str, *, budget: Budget, policy: Policy) -> RunResult: ...


class LangGraphRunner:
    def run(self, task, *, budget, policy) -> RunResult:
        raw = self._graph.invoke({"input": task})
        return RunResult.from_langgraph(raw)      # translate at the boundary


class MiniharRunner:
    def run(self, task, *, budget, policy) -> RunResult:
        return self._harness.run(task, budget=budget, policy=policy)
```

Now switching costs you one adapter, not a rewrite. Your budgets, policy and
result type are yours regardless of what is underneath — which also means your
tests survive the switch.

---

## 5. Trade-offs

**Speed now vs. control later.** A framework ships you faster and constrains you
later. If you are validating an idea, ship. If you know this is core to your
product, the control is worth the fortnight.

**Ecosystem vs. dependency.** Integrations are real value, and every one is a
version you must track. The field moves fast enough that this is a standing tax.

**Team knowledge.** A framework everyone knows beats a bespoke harness only one
person understands. Write your own only if you will document and share it.

---

## 6. Production Notes

- **Read the loop.** Whatever you adopt, find its main loop and read it. It is a
  few hundred lines and it demystifies every subsequent bug.
- **Own your budgets and permissions**, even inside a framework. These are the
  irreversible ones; do not delegate them to someone else's defaults.
- **Pin versions.** Minor releases in this space change behaviour.
- **Keep an adapter layer** from day one, even if you never switch. It is cheap
  insurance and it makes your own code testable without the framework.

---

## 7. What To Say Out Loud

> "Every framework is the same loop plus opinions about state and control flow,
> so the question is whether those opinions match my problem, not whether the
> framework is good. I adopt when I need durable resumable workflows, because
> that machinery is genuinely hard. I build when my control flow is unusual —
> custom permissions or odd interruption — because I will fight the framework on
> every one of those. Where most mature teams land is their own loop with other
> people's components. Either way I keep budgets and permissions in my own code,
> because those are the irreversible ones, and I put an adapter between my
> system and the framework so switching costs an adapter rather than a rewrite."

---

## 8. Check Yourself

1. What is the real risk of adopting a framework you have not read?
2. Name a situation where building is clearly right, and one where adopting is.
3. Why keep budgets and permissions in your own code even inside a framework?
4. What does an adapter layer buy you if you never switch?
