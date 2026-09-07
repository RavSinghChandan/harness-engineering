# Harness Engineering — Module 4
# Topic: Compaction and Summarisation

> **F4 — context overflow.** The failure that looks like the model getting
> dumber, and is actually you silently dropping its instructions.

---

## 1. Intuition

A long run fills the window. You have three options, and only one is good:

1. **Crash** — the provider rejects the request. Honest, unhelpful.
2. **Truncate** — drop the oldest messages. Cheap, and it silently deletes the
   brief the whole task depends on.
3. **Compact** — replace old detail with a summary that keeps what matters.

Compaction is the interesting one, and the whole game is deciding **what
matters**.

---

## 2. Core Concept

### What must survive compaction

Some things can never be summarised away, no matter how old:

| Keep always | Why |
|---|---|
| The original task | Everything else is in service of it |
| Constraints and preferences | "in Python", "under 500 words", "do not email" |
| Decisions already made | Otherwise the agent redoes or contradicts them |
| Facts discovered | The findings *are* the work |
| Open questions | What is still unresolved |
| The last few turns | Immediate working context |

### What can go

| Safe to compact | Why |
|---|---|
| Full tool outputs | Keep the conclusion, drop the 4,000-line file |
| Failed attempts | Keep "tried X, failed because Y" |
| Intermediate reasoning | The conclusion carries it |
| Pleasantries | No information |

### The shape

```
BEFORE (98k tokens)                AFTER (24k tokens)
┌────────────────────┐             ┌────────────────────┐
│ system             │             │ system             │  unchanged
│ task               │             │ task               │  unchanged
│ turn 1..40 (huge)  │   ──────▶   │ SUMMARY of 1..34   │  compacted
│                    │             │ turn 35..40 (full) │  kept whole
└────────────────────┘             └────────────────────┘
```

Never compact the most recent turns. The agent needs immediate detail to
continue coherently — summarising the last thing it did produces confusion.

---

## 3. Minimal Implementation

```python
COMPACT_PROMPT = """Summarise this portion of an agent's working session.

You MUST preserve, in full:
- the original task and every constraint given
- decisions made and the reason for each
- facts discovered, with their source
- what was tried and failed, and why
- questions still open

You may compress: full file contents, tool output detail, and reasoning that
led to a stated conclusion.

Write in plain prose, third person, under 500 words. Do not add anything that
is not in the transcript."""


@dataclass
class Compactor:
    model: callable
    count_tokens: callable
    keep_recent: int = 6              # turns kept verbatim
    trigger_ratio: float = 0.75       # compact at 75% of window

    def needs_compaction(self, messages, window: int) -> bool:
        used = sum(self.count_tokens(m["content"]) for m in messages)
        return used > window * self.trigger_ratio

    def compact(self, messages: list[dict]) -> list[dict]:
        # The system prompt and original task are never summarised.
        head = messages[:2]
        recent = messages[-self.keep_recent:]
        middle = messages[2:-self.keep_recent]

        if len(middle) < 4:            # not enough to be worth a model call
            return messages

        transcript = "\n\n".join(
            f"[{m['role']}] {m['content']}" for m in middle
        )
        summary = self.model([
            {"role": "system", "content": COMPACT_PROMPT},
            {"role": "user", "content": transcript},
        ]).content

        return [
            *head,
            {"role": "system",
             "content": f"Summary of earlier work in this session:\n{summary}"},
            *recent,
        ]
```

### When to trigger

**At 75%, not at 100%.** Compaction itself needs room — you are sending the old
transcript to a model to summarise it. Wait until the window is full and you
cannot even do that.

---

## 4. What Compaction Costs You

Be honest about this. Compaction is lossy, and the losses have a shape:

- **Exact quotes disappear.** If the agent needs a verbatim string later, it is
  gone. Store those outside context (see memory tiers).
- **Numbers drift.** Summaries round. If precision matters, keep a structured
  scratchpad rather than relying on prose.
- **It costs a model call**, adding latency mid-run at the worst moment.
- **It can summarise away the thing that mattered.** The prompt above is
  defensive for a reason.

The mitigation is not "better prompts". It is **not needing the detail** —
persist important artefacts to files or a store, and let the summary reference
them by name.

---

## 5. Trade-offs

**Compact vs. start fresh.** For genuinely long tasks, finishing one run and
starting another with an explicit handoff document is often cleaner than
repeated compaction. Each compaction compounds the loss of the previous one.

**Model choice for summarising.** A cheap model is tempting and drops more.
Given the summary becomes the agent's entire memory of the session, this is a
poor place to save money.

**Trigger ratio.** Lower means more compactions, more loss, more cost. Higher
risks not having room to compact. 0.7–0.8 is a reasonable band.

---

## 6. Production Notes

- **Log every compaction**: turn number, tokens before and after, and the
  summary itself. When an agent "forgets" something, this is the first place to
  look and you will need the actual summary text.
- **Count compactions per run** as a metric. More than two suggests the task
  should be split.
- **Never compact the system prompt or the original task.** Make that structural
  in the code, not a hope in the prompt.
- **Test with a real long transcript**, not a synthetic one. Real sessions have
  a messy shape that synthetic tests miss.

---

## 7. What To Say Out Loud

> "When the window fills I compact rather than truncate — truncation silently
> drops the original brief and looks like the model getting dumber. I keep the
> system prompt, the task, and the last few turns verbatim, and summarise the
> middle with a prompt that explicitly protects decisions, discovered facts and
> open questions. I trigger at about 75% of the window, because compaction
> itself needs room to run. The honest cost is that it is lossy: exact quotes
> and precise numbers drift. So the real fix is not needing them in context —
> persist important artefacts to files and let the summary reference them."

---

## 8. Check Yourself

1. Why compact at 75% rather than 100%?
2. Name three things that must survive compaction, and why.
3. Why keep the most recent turns verbatim?
4. What is the mitigation for compaction losing exact quotes?

→ Next: [`memory-tiers.md`](memory-tiers.md)
