# Harness Engineering — Module 9
# Topic: OpenAI Agents SDK

---

## 1. Intuition

Where LangGraph asks you to draw a graph, the OpenAI Agents SDK asks you to
describe agents and let them hand off to each other. The loop is hidden; you
declare an agent with instructions, tools and handoffs, and call `Runner.run`.

The design bet is that most agent systems are a small set of specialists passing
work between them, and that this is better expressed as a cast of agents than as
a state machine.

---

## 2. What It Actually Gives You

| Harness concern | The SDK's answer |
|---|---|
| Loop control | Hidden inside `Runner`. `max_turns` caps it |
| Tools | `@function_tool` on a typed Python function |
| Multi-agent | First-class handoffs; the model chooses |
| Structured output | `output_type` with a Pydantic model |
| Guardrails | Input and output guardrails that can halt a run |
| Tracing | Built in, on by default |
| Permissions | Guardrails only; no effect model |
| Budgets | `max_turns` only; no cost budget |
| Durability | **Nothing.** No checkpointing |

Guardrails and built-in tracing are the differentiators. The absence of
durability is the biggest gap — a run that dies is gone.

---

## 3. The Shape

```python
from agents import Agent, Runner, function_tool, input_guardrail, GuardrailFunctionOutput


@function_tool
def search_orders(query: str, limit: int = 5) -> str:
    """Search orders by text. Returns ids and summaries."""
    return format_results(store.search(query, limit))


@input_guardrail
async def block_out_of_scope(ctx, agent, user_input: str) -> GuardrailFunctionOutput:
    verdict = await classify(user_input)
    return GuardrailFunctionOutput(
        output_info=verdict,
        tripwire_triggered=verdict.off_topic,      # halts the run
    )


billing = Agent(
    name="Billing",
    instructions="Handle refunds and invoices. Never issue a refund over $100.",
    tools=[search_orders, issue_refund],
)

triage = Agent(
    name="Triage",
    instructions="Route the user to the right specialist.",
    handoffs=[billing, shipping],
    input_guardrails=[block_out_of_scope],
)

result = await Runner.run(triage, "I need a refund for ORD-1234", max_turns=10)
```

Two observations that matter for harness thinking.

**Handoffs are model decisions.** The model chooses which agent to hand to; you
do not route in code. That is convenient and it is also non-deterministic
delegation — the failure mode is F12, delegation drift, and it needs the
structured-handoff discipline from Module 7.

**"Never issue a refund over $100" is a prompt.** It is a suggestion, not a
guarantee. This is the prompt-as-control anti-pattern from Module 1, and the
fix is the same: the limit belongs inside `issue_refund`, in code.

```python
@function_tool
def issue_refund(order_id: str, amount_usd: float) -> str:
    """Issue a refund. Amounts over $100 require human approval."""
    if amount_usd > 100:
        return "Error: refunds over $100 need human approval. Use escalate_to_human."
    ...
```

Now the cap holds regardless of what the model was told.

---

## 4. Guardrails as a Permission Layer

Guardrails are the closest thing the SDK offers to permissions, and they are
worth using — but they are checks on input and output, not on *effects*. There
is no notion of a tool being destructive.

To get a real permission layer, wrap the tools:

```python
def guarded(fn, effect: Effect):
    @function_tool
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        verdict = permissions.check(fn.__name__, effect, kwargs)
        if not verdict.allowed:
            return f"Error: {verdict.reason}"      # the model can adapt
        return fn(*args, **kwargs)
    return wrapper
```

The wrapper is the enforcement point. Every guarantee you need lives there,
because it is the only place the framework cannot route around.

---

## 5. Trade-offs

**No durability.** A crashed run cannot be resumed. If your runs are long or
pause for approval, you must build checkpointing on top, or use a framework that
has it. This is the single biggest reason to pick something else.

**The loop is hidden.** Convenient until you need to change it — inject state
each turn, compact context, apply a custom stopping rule. You are then working
around the framework rather than with it.

**Provider alignment.** It is designed around OpenAI's models and features.
Workable with others; not the happy path.

**Handoffs are non-deterministic.** Useful when routing genuinely depends on
content, a liability when a fixed sequence would do. If the route is knowable in
code, route in code.

---

## 6. When To Choose It

Choose it for **multi-specialist systems with short runs** — customer support
triage, routing to domain agents — where handoffs match the problem and tracing
out of the box saves real setup.

Do not choose it for long runs, runs that pause for human approval, or anything
needing durability. And do not rely on instructions for safety: put every limit
inside the tool.

---

## 7. What To Say Out Loud

> "The Agents SDK models the system as specialists that hand off to each other,
> with the loop hidden inside the runner. Guardrails and built-in tracing are the
> strong parts. The gaps I fill are durability — there is no checkpointing, so a
> crashed run is gone — and permissions, because guardrails check input and
> output but have no concept of a destructive effect. I also never leave a limit
> in the instructions: 'never refund over a hundred dollars' in a prompt is a
> suggestion, so the check goes inside the refund tool where it holds regardless
> of what the model was told."

---

## 8. Check Yourself

1. Why is "never refund over $100" in instructions insufficient?
2. What do guardrails check, and what do they not?
3. What is the biggest gap for long-running agents?
4. When is a model-chosen handoff the wrong design?

→ Next: [`claude-agent-sdk.md`](claude-agent-sdk.md)
