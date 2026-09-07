# Harness Engineering — Module 7
# Topic: Message Passing

---

## 1. Intuition

When one agent hands work to another, the whole handoff is a string. There is no
type system across that boundary, no compiler, no stack trace. Whatever the
sender writes, the receiver reads as plain text and interprets however it likes.

Which means the message format *is* the interface, and it deserves the same care
you would give a public API — because that is exactly what it is.

---

## 2. Core Concept

### What a handoff must carry

A parent delegating a task has to send four things. Leave any out and the child
either guesses or fails:

```python
@dataclass
class Handoff:
    task: str                       # what to do, in full — no pronouns
    context: dict[str, str]         # facts the child cannot discover itself
    constraints: list[str]          # what it must not do
    output_contract: str            # the shape the parent will parse
```

**`task` must be self-contained.** The commonest delegation bug is a parent
writing "check the other one too". The child has no idea what "the other one" is,
because it never saw the parent's conversation. Every reference must be resolved
before it is sent.

**`context` carries what the child cannot find.** The user's account id, the
constraint stated three turns ago. Not the whole transcript — that defeats the
point of delegating, which was to keep the child's context small.

**`constraints` are advisory and must also be enforced.** "Do not modify files"
in a message is a suggestion. The same rule in the child's permission layer is a
guarantee. Send both: the message so the child does not try, the permission so
it cannot.

**`output_contract` states the shape.** Without it the child returns prose and
the parent has to parse English.

### Returning results

```python
@dataclass
class Result:
    status: str                     # "completed" | "partial" | "failed"
    output: str
    evidence: list[str] = field(default_factory=list)   # ids, paths, urls
    unresolved: list[str] = field(default_factory=list)
    cost_usd: float = 0.0
    turns: int = 0
```

`status` being structural matters. A child that hit its budget must not return
prose that reads like success — the parent has no reliable way to detect that,
and it will build on a half-finished result.

`unresolved` is the field that makes multi-agent systems debuggable. A child
saying "I could not access the billing API" lets the parent adapt. A child
silently omitting billing produces a confident, wrong answer.

`cost_usd` and `turns` let the parent aggregate. Without them delegation looks
free, and the total spend of a run becomes unknowable.

### Why not just pass the transcript

Because it defeats the purpose. The reason to delegate is to give a subtask a
clean, small context. Forwarding the parent's history means paying for it twice
and re-importing whatever confusion was in it.

Worse, it spreads contamination: if the parent's context contains injected
instructions from a tool result, forwarding it hands them to the child too. A
structured handoff is a natural quarantine boundary — see
[`../05-permissions-and-safety/prompt-injection-through-tools.md`](../05-permissions-and-safety/prompt-injection-through-tools.md).

---

## 3. Minimal Implementation

```python
class Delegator:
    """Structured handoff with enforced, not requested, constraints."""

    def delegate(self, handoff: Handoff, *, budget: Budget) -> Result:
        prompt = self._render(handoff)

        child = Harness(
            tools=self._tools_for(handoff),      # narrowed, not the full set
            permissions=PermissionLayer(mode=Mode.READ_ONLY),   # enforced
            budget=budget,                       # child cannot exceed it
        )

        trace = child.run(prompt)
        return Result(
            status="completed" if trace.stop_reason == "completed" else "partial",
            output=trace.output,
            evidence=trace.artefacts,
            unresolved=trace.unresolved,
            cost_usd=trace.cost_usd,
            turns=trace.turns,
        )

    def _render(self, h: Handoff) -> str:
        parts = [f"TASK\n{h.task}"]
        if h.context:
            parts.append("CONTEXT\n" + "\n".join(f"- {k}: {v}" for k, v in h.context.items()))
        if h.constraints:
            parts.append("CONSTRAINTS\n" + "\n".join(f"- {c}" for c in h.constraints))
        parts.append(f"OUTPUT\n{h.output_contract}")
        return "\n\n".join(parts)
```

The child's budget is subtracted from the parent's, not granted fresh. Otherwise
three children each spend the parent's full allowance and the run costs four
times what the budget said.

---

## 4. The Telephone Game

Each hop loses fidelity. Parent to child to grandchild, and the original intent
is two paraphrases away from the task actually being done.

Two rules keep it manageable:

**Depth one by default.** A child that wants to delegate usually indicates the
decomposition was wrong. Allow depth two only with an explicit reason.

**Pass the original task text down verbatim**, alongside the paraphrase:

```python
context = {
    "original_request": root_task,          # unchanged, all the way down
    "your_slice": specific_subtask,
}
```

A grandchild can then check its slice against what the user actually asked, and
notice when the chain has drifted.

---

## 5. Trade-offs

**Structured handoffs are more work than a string.** Worth it the moment there
is more than one child, or any child that can fail partially.

**Contracts constrain.** A child that discovers something valuable outside its
output shape has nowhere to put it. `unresolved` is the escape hatch; a free-text
`notes` field is a reasonable second one.

**Enforced constraints can block legitimate work.** A child told read-only that
genuinely needs to write must fail and say so, rather than being allowed to
write. That is the correct trade, but it does mean some tasks come back
unfinished.

---

## 6. Production Notes

- **Resolve every reference before sending.** No "the other one", no "it".
- **Send constraints twice** — in the message and in the permission layer.
- **Make status structural**, never inferred from the text.
- **Return cost and turns** so the parent can aggregate.
- **Subtract the child's budget from the parent's.**
- **Log both directions** with a shared run id, or a multi-agent failure is
  unreadable.
- **Default to depth one.**

---

## 7. What To Say Out Loud

> "A handoff is an API even though it is a string, so it is structured: task,
> context, constraints, output contract. The task has to be fully self-contained
> — the commonest bug is a parent writing 'check the other one too' when the
> child never saw the conversation. Constraints go in the message *and* in the
> child's permission layer, because in a message they are a suggestion and in the
> layer they are a guarantee. Results come back with a structural status, so a
> child that hit its budget cannot return prose that reads like success, plus
> cost and turns so the parent can aggregate — otherwise delegation looks free
> and total spend is unknowable."

---

## 8. Check Yourself

1. Why must every reference be resolved before a handoff is sent?
2. Why send constraints in both the message and the permission layer?
3. Why must `status` be a field rather than inferred from the output?
4. Why is forwarding the parent's transcript a bad default?

→ Next: [`shared-state-and-conflicts.md`](shared-state-and-conflicts.md)
