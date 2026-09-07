# P03 — Context Manager

**Builds:** token budgeting, deliberate assembly, and compaction.
**Prevents:** F4 (context overflow), F9 (cost blowout).
**Read first:** [`04-context-and-memory/context-assembly.md`](../../04-context-and-memory/context-assembly.md) and [`compaction-and-summarisation.md`](../../04-context-and-memory/compaction-and-summarisation.md)

---

## Run it

```bash
cd projects/p03-context-manager
python -m pytest tests/ -q      # 18 tests
```

---

## What is here

```
minihar/context.py     ContextBudget, ContextAssembler — the deliberate build
minihar/compaction.py  Compactor — summarise the middle, protect both ends
tests/                 18 tests
```

---

## Order is not aesthetic

```
system → memory → retrieved → history → current
```

Two reasons, both costly to get wrong:

**Caching.** Providers cache a prompt *prefix*. The system prompt must be
byte-identical every turn or you pay full price on every call. Put a timestamp
in there and you have quietly multiplied your bill.

**Attention.** Models attend most reliably to the start and end of context — the
middle is where things get lost. So the brief goes first and the immediate ask
goes last. A test pins each of these.

---

## Whole messages, never partial

```python
if used + cost > limit:
    self.dropped.append(message["content"][:60])
    continue                      # drop it entirely
```

Half a tool result is worse than none, because the model reasons over a sentence
that stops mid-clause and does so confidently. The test asserts every kept
message is intact:

```python
assert m["content"] == "x" * 800, "a kept message must be whole"
```

Dropped messages are recorded, because "why did it forget?" is a question you
will be asked.

---

## Compaction protects both ends

```python
head = messages[:2]                      # system + task: never summarised
recent = messages[-keep_recent:]         # newest turns: verbatim
middle = ...                             # only this is compressed
```

That the system prompt and original task survive is **structural**, not a hope
expressed in a prompt. A test asserts it directly.

Triggering happens at **75% of the window**, not 100% — compaction sends the old
transcript to a model, so it needs room to run.

The summary text is **logged**. When an agent forgets something, the summary is
the first thing you need to read, and it is gone forever if you did not keep it.

---

## The honest cost

Compaction is lossy in a specific shape: exact quotes vanish, numbers drift. The
mitigation is not a better prompt — it is **not needing the detail in context**.
Persist important artefacts to files and let the summary reference them by name.

---

## Exercises

1. **Relevance over recency.** History currently keeps the newest that fit. Rank
   by relevance to the current question instead. What does that cost per turn?
2. **A real tokeniser.** Swap `rough_tokens` for `tiktoken`. How far off was the
   4-chars-per-token estimate on your own transcripts?
3. **Compaction of compactions.** Compact twice on one transcript. What is lost
   the second time, and what would you keep outside context to prevent it?
4. **Wire it to P01.** Call `assemble` at the top of the loop and `compact` when
   `needs_compaction` is true. Which of P01's tests still pass?

→ Next: [`p05-observability`](../p05-observability/) — knowing what happened.
