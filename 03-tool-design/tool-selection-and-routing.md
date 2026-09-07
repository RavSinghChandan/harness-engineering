# Harness Engineering — Module 3
# Topic: Tool Selection and Routing

---

## 1. Intuition

With five tools, a model picks correctly almost always. With forty, it starts
confusing similar ones, and every schema is sitting in context on every call,
costing tokens.

The instinct is to write better descriptions. Past a certain point that stops
working, because the problem is not clarity — it is the **number of choices**.

---

## 2. Core Concept

### Accuracy against tool count

| Tools | Selection quality |
|---|---|
| 1–5 | Essentially reliable |
| 6–15 | Good with distinct names |
| 16–30 | Errors climb; overlapping tools confused |
| 30+ | Needs routing |

### Three ways to shrink the choice

**1. Merge overlapping tools.** If `search_orders`, `find_order` and
`lookup_order_by_date` exist, that is one tool with parameters. Overlap is worse
than breadth, because the model must guess an intent distinction you invented.

**2. Route before the loop.** A cheap first call narrows the task type, and only
that category's tools are offered:

```python
category = classify(task)                       # cheap model, 4 options
tools = REGISTRY.for_category(category)         # 5 tools instead of 40
```

**3. Progressive disclosure.** Start with a small set plus a discovery tool:

```python
def list_capabilities(area: str) -> str:
    """Describe tools available for an area: billing, shipping, accounts."""
```

The agent asks for what it needs. Costs a turn, saves thousands of schema tokens
per call on a long run.

### Naming is most of it

| Weak | Better | Why |
|---|---|---|
| `get_data` | `get_order_by_id` | Says what and how |
| `search` | `search_orders` | Says the domain |
| `process` | `issue_refund` | Says the effect |
| `handle_request` | — | Delete it; it means nothing |

And one sentence of disambiguation in each description does more than paragraphs
of prose:

> "Use this when the user knows the order ID. For a text search, use
> `search_orders` instead."

---

## 3. Minimal Implementation

```python
from dataclasses import dataclass, field


@dataclass
class RoutedRegistry:
    """Only the relevant tools reach the model's context."""

    categories: dict[str, list[Tool]] = field(default_factory=dict)
    always: list[Tool] = field(default_factory=list)   # e.g. escalate_to_human

    def register(self, category: str, tool: Tool) -> None:
        self.categories.setdefault(category, []).append(tool)

    def for_task(self, category: str) -> list[Tool]:
        return self.always + self.categories.get(category, [])

    def schemas_for(self, category: str) -> list[dict]:
        return [t.schema() for t in self.for_task(category)]

    def discovery_tool(self) -> Tool:
        def list_capabilities(area: str) -> str:
            """List the tools available in an area. Areas: {areas}."""
            tools = self.categories.get(area, [])
            if not tools:
                return f"No area {area!r}. Available: {', '.join(sorted(self.categories))}."
            return "\n".join(f"{t.name}: {t.description}" for t in tools)

        list_capabilities.__doc__ = list_capabilities.__doc__.format(
            areas=", ".join(sorted(self.categories))
        )
        return Tool(name="list_capabilities", run=list_capabilities, effect=Effect.READ)
```

`always` matters: escalation and completion tools must be reachable from every
category, or a routed agent can get stuck with no way out.

---

## 4. Diagnosing Bad Selection

When the model picks wrongly, work through this in order:

1. **Are two tools genuinely overlapping?** Merge them.
2. **Does the description say when *not* to use it?** Add the sentence.
3. **Is the name domain-specific?** `search` → `search_orders`.
4. **Are there simply too many?** Route.

Do not jump to routing. Steps 1–3 are cheaper and usually enough below thirty
tools.

---

## 5. Trade-offs

**Routing adds a call.** One cheap classification per run, plus the risk of
routing wrongly and hiding the tool that was needed. Always include an escape
hatch.

**Progressive disclosure costs turns.** Discovery is one turn every time. Good
for long runs, poor for short ones.

**Merged tools grow parameters.** One tool with eight parameters can be as
confusing as eight tools. Merge on *user intent*, not on convenience.

---

## 6. Production Notes

- **Log which tool was chosen against which was correct** where you can tell.
  That confusion matrix points straight at the overlapping pair.
- **Measure schema tokens per call.** Forty tools with paragraph descriptions is
  a real line on the bill.
- **Always keep an escape hatch** in `always` — the agent must be able to
  escalate from any category.
- **Test routing with real tasks**, not invented ones. Real requests are messier
  and route worse.

---

## 7. What To Say Out Loud

> "Selection accuracy degrades with tool count, so past about twenty I stop
> writing better descriptions and start reducing choices. First I merge
> overlapping tools, because overlap is worse than breadth — the model has to
> guess a distinction I invented. Then names get domain-specific and each
> description says when *not* to use it, which fixes most confusion in one
> sentence. Only then do I route: a cheap classification narrows to one
> category's tools, with escalation always available so a mis-route cannot
> strand the agent."

---

## 8. Check Yourself

1. Why is overlap worse than breadth?
2. What is the one sentence that fixes most selection errors?
3. What must always be in the `always` list, and why?
4. When is progressive disclosure a bad trade?

→ Next: [`dangerous-tools-and-confirmation.md`](dangerous-tools-and-confirmation.md)
