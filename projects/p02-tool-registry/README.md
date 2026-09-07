# P02 — Tool Registry

**Builds:** schemas generated from code, validation, and errors the model can act on.
**Prevents:** F3 (tool misuse) — the failure you will hit most often.
**Read first:** [`03-tool-design/tool-schema-design.md`](../../03-tool-design/tool-schema-design.md) and [`errors-as-feedback.md`](../../03-tool-design/errors-as-feedback.md)

---

## Run it

```bash
cd projects/p02-tool-registry
python -m pytest tests/ -q      # 18 tests
```

---

## What is here

```
minihar/errors.py    ToolError — what failed, why, what we got, what to do
minihar/registry.py  Schema generation from signatures, validation, loop guard
tests/               18 tests asserting message CONTENT, not just failure
```

The tests check what the error *says*, because the words are what the model
acts on. `assert "shipped" in out` is testing the thing that actually matters.

---

## Schemas come from the code

```python
def search_orders(
    query: str,
    max_results: int = 5,
    status: Literal["pending", "shipped", "delivered", "cancelled"] = "pending",
) -> str:
    """Search a customer's past orders.

    Use when the user asks about an order they cannot find. For a specific
    known order ID, use get_order instead.
    """
```

`Literal` becomes an `enum`, so the model **cannot express** an invalid status.
The docstring becomes the description — including the "use X instead" sentence
that fixes most tool-selection errors.

Registering a parameter with no description raises **at registration time**:

```python
raise ValueError(f"{self.name}: parameter {name!r} has no description.")
```

An undescribed parameter is a guaranteed future bug. Better a failed import than
a confused model in production.

---

## Errors that teach

Compare what the model receives:

```
Grade F   "Invalid input"
Grade C   "Error: invalid status 'in-transit'"
Grade A   "Error in search_orders: 'status' must be one of ['pending',
           'shipped', 'delivered', 'cancelled']. Received: 'in-transit'."
```

Grade A can be fixed on the next turn with no human involved. Every validation
path here produces grade A, and a test pins each one.

Errors are also **kinded** — `FIX_AND_RETRY`, `WAIT_AND_RETRY`, `TERMINAL`. A
misspelled tool name is terminal and says *"Do not retry"*, because retrying an
invented tool is pure waste.

---

## The loop guard

Helpful errors create a new problem: the model happily retries something it
cannot fix. So the registry counts errors by `(tool, problem)`:

```python
if self._error_counts[key] >= self.repeat_limit:
    return f"... This has now failed 3 times ... Stop calling this tool."
```

Two tests cover this — that three identical failures trip it, and that
*different* failures do not share a counter.

---

## Exercises

1. **Pattern validation.** `Param(pattern=...)` reaches the schema but is not
   enforced. Add it — and make the error quote the expected format.
2. **Coercion.** `max_results="5"` fails. Should it? Argue both sides, then
   implement whichever you believe, and write the test that proves it.
3. **Too many tools.** Add twenty tools and read the schema token cost. At what
   point would you introduce routing instead of more descriptions?
4. **Wire it to P01.** Replace P01's `tools` dict with this registry. Which of
   P01's tests still pass unchanged?

→ Next: [`p03-context-manager`](../p03-context-manager/) — keeping the run inside the window.
