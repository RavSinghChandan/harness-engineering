# Harness Engineering — Module 9
# Topic: LangGraph

---

## 1. Intuition

LangGraph's core idea is that an agent is a **state machine**, not a loop. You
declare nodes and the edges between them; the framework runs the graph and
persists state at every node boundary.

That reframing is the whole value. A loop with a growing pile of `if` statements
becomes a graph you can draw — and, more usefully, a graph you can pause and
resume from any node.

---

## 2. What It Actually Gives You

| Harness concern | LangGraph's answer |
|---|---|
| Loop control | The graph. Edges decide what runs next |
| Termination | An `END` node, plus a recursion limit |
| State | A typed `State` dict, threaded through every node |
| Durability | Checkpointers — save state at each node |
| Interrupts | `interrupt_before` / `interrupt_after` on a node |
| Human in the loop | Interrupt, inspect state, edit it, resume |
| Observability | LangSmith tracing, or your own callbacks |
| Permissions | **Nothing.** You build it |
| Budgets | Recursion limit only; no token or cost budget |

The durability and interrupt story is genuinely good and is the main reason to
reach for it. The permissions and budget gaps are yours to fill, exactly as
described in Modules 5 and 8.

---

## 3. The Shape

```python
from typing import Annotated, TypedDict
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver


class State(TypedDict):
    messages: Annotated[list, add_messages]     # reducer: append, don't replace
    tried_and_failed: list[str]
    budget_spent: float


def call_model(state: State) -> dict:
    reply = model.invoke(state["messages"])
    return {"messages": [reply]}                # merged via the reducer


def call_tools(state: State) -> dict:
    results = [execute(c) for c in state["messages"][-1].tool_calls]
    return {"messages": results}


def should_continue(state: State) -> str:
    last = state["messages"][-1]
    if state["budget_spent"] > MAX_SPEND:
        return END                              # your budget, your edge
    return "tools" if last.tool_calls else END


graph = StateGraph(State)
graph.add_node("model", call_model)
graph.add_node("tools", call_tools)
graph.set_entry_point("model")
graph.add_conditional_edges("model", should_continue, {"tools": "tools", END: END})
graph.add_edge("tools", "model")

app = graph.compile(
    checkpointer=SqliteSaver.from_conn_string("runs.db"),
    interrupt_before=["tools"],                 # pause before every tool call
)
```

Two things deserve attention.

**The reducer.** `Annotated[list, add_messages]` says how state merges when a
node returns a partial update. Without a reducer, returning `messages` replaces
the list rather than appending — a common and confusing first bug.

**`interrupt_before`.** This is the human-in-the-loop primitive. The graph stops
before the named node, the state is durable, and you resume by invoking again
with the same thread id. You can also *edit* the state before resuming, which is
how approval-with-modification works.

---

## 4. Where It Helps and Where It Does Not

**Helps:**

- **Durable, resumable runs.** Checkpointers are the best part of the framework
  and would take real work to build yourself (see project P07).
- **Human-in-the-loop.** Interrupt, inspect, edit, resume — with persistence
  handled.
- **Non-linear flows.** Branches, retries with different strategies, parallel
  fan-out. A plain loop expresses these badly.
- **Cycles with structure.** Plan → act → reflect → re-plan is natural as a
  graph and awkward as nested conditionals.

**Does not help:**

- **Permissions.** There is no effect model and no confirmation layer. Build it,
  and enforce it inside the tool node.
- **Cost budgets.** `recursion_limit` caps node executions, not tokens or money.
  Track spend in state and check it in your conditional edge, as above.
- **Context management.** No compaction, no budgeting. Yours.
- **Simple loops.** A three-tool agent expressed as a graph is more code and more
  concepts than a `while` loop, with no benefit.

---

## 5. Trade-offs

**Concepts to learn.** State, reducers, nodes, conditional edges, checkpointers,
thread ids. Real, and worth it only if you need durability or branching.

**Debugging is indirect.** A bug in a conditional edge shows up as the graph
going somewhere unexpected, and the stack trace is inside the framework rather
than your code. LangSmith helps considerably; without it, it is harder than
debugging a loop.

**Version churn.** The API has moved fast. Pin versions and expect migration
work between minor releases.

**State must be serialisable** for checkpointing — no open connections or file
handles. This is the same discipline durability requires anywhere, but the
framework makes it non-negotiable.

---

## 6. When To Choose It

Choose LangGraph when you need **durable, interruptible, branching** runs and do
not want to build checkpointing yourself. That combination is where it clearly
beats a hand-rolled loop.

Do not choose it for a linear tool-calling agent. That is a loop, and the loop is
about forty lines — see project P01.

Either way, you still own permissions, budgets and context. The framework runs
the graph; it does not make the agent safe.

---

## 7. What To Say Out Loud

> "LangGraph models the agent as a state machine rather than a loop, and its real
> value is checkpointers plus `interrupt_before` — durable, resumable runs with
> human-in-the-loop for free, which is genuine work to build yourself. What it
> does not give me is a permission model, cost budgets or context management, so
> I still build those: budget lives in the state and gets checked in a conditional
> edge, permissions are enforced inside the tool node. I would not reach for it
> for a linear tool-calling agent — that is a forty-line loop — but for branching
> flows that pause for approval it earns the concepts you have to learn."

---

## 8. Check Yourself

1. What does a reducer do, and what breaks without one?
2. What does `interrupt_before` make possible?
3. What does `recursion_limit` cap, and what does it *not* cap?
4. Name three harness concerns LangGraph leaves entirely to you.

→ Next: [`openai-agents-sdk.md`](openai-agents-sdk.md)
