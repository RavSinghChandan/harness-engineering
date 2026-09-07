# Harness Engineering — Module 7
# Topic: Delegation and Subagents

> **F12 — delegation drift.** The subagent solves a subtly different problem
> than the one you meant to give it.

---

## 1. Intuition

Delegation is a translation. You hold a rich mental model of the task; you
compress it into a paragraph; the subagent decompresses that paragraph into its
own model. Everything lost in that round trip is drift.

Human teams handle this with clarifying questions. A subagent does not ask. It
proceeds confidently on its interpretation and returns something that looks like
an answer.

So the discipline is: **make the task description carry everything, and make the
return shape too specific to fudge.**

---

## 2. Core Concept

### A delegation contract has five parts

| Part | Without it |
|---|---|
| **Goal** — what "done" means | The subagent stops somewhere arbitrary |
| **Context** — what it needs to know | It re-derives it, badly, or guesses |
| **Constraints** — what it must not do | It exceeds scope |
| **Return shape** — the exact output | You get prose you must re-parse |
| **Budget** — turns and time | It runs until something else stops it |

### Vague versus contracted

```python
# DRIFTS — every part is missing.
delegate("Look into the auth code")
```

What is it looking for? What counts as done? What should it return? Three
different runs give three different shapes of answer.

```python
# CONTRACTED
delegate(
    goal="Find where the session token is validated.",
    context="Python FastAPI service. Auth lives under auth/. "
            "Tokens are JWTs signed with HS256.",
    constraints=[
        "Read only. Do not modify any file.",
        "Search auth/ first; do not read the test suite.",
    ],
    returns={
        "file": "path to the file",
        "function": "name of the validating function",
        "line": "line number as an integer",
        "confidence": "high | medium | low",
    },
    max_turns=8,
)
```

The `returns` shape is the part people skip, and it is the one that removes most
drift. A structured return either matches or obviously does not — prose always
*looks* plausible.

### Verify what comes back

The supervisor must not trust the subagent's word:

```python
result = delegate(...)

if result.get("confidence") == "low":
    return self.investigate_directly(task)      # do it yourself

if not Path(result["file"]).exists():           # cheap objective check
    return self.redelegate(task, note=f"{result['file']} does not exist")
```

Cheap verification beats elaborate prompting. If the subagent claims a file and
the file is not there, you know immediately.

---

## 3. Minimal Implementation

```python
import json
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Contract:
    """A delegation, written so it cannot be interpreted loosely."""

    goal: str
    context: str = ""
    constraints: tuple[str, ...] = ()
    returns: dict[str, str] = field(default_factory=dict)
    max_turns: int = 8
    tools: tuple[str, ...] = ()

    def as_prompt(self) -> str:
        parts = [f"GOAL: {self.goal}"]
        if self.context:
            parts.append(f"CONTEXT: {self.context}")
        if self.constraints:
            listed = "\n".join(f"- {c}" for c in self.constraints)
            parts.append(f"CONSTRAINTS:\n{listed}")
        if self.returns:
            shape = json.dumps(self.returns, indent=2)
            parts.append(
                "RETURN exactly this JSON shape and nothing else:\n" + shape
            )
        parts.append(
            f"You have {self.max_turns} turns. If you cannot complete the goal, "
            'return the shape with confidence "low" and say what is missing.'
        )
        return "\n\n".join(parts)


@dataclass
class Delegator:
    build_subagent: callable
    max_subagents: int = 5              # hard cap: a fork bomb is F1 x N
    max_depth: int = 2                  # subagents of subagents get unobservable
    spawned: int = 0

    def run(self, contract: Contract, depth: int = 0) -> dict:
        if depth >= self.max_depth:
            return {"error": "delegation depth limit reached", "confidence": "low"}
        if self.spawned >= self.max_subagents:
            return {"error": "subagent limit reached", "confidence": "low"}

        self.spawned += 1
        sub = self.build_subagent(
            tools=contract.tools,           # strictly fewer than the parent
            max_turns=contract.max_turns,
        )
        result = sub.run(contract.as_prompt())

        return self._parse(result.output, contract)

    def _parse(self, output: str, contract: Contract) -> dict:
        """A structured return either matches or obviously does not."""
        if not contract.returns:
            return {"output": output}
        try:
            start, end = output.index("{"), output.rindex("}") + 1
            parsed = json.loads(output[start:end])
        except (ValueError, json.JSONDecodeError):
            return {"error": "subagent did not return the agreed shape",
                    "raw": output[:500], "confidence": "low"}

        missing = set(contract.returns) - set(parsed)
        if missing:
            return {"error": f"missing keys: {sorted(missing)}",
                    "raw": parsed, "confidence": "low"}
        return parsed
```

Note that every failure path returns `confidence: "low"` rather than raising.
The supervisor then has one consistent thing to check.

---

## 4. Trade-offs

**Detailed contracts cost tokens.** A long contract on every delegation adds up.
It is still cheaper than a subagent solving the wrong problem for eight turns.

**Structured returns constrain.** Sometimes the interesting finding does not fit
your schema. Add a free-text `notes` field so nothing valuable is discarded.

**Verification costs time.** Verify what is cheap and objective — a file exists,
a number parses, a test passes. Do not build an elaborate verification agent;
that is another agent to get things wrong.

---

## 5. Production Notes

- **Log the contract and the return together.** Drift is only visible when you
  can see both sides.
- **Track a drift rate**: how often a return fails parsing or verification.
  Rising drift usually means your contracts got vaguer as the code grew.
- **Give subagents read-only tools by default.** Grant writes only when the
  delegation is explicitly about writing.
- **Attribute subagent cost to the parent run**, or your unit economics lie.
- **Time-box everything.** A hung subagent hangs the parent, and the parent's
  user sees an unexplained stall.

---

## 6. What To Say Out Loud

> "Delegation is a lossy translation: I compress a rich mental model into a
> paragraph and the subagent decompresses it into its own. It never asks a
> clarifying question, so the contract has to carry everything — goal, context,
> constraints, the exact return shape, and a budget. The return shape does most
> of the work, because structured output either matches or obviously does not,
> whereas prose always looks plausible. Then the supervisor verifies cheaply
> rather than trusting: if the subagent names a file, I check the file exists.
> And every failure path returns low confidence rather than raising, so the
> supervisor has one consistent thing to check."

---

## 7. Check Yourself

1. What are the five parts of a delegation contract?
2. Why does a structured return reduce drift more than a better prompt?
3. Why do failures return `confidence: low` instead of raising?
4. Why default subagents to read-only tools?

→ Next module: [`../08-production-harness/deployment-shapes.md`](../08-production-harness/deployment-shapes.md)
