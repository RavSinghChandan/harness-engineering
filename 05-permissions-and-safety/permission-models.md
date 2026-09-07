# Harness Engineering — Module 5
# Topic: Permission Models

> **F6 — excess authority — is the worst failure in the taxonomy.** Deleted data
> stays deleted. Read this module before you ship anything that writes.

---

## 1. Intuition

Your agent has an API key. That key can do everything the key can do — not
everything you *intended* it to do. If the key can drop a table, then your agent
can drop a table, and the only thing standing between a user's data and an
unlucky sampling of the model is a sentence in a system prompt.

That is not a control. A permission model is.

---

## 2. Core Concept

### Three questions, always in this order

```
  1. AUTHENTICATION   who is this?           → identity
  2. AUTHORISATION    may they do this?      → policy
  3. CONFIRMATION     should we ask first?   → human judgement
```

Most teams do (1) and skip straight to executing. The interesting work is in
(2) and (3).

### The four permission models

**A. Allow-list (default deny)**
Nothing is permitted unless named. Safest, most tedious, correct for anything
touching money or user data.

**B. Deny-list (default allow)**
Everything permitted except named exceptions. Convenient and *wrong* for
security, because you cannot enumerate every dangerous action in advance.

**C. Capability-based**
The agent holds tokens that *are* the permission. It cannot ask for what it does
not hold. Elegant, and the natural fit for subagents.

**D. Graduated / mode-based**
Permission depends on a mode the user chose: read-only, ask-first, autonomous.
This is what real coding agents use, because the right answer genuinely differs
between a demo and a trusted repo.

### Choosing

| Situation | Model |
|---|---|
| Anything financial or destructive | **Allow-list** |
| Internal dev tool on a scratch repo | Deny-list is acceptable |
| Subagent doing a narrow task | **Capability** — hand it only what it needs |
| A product with varied user trust | **Graduated** |

---

## 3. Minimal Implementation

A policy layer that is small enough to audit and strict enough to trust:

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable


class Effect(str, Enum):
    """What a tool does to the world. This drives every policy decision."""
    READ = "read"            # safe, reversible, idempotent
    WRITE = "write"          # changes state, usually reversible
    DESTRUCTIVE = "destroy"  # irreversible: delete, refund, send, deploy


class Mode(str, Enum):
    READ_ONLY = "read_only"   # reads only; everything else denied
    ASK_FIRST = "ask_first"   # writes need confirmation (sensible default)
    AUTONOMOUS = "autonomous" # writes allowed; destruction still confirmed


@dataclass(frozen=True)
class Verdict:
    allowed: bool
    reason: str = ""
    needs_confirmation: bool = False


@dataclass
class Policy:
    mode: Mode = Mode.ASK_FIRST
    allowed_tools: frozenset[str] | None = None   # None = all registered tools
    confirm: Callable[[str, dict], bool] = lambda name, args: False

    def check(self, name: str, effect: Effect, args: dict) -> Verdict:
        # 1. Allow-list first. If it is not named, it does not run.
        if self.allowed_tools is not None and name not in self.allowed_tools:
            return Verdict(False, f"Tool {name!r} is not permitted in this session.")

        # 2. Reads are always fine. This is what makes strict modes usable.
        if effect is Effect.READ:
            return Verdict(True)

        # 3. Mode decides the rest.
        if self.mode is Mode.READ_ONLY:
            return Verdict(False, f"{name!r} modifies state; session is read-only.")

        needs_ask = (
            effect is Effect.DESTRUCTIVE          # always confirm destruction
            or self.mode is Mode.ASK_FIRST        # ask-first confirms writes too
        )
        if needs_ask and not self.confirm(name, args):
            return Verdict(False, "The user declined this action.",
                           needs_confirmation=True)

        return Verdict(True)
```

Three properties make this trustworthy:

- **Default deny** — an unknown tool is refused, not permitted.
- **Destruction always confirms**, even in autonomous mode. There is no
  configuration that lets an agent delete silently.
- **Reads are free**, so the strict modes remain genuinely useful rather than
  being switched off out of frustration.

### Wiring it into the loop

```python
verdict = self.policy.check(call.name, tool.effect, call.arguments)
if not verdict.allowed:
    # A denial is information for the model, not an exception.
    return ToolResult.denied(call, verdict.reason)
return tool.run(**call.arguments)
```

Returning the denial as a message lets the agent explain itself to the user:
*"I can't delete that file because this session is read-only."* Raising would
just end the run with a stack trace.

---

## 4. The Confirmation Trap

Confirmation only works if the human can actually judge. These are bad:

```
"Allow tool call?"                          ← allow WHAT?
"Run bash command?"                         ← which command?
"Agent wants file access. Allow?"           ← which file? read or write?
```

This is good:

```
Delete 3 files?
  /workspace/old_report.pdf
  /workspace/draft_v1.md
  /workspace/notes.txt
This cannot be undone.                      [Allow]  [Deny]
```

Show the **exact action, the exact target, and the reversibility**. A user who
clicks "allow" on a vague prompt has not consented to anything.

Two more rules:

- **Never make deny the scary option.** If denying breaks the session, users
  learn to always allow, and your permission system is decorative.
- **Beware "always allow".** Convenient, and it silently converts ask-first into
  autonomous. If you offer it, scope it to the exact tool *and* argument shape.

---

## 5. Trade-offs

**Security vs. usability.** Every prompt is friction. Too many and users click
through blindly — worse than not asking. Confirm on *effect*, not on every call.

**Static vs. dynamic policy.** Static (a frozen allow-list) is auditable.
Dynamic (an LLM judging risk) is flexible and introduces a model into your
security boundary, which means it can be talked out of it. Prefer static for
anything irreversible.

**Coarse vs. fine grain.** `file_write` is easy to reason about;
`file_write_to_workspace_only_under_10mb` is precise and unmaintainable. Start
coarse; split a tool when a real incident demands it.

---

## 6. Production Notes

- **Log every denial.** A spike in denials is either an attack or a UX problem,
  and both matter.
- **Test the denials, not just the approvals.** Most permission bugs are a path
  that skips the check entirely.
- Put the check in **one place**, on the hot path of tool execution. Scattered
  checks always grow a hole.
- Give **subagents strictly fewer** permissions than the parent. A subagent
  summarising a file has no reason to hold write access.
- The policy object should be **immutable during a run**. A policy the agent can
  modify is not a policy.

---

## 7. What To Say Out Loud

> "I model permissions on effect, not on tool name: read, write, destructive.
> Reads are free, writes depend on the session mode, and destructive actions
> always confirm — there is no configuration that lets the agent delete
> silently. It is default-deny with an allow-list, because you cannot enumerate
> every dangerous action in advance. Denials come back as messages rather than
> exceptions so the agent can explain itself to the user. And confirmation
> prompts must show the exact target and whether it is reversible — a vague
> 'allow tool call?' trains users to click yes, which is worse than not asking."

---

## 8. Check Yourself

1. Why is deny-list the wrong default for security?
2. Why do destructive actions confirm even in autonomous mode?
3. What is wrong with "Allow tool call?" as a prompt?
4. Why should a denial be a message rather than a raised exception?

→ Next: [`sandboxing-and-isolation.md`](sandboxing-and-isolation.md)
