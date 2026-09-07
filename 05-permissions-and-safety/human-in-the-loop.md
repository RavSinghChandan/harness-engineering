# Harness Engineering — Module 5
# Topic: Human In The Loop

---

## 1. Intuition

A confirmation prompt only works if the human can actually judge. Ask badly and
you get worse than nothing: users learn to click "allow" without reading, and
your permission system becomes a decoration that everyone believes in.

The goal is not "ask more". It is **ask rarely, and make each ask decidable in
two seconds.**

---

## 2. Core Concept

### What a good prompt shows

```
Delete 3 files?
  /workspace/old_report.pdf
  /workspace/draft_v1.md
  /workspace/notes.txt

This cannot be undone.              [Allow]  [Deny]
```

Four things: the **action**, the **exact target**, the **scale**, and the
**reversibility**. Compare with what most systems ship:

| Bad | Missing |
|---|---|
| "Allow tool call?" | Everything |
| "Run bash command?" | Which command |
| "Agent wants file access" | Which file, read or write |
| "Proceed?" | Any information at all |

A user who approves a vague prompt has not consented to anything, and you cannot
later claim they did.

### When to ask

| Ask | Do not ask |
|---|---|
| Irreversible actions | Reads |
| Money, messages to third parties | Anything inside a scratch workspace |
| Anything outside the workspace | Repeated identical safe actions |
| Above a value threshold | Steps the user already approved as a batch |

Confirm on **effect**, not per call. Ten confirmations for one task trains
click-through faster than anything else.

### Never make deny the scary option

If denying breaks the session or loses work, users will always allow.

```python
# WRONG -- denial is punished.
if not confirm(...):
    raise RunAborted("User denied. Run terminated.")

# RIGHT -- denial is a normal outcome the agent handles.
if not confirm(...):
    return "Denied: the user declined this action."
```

The agent then explains and offers an alternative, which is exactly what a
colleague would do.

### The "always allow" trap

Convenient, and it silently converts ask-first into autonomous. If you offer it,
scope it narrowly:

```python
@dataclass(frozen=True)
class Grant:
    tool: str
    argument_shape: str        # e.g. paths under /workspace/drafts
    expires_at: float          # never permanent
    max_uses: int = 10
```

Scoped to a tool *and* an argument shape *and* a time limit. "Always allow
delete_file" is not a grant, it is a removal of the control.

---

## 3. Minimal Implementation

```python
import time
from dataclasses import dataclass, field


@dataclass
class ConfirmationRequest:
    tool: str
    summary: str                    # "Delete 3 files"
    targets: tuple[str, ...]        # the exact things affected
    reversible: bool
    value_usd: float = 0.0

    def render(self) -> str:
        lines = [self.summary + "?"]
        lines += [f"  {t}" for t in self.targets[:10]]
        if len(self.targets) > 10:
            lines.append(f"  ...and {len(self.targets) - 10} more")
        if self.value_usd:
            lines.append(f"Value: ${self.value_usd:.2f}")
        lines.append("This can be undone." if self.reversible
                     else "This CANNOT be undone.")
        return "\n".join(lines)


@dataclass
class Confirmer:
    ask: callable                              # your UI
    grants: list = field(default_factory=list)
    log: list = field(default_factory=list)

    def confirm(self, request: ConfirmationRequest) -> bool:
        if self._granted(request):
            self.log.append(("auto", request.tool))
            return True

        answer = bool(self.ask(request.render()))
        self.log.append(("allowed" if answer else "denied", request.tool))
        return answer

    def _granted(self, request: ConfirmationRequest) -> bool:
        now = time.time()
        for grant in self.grants:
            if (grant.tool == request.tool
                    and grant.expires_at > now
                    and grant.max_uses > 0
                    and all(t.startswith(grant.argument_shape)
                            for t in request.targets)):
                grant.max_uses -= 1
                return True
        return False
```

---

## 4. Asynchronous Approval

For high-value actions the human is not sitting there. The run must survive the
wait — which is P07's checkpointing:

```python
if request.value_usd > 100:
    checkpoint = save_state(run)                 # durable
    approval_id = queue_for_approval(request, checkpoint.run_id)
    return (
        f"This needs human approval (request {approval_id}). "
        "The run is paused and will continue once a decision is made."
    )
```

Do not hold a connection open for an hour. Checkpoint, return, resume on
approval.

---

## 5. Trade-offs

**Friction vs. safety.** Every prompt costs attention. Too many and they are
ignored; too few and something irreversible slips through. Tune by watching how
often users *deny* — a denial rate near zero usually means people are clicking
through, not that everything was fine.

**Batch vs. per-item.** "Delete these 3 files" is one decision; three prompts is
three chances to stop reading. Batch when the items are homogeneous, split when
one is materially riskier.

**Sync vs. async.** Sync is simple and blocks. Async needs durable runs, and it
is the only workable answer above a certain value.

---

## 6. Production Notes

- **Log every decision** with the rendered prompt. When someone says "I never
  approved that", you need to show exactly what they saw.
- **Watch the denial rate.** Near-zero means click-through, not safety.
- **Expire every grant.** Permanent grants accumulate silently and nobody audits
  them.
- **Timeout unanswered prompts as a denial**, never as an allow.
- **Show the same prompt text in the log, the UI and the audit record.** Three
  different renderings is how disputes start.

---

## 7. What To Say Out Loud

> "A confirmation only works if the human can judge it in two seconds, so every
> prompt shows the action, the exact targets, the scale, and whether it can be
> undone. 'Allow tool call?' trains people to click yes, which is worse than not
> asking. I confirm on effect rather than per call, because ten prompts for one
> task guarantees click-through. Denial is always a normal outcome the agent
> handles and explains — if denying breaks the session, users learn to always
> allow. And for high-value actions I checkpoint the run and queue it for
> approval rather than holding a connection open."

---

## 8. Check Yourself

1. What four things must a confirmation prompt show?
2. Why is a near-zero denial rate a warning sign?
3. What is wrong with an unscoped "always allow"?
4. Why must an unanswered prompt time out as a denial?
