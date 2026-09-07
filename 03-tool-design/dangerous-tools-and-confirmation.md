# Harness Engineering — Module 3
# Topic: Dangerous Tools and Confirmation

---

## 1. Intuition

Most tools are boring. A handful can ruin someone's day. The engineering job is
telling them apart *in the type system*, so that a future colleague adding a
tool cannot accidentally make a destructive one look safe.

The mistake is deciding danger by tool name at the call site. Names drift,
someone adds `cleanup_workspace`, and it quietly deletes.

---

## 2. Core Concept

### Danger is a property of the tool, not a judgement at call time

```python
@dataclass(frozen=True)
class Tool:
    name: str
    run: Callable[..., str]
    effect: Effect                  # READ | WRITE | DESTRUCTIVE -- required
    reversible: bool = True
    value_at_risk: Callable[..., float] | None = None
```

`effect` has no default. A developer registering a tool must state it, and code
review sees it in the diff. Compare with `is_dangerous: bool = False`, where
forgetting produces a silently unsafe tool.

### The three questions that classify anything

1. **Can I undo it?** No → destructive.
2. **Does anyone outside see it?** Yes → destructive. A sent email cannot be
   unsent, and a posted message cannot be unposted.
3. **Does it cost money?** Yes → destructive, and add a value threshold.

That third one catches tools people misclassify: `issue_refund` and
`provision_server` feel like writes and behave like deletions.

### Making the dangerous version harder to reach

```python
# The safe tool takes a plain string. The dangerous one does not.
def read_file(path: str) -> str: ...

def delete_file(target: FileHandle) -> str:
    """Takes a handle returned by list_files -- not a path the model invented."""
```

Requiring a handle means the model cannot delete a file it has not first listed.
It cannot hallucinate a target. This is stronger than any confirmation, because
it removes a whole class of mistake rather than asking a human to catch it.

---

## 3. Minimal Implementation

```python
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class Danger:
    """What a confirmation prompt needs to render a decidable question."""

    summary: str
    targets: tuple[str, ...]
    reversible: bool
    value_usd: float = 0.0


def describe_danger(tool: Tool, arguments: dict[str, Any]) -> Danger:
    """Turn a raw call into something a human can judge in two seconds."""
    if tool.name == "delete_file":
        paths = arguments.get("paths") or [arguments.get("path", "?")]
        return Danger(
            summary=f"Delete {len(paths)} file{'s' if len(paths) > 1 else ''}",
            targets=tuple(paths),
            reversible=False,
        )
    if tool.name == "issue_refund":
        return Danger(
            summary=f"Refund order {arguments.get('order_id')}",
            targets=(str(arguments.get("order_id")),),
            reversible=False,
            value_usd=float(arguments.get("amount", 0)),
        )
    return Danger(
        summary=f"Run {tool.name}",
        targets=tuple(f"{k}={v}" for k, v in arguments.items()),
        reversible=tool.reversible,
    )


def gate(tool: Tool, arguments: dict, policy, confirmer) -> str | None:
    """Returns a denial message, or None to proceed."""
    if tool.effect is Effect.READ:
        return None

    danger = describe_danger(tool, arguments)

    if danger.value_usd > policy.auto_approve_limit_usd:
        return (
            f"Denied: {danger.summary} exceeds the automatic limit of "
            f"${policy.auto_approve_limit_usd:.2f} and needs human approval."
        )

    if tool.effect is Effect.DESTRUCTIVE or policy.mode is Mode.ASK_FIRST:
        if not confirmer.confirm(danger):
            return "Denied: the user declined this action."
    return None
```

Note the value threshold sits *above* the confirmation. Some actions should not
be approvable by whoever happens to be at the keyboard.

---

## 4. Audit Before, Not After

```python
audit.record(tool=tool.name, arguments=arguments, run_id=run_id,
             status="attempting")          # BEFORE
result = tool.run(**arguments)
audit.record(..., status="done", result=result)
```

If the process dies mid-call you still know what it was attempting. An audit
record written only on success is exactly missing for the case you need it —
which is Module 8's incident response.

---

## 5. Trade-offs

**Handles vs. strings.** Requiring a handle is safer and clumsier: the model
must list before it deletes, costing a turn. Worth it for destruction, overkill
for writes.

**Batching dangerous actions.** One prompt for ten deletions is less friction and
a bigger blast radius per click. Batch homogeneous items; split anything unusual.

**Thresholds.** A value limit is crude — ten £99 refunds pass a £100 limit. Add
a per-run cumulative cap alongside the per-action one.

---

## 6. Production Notes

- **No default on `effect`.** Force the decision at registration.
- **Test the gate, not just the tool.** Assert that a destructive call without
  confirmation is refused.
- **Cap destructive calls per run**, not just per call.
- **Alert on any destructive tool used outside business hours** by an agent —
  cheap signal, occasionally invaluable.

---

## 7. What To Say Out Loud

> "Danger is a property of the tool, declared at registration with no default,
> so a colleague adding a tool has to state whether it is a read, a write or
> destructive, and review sees it. I classify on three questions: can I undo it,
> does anyone outside see it, does it cost money — the third catches refunds and
> provisioning, which feel like writes and behave like deletions. Where it
> matters I make the dangerous tool take a handle rather than a string, so the
> model cannot delete something it never listed. And the audit record is written
> before the action, so a process that dies mid-call still tells me what it was
> attempting."

---

## 8. Check Yourself

1. Why does `effect` have no default value?
2. What do the three classification questions catch that intuition misses?
3. Why is a handle stronger than a confirmation prompt?
4. Why write the audit record before the action?

→ Next: [`tool-testing.md`](tool-testing.md)
