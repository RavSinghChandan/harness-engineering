# Harness Engineering — Module 10
# Topic: The Failure Story Framework

---

## 1. Why This Is The Question

"Tell me about a time an agent failed in production" separates people who have
shipped from people who have read.

Anyone can describe an architecture. Only someone who has operated one can say
what the symptom looked like at 2am, why the obvious explanation was wrong, and
what they changed so it could not recur. That is what the question is really
testing.

The trap is that most people answer with a *bug* — "the model hallucinated a
field name" — which is a story about the model, not about engineering. A good
failure story is about a gap in the harness.

---

## 2. The Structure

Six beats, roughly four minutes.

**1. Context (20 seconds).** What the agent did, who used it, what was at stake.
Enough to make the stakes real; no more.

> "A support agent handling refunds and order lookups. About two thousand runs a
> day, customer-facing."

**2. Symptom (20 seconds).** What was *observed*, not what was wrong. Symptoms
are what you actually had at the time.

> "Cost per run tripled over a week. No errors, no complaints, nothing in the
> dashboards except spend."

**3. Investigation (60 seconds).** How you narrowed it. This is the longest beat
and the most revealing, because it shows how you think. Include the wrong turn.

> "I assumed a traffic spike — volume was flat. Then a model price change — no.
> The stop-reason chart showed completed runs steady but p95 turns up from six to
> twenty-two, so a tail of runs was looping. Pulling one trace, the agent searched
> the knowledge base eleven times with slightly different queries, getting
> overlapping results each time and never enough to answer."

**4. Root cause (30 seconds).** Name the harness gap, not the model's mistake.

> "Two gaps. The retrieval tool had no session-level deduplication, so the same
> chunks came back repeatedly and the context filled with near-duplicates. And
> there was no no-progress detector — the loop happily ran twenty turns as long
> as each turn returned something."

**5. Fix (45 seconds).** What you changed, in layers — immediate, then
structural.

> "Immediately, a per-run retrieval budget: after five searches the tool returns
> 'budget exhausted, answer with what you have or say what is missing'. Then
> session-wide dedup, with an explicit 'no new results' message so the agent can
> tell it is stuck. Structurally, a no-progress detector — if three consecutive
> turns produce no new information, stop. And an alert on p95 turns week over
> week, because that number moved days before the cost did."

**6. What it taught you (20 seconds).** Generalise to a principle.

> "Silent degradation is the dangerous kind. Nothing errored, users got answers,
> and the only symptom was money. Since then every loop has a progress condition,
> not just a turn cap — 'is it still making progress' is a different question from
> 'has it done too many turns', and only the first one catches this."

---

## 3. What Makes It Land

**Specific numbers.** "Cost tripled", "p95 from six to twenty-two", "eleven
searches". Vague stories sound invented, because invented stories are vague.

**A wrong turn.** Real investigations have them. Including one is the strongest
authenticity signal you have, and it costs you nothing — nobody expects the first
hypothesis to be right.

**A harness root cause.** "The model looped" is the symptom. "The loop had no
progress condition" is the cause. The second says you understand where the
guarantee should have lived.

**Layered fixes.** Immediate mitigation, then structural change, then detection.
That sequence is what operating a system actually looks like.

**Detection at the end.** "And an alert on p95 turns" is the beat that shows you
thought about the *next* failure, not just this one.

---

## 4. What Sinks It

| Anti-pattern | Why it fails |
|---|---|
| Blaming the model | Models are non-deterministic; that is the premise, not the finding |
| "We improved the prompt" | Prompts are suggestions. What is the guarantee? |
| No numbers | Sounds invented |
| Everything went perfectly | Nobody's investigation is clean |
| No detection change | You fixed one instance, not the class |
| A trivial failure | A typo in a schema is not a story |

The prompt-fix answer is the most common and the most damaging, because it says
you would fix the next incident the same non-binding way.

---

## 5. Three Stories Worth Preparing

Have one for each of the big categories, so you can match the interviewer's
interest:

**A cost story (F9).** Silent, discovered late, fixed with budgets and rate
alerts. Good for platform and infrastructure roles.

**A safety story (F6/F7).** An agent did something it should not have been able
to do, or failed silently and someone acted on a wrong answer. Fixed with an
effect model and structural status. Good for anything customer-facing or
regulated.

**A correctness story (F4/F5).** Context overflow or poisoning — the agent lost a
constraint after compaction, or an injected instruction from a tool result
changed its behaviour. Fixed with structured state or capability removal. Good
for research and RAG-heavy roles.

If you have not had a production failure of your own, tell a project story
honestly framed: "in a system I built, I introduced this failure deliberately to
see what would happen, and here is what I found." That is not weaker than a real
one — it is a person who tested their own system, which is rarer than it should
be.

---

## 6. The Compressed Version

Some interviewers want two minutes, not four. Have this ready:

> "Cost per run tripled in a week with no errors and no complaints. The
> stop-reason chart showed p95 turns up from six to twenty-two, so a tail of runs
> was looping — retrieval with no session-level dedup, returning the same chunks
> repeatedly, and no no-progress detector, so the loop kept going because each
> turn returned *something*. I added a retrieval budget and session-wide dedup
> with an explicit 'no new results' message, then a no-progress detector, then an
> alert on p95 turns. The lesson is that a turn cap is not a progress condition —
> and silent degradation is the dangerous kind, because the only symptom was
> money."

---

## 7. Check Yourself

1. What are the six beats, in order?
2. Why include a wrong turn in the investigation?
3. Why is "we improved the prompt" a damaging answer?
4. Which three story categories should you have prepared, and why three?

→ Next: [`whiteboard-a-harness.md`](whiteboard-a-harness.md)
