# Harness Engineering — Module 1
# Topic: When Not To Use An Agent

---

## 1. Intuition

An agent is a loop that lets a language model choose what happens next. That is
powerful when the path genuinely varies, and pure cost when it does not.

A great deal of production "agent" code is a fixed three-step process wrapped in
a loop that costs ten times more, fails in novel ways, and cannot be tested. The
most senior decision you will make is often **not** to build an agent.

---

## 2. Core Concept

### The decision test

Ask one question: **do I know the sequence of steps before the request arrives?**

- **Yes, always** → write a function. No loop, no agent.
- **Yes, but branching on data** → write a workflow with `if`/`else`.
- **No — it depends on what we find along the way** → this is an agent.

### The spectrum

```
  Function ──── Chain ──── Workflow ──── Agent ──── Multi-agent
    ▲                                                    ▲
  cheapest                                          most expensive
  most testable                                  least predictable
```

Always start at the left. Move right only when the left fails for a reason you
can articulate.

### Concrete comparison

| Task | Right shape | Why |
|---|---|---|
| Summarise a document | **Function** | One call. There is no decision. |
| Translate then summarise | **Chain** | Fixed order, known steps |
| Route a support ticket to a team | **Workflow** | Branching, but on known categories |
| Classify, then maybe search, then maybe escalate | **Workflow** | Still enumerable |
| Debug a failing test in an unknown codebase | **Agent** | Path depends on findings |
| Research a topic across many sources | **Agent** | Depth is data-dependent |

The debugging example is a true agent: you cannot know whether you will need to
read two files or twenty until you start reading.

---

## 3. What An Agent Actually Costs

Be honest about this before choosing one:

| Cost | Function | Agent |
|---|---|---|
| Tokens | 1 call | 5–50 calls |
| Latency | ~1s | 10–120s |
| Testability | Deterministic unit test | Scripted fakes + evals |
| Failure modes | Exception | All twelve in the taxonomy |
| Debugging | Read a stack trace | Replay a transcript |
| Cost predictability | Exact | A range, sometimes wide |

An agent is roughly **10× the cost and 10× the operational surface** of a
function. That is worth paying when the flexibility is real, and a poor trade
when it is not.

---

## 4. Minimal Implementation

Sometimes the honest answer is a function. Do not be embarrassed by this:

```python
def summarise(document: str) -> str:
    """No loop, no tools, no agent. One call, one answer, fully testable."""
    return client.complete([
        {"role": "system", "content": "Summarise in three sentences."},
        {"role": "user", "content": document},
    ]).content
```

And a workflow — branching, still no agent:

```python
def handle_ticket(ticket: Ticket) -> Response:
    category = classify(ticket.body)            # one model call

    if category == "billing":
        return billing_flow(ticket)             # deterministic
    if category == "bug":
        return attach_to_issue_tracker(ticket)  # deterministic
    return escalate_to_human(ticket)
```

Every path is enumerable, testable and cheap. Reach for the agent loop only when
you genuinely cannot draw this diagram.

---

## 5. Warning Signs You Over-Reached

You built an agent but should not have, if:

- The transcript shows the **same tool sequence every single time**
- `max_turns` is 3 and it never comes close
- You have no tools — it is a single call in a loop
- You cannot explain to a colleague what decision the model is making
- Your tests mock the model to return a fixed script — because the script *is*
  the program

That last one is the giveaway. If the useful behaviour is fully described by a
fixed script, write the script.

---

## 6. Warning Signs You Under-Reached

Conversely, you need an agent if your workflow code has:

- A growing `if`/`elif` chain nobody wants to touch
- Retry logic that depends on *what kind* of failure occurred
- Steps whose number is data-dependent ("keep searching until you find it")
- Frequent new branches for cases nobody anticipated

That is a loop trying to be born. Let it.

---

## 7. Production Notes

- Start with a workflow. Ship it. Watch where it breaks. The breakages tell you
  precisely which decisions need to be dynamic — and often it is only one.
- A **hybrid** is usually best: a deterministic workflow with one agentic step
  in the middle. You get predictable cost with flexibility exactly where needed.
- When you do build an agent, keep the tool count small. Every tool multiplies
  the decision space and the ways to get it wrong.

---

## 8. What To Say Out Loud

> "I ask one question first: do I know the steps before the request arrives? If
> yes, it is a workflow and I write ordinary code — cheaper, testable, and it
> fails in ways I understand. An agent is roughly ten times the cost and the
> operational surface, so it needs to earn that. The signal that I actually need
> one is that the number of steps is data-dependent — like debugging, where I
> cannot know if I will read two files or twenty. My favourite shape in
> production is a deterministic workflow with one agentic step in the middle."

---

## 9. Check Yourself

1. Your agent's transcript is identical on every run. What does that tell you?
2. Give a task that genuinely needs an agent and say why a workflow fails.
3. What is the hybrid shape and why is it often the best trade?

→ Next module: [`../02-agent-loop-engineering/the-core-loop.md`](../02-agent-loop-engineering/the-core-loop.md)
