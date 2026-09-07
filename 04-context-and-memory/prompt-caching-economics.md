# Harness Engineering — Module 4
# Topic: Prompt Caching Economics

---

## 1. Intuition

An agent re-sends its entire context on every turn. Turn ten sends the system
prompt, the tool schemas and nine turns of history — again. A twenty-turn run
can send the same system prompt twenty times.

Prompt caching makes those repeats cheap. But it only works if the repeated part
is **byte-identical and at the front**, and that constraint quietly dictates how
you must order your prompt.

---

## 2. Core Concept

### How the cache works

The provider caches a *prefix* of your prompt. On the next call it compares from
the start; everything that matches is served from cache at a large discount,
and the first byte that differs invalidates everything after it.

So the ordering rule is simple and absolute:

> **Stable content first. Volatile content last.**

### The ordering that follows

```
1. System prompt              — same every call
2. Tool schemas               — same every call
3. Persistent memory          — changes rarely
4. Session state              — changes each turn
5. Message history            — grows each turn
6. Current turn               — always new
```

Anything above the first change is cached. Put a timestamp in the system prompt
and you have moved the first change to position one — the cache never hits, and
you pay full price for the whole prompt on every turn.

### The mistakes that break it

| Mistake | Effect |
|---|---|
| Timestamp in the system prompt | Cache never hits, ever |
| Tool schemas sorted by a dict order that varies | Random misses |
| Memory rendered before tool schemas | Memory change invalidates schemas |
| Random ids or a session uuid in the preamble | Cache never hits |
| Re-summarising history on every turn | Invalidates from the summary onward |

The last one is subtle. Compaction rewrites earlier history, which sits *before*
the recent turns, so it invalidates almost the whole prefix. Compaction is worth
it anyway — but expect one expensive turn afterwards, and do not compact more
often than you need to.

### The arithmetic

Take a 20-turn run with a 6,000-token stable prefix, at $3 per million input
tokens and cached reads at 10% of that:

- **No caching:** 20 × 6,000 = 120,000 tokens ≈ **$0.36**
- **With caching:** 6,000 full + 19 × 6,000 at 10% ≈ 17,400 effective ≈ **$0.05**

Roughly 85% off the stable part, for a change in *ordering*. That is the highest
return per line of code anywhere in a harness.

---

## 3. Minimal Implementation

```python
class CacheFriendlyPrompt:
    """Assembles the prompt in strict stability order."""

    def build(self, state: SessionState, history: list[Message]) -> list[dict]:
        blocks = []

        # --- Stable prefix: identical bytes on every call ---
        blocks.append({
            "type": "text",
            "text": self.system_prompt,
            "cache_control": {"type": "ephemeral"},      # cache breakpoint here
        })
        blocks.append({
            "type": "text",
            "text": self.render_tools_deterministically(),
            "cache_control": {"type": "ephemeral"},
        })

        # --- Semi-stable: memory, changes between runs not within one ---
        if memory := self.memory.render():
            blocks.append({"type": "text", "text": memory,
                           "cache_control": {"type": "ephemeral"}})

        # --- Volatile: never cached, and that is correct ---
        blocks.append({"type": "text", "text": state.render()})

        return blocks + [m.to_dict() for m in history]

    def render_tools_deterministically(self) -> str:
        """Sorted by name. Never rely on dict insertion order across processes."""
        return "\n\n".join(
            json.dumps(t.schema(), sort_keys=True)
            for t in sorted(self.tools, key=lambda t: t.name)
        )
```

`sorted(...)` and `sort_keys=True` are the whole trick for schemas. A registry
built by decorator order can differ between processes, and then a worker restart
silently halves your cache hit rate with no visible symptom other than the bill.

---

## 4. Measuring It

You cannot tune what you do not measure. Every provider returns cache statistics
on the response — log them per turn:

```python
usage = response.usage
trace.record(
    input_tokens=usage.input_tokens,
    cache_read=getattr(usage, "cache_read_input_tokens", 0),
    cache_write=getattr(usage, "cache_creation_input_tokens", 0),
)

hit_rate = usage.cache_read_input_tokens / max(usage.input_tokens, 1)
if turn > 1 and hit_rate < 0.5:
    log.warning("cache hit rate %.0f%% on turn %d — prefix is unstable", hit_rate * 100, turn)
```

That warning is the alarm you want. A cache regression has no functional symptom
at all; without this line you find out from the invoice at the end of the month.

---

## 5. Trade-offs

**Cache writes cost more than plain input.** Typically around 125%. Caching a
prefix used once is a small loss, so cache what you will reuse — which in an
agent loop is essentially always, since turn two reuses turn one's prefix.

**Caches expire.** Ephemeral caches commonly live around five minutes. An agent
that waits on a slow human approval will find the cache cold on resumption.
That is fine; it is one expensive turn, not a bug.

**Cache-friendly ordering constrains design.** You cannot put "today's date" at
the top, however natural that feels. Put it in the volatile block at the bottom.

---

## 6. Production Notes

- **Order by stability**, always, and put cache breakpoints at the boundaries.
- **Sort tool schemas by name** and serialise with sorted keys.
- **Never put time, random ids or session uuids in the prefix.**
- **Log hit rate per turn and alert below 50%** after turn one.
- **Expect a miss after compaction.** Do not compact more often than the budget
  requires.
- **Re-check hit rate after any prompt change.** Moving one line can cost real
  money and produce no other symptom.

---

## 7. What To Say Out Loud

> "An agent re-sends its whole context every turn, so the prompt is assembled in
> strict stability order: system prompt, tool schemas, memory, session state,
> history. The cache matches a prefix, and the first differing byte invalidates
> everything after it — so a timestamp in the system prompt means the cache never
> hits at all. Tool schemas get sorted by name and serialised with sorted keys,
> because a registry built by decorator order can vary between processes and
> quietly halve the hit rate on a worker restart. I log the hit rate per turn and
> alert below fifty percent, since a cache regression has no functional symptom
> — you find out from the bill."

---

## 8. Check Yourself

1. Why must stable content come first?
2. Why sort tool schemas by name?
3. Why does compaction cause a cache miss?
4. Why alert on hit rate rather than waiting for the invoice?

→ Next: [`../05-permissions-and-safety/permission-models.md`](../05-permissions-and-safety/permission-models.md)
