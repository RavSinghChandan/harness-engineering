# Harness Engineering — Module 3
# Topic: Tool Testing

---

## 1. Intuition

Tools are the part of an agent you can test like ordinary software. They are
plain functions with typed inputs and string outputs, and they are also the part
that actually touches the world.

Yet most agent codebases test the prompt and not the tools — which is backwards.
The prompt is the part you *cannot* test deterministically. The tools are the
part you can.

---

## 2. Core Concept

### Four layers, cheapest first

| Layer | Tests | Needs a model? | Speed |
|---|---|---|---|
| Unit | The function's logic | No | ms |
| Contract | Schema, errors, effect | No | ms |
| Integration | Real dependency | No | seconds |
| Loop | Model picks it correctly | Yes | seconds, costs money |

Most teams write only the last one. Most bugs live in the first two.

### The contract tests every tool needs

These are the same for every tool, so write them once as a shared suite:

```python
def assert_tool_contract(tool: Tool) -> None:
    # 1. It has a schema, and the schema is valid.
    schema = tool.schema()
    assert schema["name"] and schema["description"]

    # 2. Every parameter is documented.
    for param in inspect.signature(tool.run).parameters:
        assert param in schema["input_schema"]["properties"], f"undocumented: {param}"

    # 3. It declares an effect explicitly.
    assert tool.effect in Effect, f"{tool.name} has no declared effect"

    # 4. Bad input returns an error string, never an exception.
    result = tool.run_safely(**{})          # missing required args
    assert isinstance(result, str)
    assert result.startswith("Error")

    # 5. The error tells the model what to do next.
    assert len(result) > 20, "error message is not actionable"
```

Point 4 is the one that bites in production. A tool that raises takes the whole
loop down; a tool that returns `"Error: order_id is required"` lets the model
correct itself on the next turn.

### Testing the error paths

Errors are what the model sees most often when something is wrong, so they
deserve more test coverage than the happy path:

```python
@pytest.mark.parametrize("bad_id,expected", [
    ("",         "must not be empty"),
    ("not-a-id", "format"),
    ("ORD-9999", "not found"),
])
def test_get_order_errors_are_actionable(bad_id, expected):
    result = get_order.run_safely(order_id=bad_id)
    assert result.startswith("Error")
    assert expected in result.lower()
```

Each message must tell the model something it can act on. "Error: invalid input"
teaches it nothing and it will retry the same call.

### Testing effects

A tool declared `READ` must not write. That is testable:

```python
def test_search_orders_is_read_only(tmp_path, db_snapshot):
    before = db_snapshot()
    search_orders.run(query="widgets")
    assert db_snapshot() == before, "READ tool mutated state"
```

Run it for every `READ` tool. A mis-declared effect defeats the entire
permission layer — the guard is only as honest as the label.

---

## 3. Golden Tests for Selection

Loop-level tests are slow and cost money, so keep them small and targeted at
selection, not at output text:

```python
GOLDEN = [
    ("What is order ORD-1234?",        "get_order"),
    ("Find my orders from last week",  "search_orders"),
    ("Cancel ORD-1234",                "cancel_order"),
]

@pytest.mark.parametrize("task,expected_tool", GOLDEN)
def test_model_picks_the_right_tool(task, expected_tool):
    trace = harness.run(task, max_turns=1)
    assert trace.tool_calls[0].name == expected_tool
```

Assert on the *tool chosen*, never on the wording of the answer. Wording varies
between runs and between model versions; the choice of tool is the thing you
actually care about, and it is far more stable.

---

## 4. Fakes Over Mocks

Prefer a small in-memory implementation to a mock library:

```python
class FakeOrderStore:
    """Behaves like the real store, in a dict."""

    def __init__(self, orders: dict | None = None):
        self.orders = orders or {}
        self.writes: list[tuple[str, dict]] = []      # assertions hang off this

    def get(self, order_id: str) -> dict | None:
        return self.orders.get(order_id)

    def cancel(self, order_id: str) -> None:
        if order_id not in self.orders:
            raise KeyError(order_id)
        self.orders[order_id]["status"] = "cancelled"
        self.writes.append(("cancel", {"order_id": order_id}))
```

A fake survives refactors; a mock asserts on call shapes that change every time
you touch the code. And `self.writes` gives you a clean way to assert that a
run did exactly the writes you expected — no more, no fewer.

---

## 5. Trade-offs

**Loop tests are flaky by nature.** The model is non-deterministic. Keep the set
small, assert on selection, and accept the occasional re-run rather than
weakening the assertion into meaninglessness.

**Fakes drift from reality.** Run the integration layer against the real
dependency nightly, so drift shows up on a schedule rather than in production.

**Contract tests feel like boilerplate.** They are — which is why they should be
one shared function applied to every tool, not copied per tool.

---

## 6. Production Notes

- **Run `assert_tool_contract` over the whole registry** in CI, parametrised, so
  a new tool cannot merge without a schema, an effect and safe errors.
- **Test effect honesty** for every `READ` tool. It is the foundation the
  permission layer stands on.
- **Keep golden selection tests under twenty.** They are the slow, expensive
  layer; they exist to catch a regression, not to prove correctness.
- **Record real failing calls as test cases.** Every production tool error is a
  test you did not have.

---

## 7. What To Say Out Loud

> "Tools are the testable part of an agent, so that is where the tests go. Every
> tool gets a shared contract suite: valid schema, documented parameters, a
> declared effect, and bad input returning an error string rather than raising —
> because a raise takes the loop down while an error string lets the model
> correct itself. I test effect honesty explicitly, since a `READ` tool that
> writes defeats the permission layer. Loop-level tests exist too, but they
> assert on which tool was chosen, never on the wording, because wording changes
> between model versions and the choice does not."

---

## 8. Check Yourself

1. Why must a tool return an error string rather than raising?
2. Why test that a `READ` tool does not write?
3. Why assert on tool choice rather than answer text?
4. Why prefer a fake over a mock here?

→ Next: [`../04-context-engineering/context-window-budgeting.md`](../04-context-engineering/context-window-budgeting.md)
