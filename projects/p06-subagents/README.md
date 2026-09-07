# P06 — Subagents

**Builds:** delegation contracts, context isolation, verified structured returns.
**Prevents:** F12 (delegation drift), and capped fan-out prevents F1 with a multiplier.
**Read first:** [`07-multi-agent-harness/when-multi-agent-helps.md`](../../07-multi-agent-harness/when-multi-agent-helps.md) and [`delegation-and-subagents.md`](../../07-multi-agent-harness/delegation-and-subagents.md)

---

## Run it

```bash
cd projects/p06-subagents
python -m pytest tests/ -q      # 14 tests
```

---

## The contract does the work

A subagent never asks a clarifying question. So the contract carries everything:

```python
Contract(
    goal="Find where the session token is validated.",
    context="Python FastAPI service. Auth lives under auth/.",
    constraints=("Read only. Do not modify any file.",),
    returns={"file": "path", "function": "name", "confidence": "high|medium|low"},
    tools=("read_file", "search"),
    max_turns=8,
)
```

`returns` is the part people skip and the one that removes most drift:

```python
def test_prose_instead_of_json_is_caught():
    """Prose always looks plausible. Structure either matches or does not."""
```

A prose answer *sounds* like a finding. A structured return either has the keys
or it does not, and the test asserts the missing ones are named.

---

## Isolation is enforced, not requested

```python
sub = self.build_subagent(
    tools=contract.tools,        # strictly fewer than the parent holds
    max_turns=contract.max_turns,
)
```

A subagent is a **reduction** of the parent's authority, never an expansion. A
test captures what the subagent was actually constructed with, so this cannot
quietly regress.

---

## Failure has one shape

Every failure path returns `confidence: "low"` rather than raising:

| Situation | Result |
|---|---|
| Returned prose | `usable=False`, "did not return the agreed shape" |
| Missing keys | `usable=False`, keys named |
| Subagent unsure | `usable=False` |
| Depth cap hit | `usable=False` |
| Fan-out cap hit | `usable=False` |

The supervisor checks `result.usable` and nothing else. One consistent thing to
check beats five exception types.

---

## Caps are hard

```python
max_subagents: int = 5
max_depth: int = 2
```

A delegation loop without caps is a fork bomb — F1 multiplied. A parametrised
test covers each depth level, and another proves the fan-out cap trips.

---

## Exercises

1. **Parallel delegation.** Run three contracts concurrently with `asyncio`.
   Which parts of `Delegator` need locking, and why is `spawned` the dangerous one?
2. **Verification.** After a return names a file, check it exists before
   accepting. Where does that belong — in `Delegator` or the supervisor?
3. **Cost attribution.** Add subagent cost to the parent's trace from P05. What
   breaks in your unit economics if you skip this?
4. **Re-delegation.** On low confidence, retry once with the error appended to
   the context. What stops that becoming a loop?

→ Next: [`p07-durable-runs`](../p07-durable-runs/) — surviving a restart.
