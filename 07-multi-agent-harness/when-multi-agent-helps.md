# Harness Engineering — Module 7
# Topic: When Multi-Agent Helps

---

## 1. Intuition

Multi-agent systems are the most over-applied idea in this field. The pitch is
seductive: give each agent a role, let them collaborate, and complex problems
solve themselves.

What usually happens is that one agent's slightly-wrong output becomes another
agent's input, the error compounds, and you have built a system that is harder
to debug, more expensive, and no more capable than a single well-equipped agent.

There are two good reasons to use more than one agent. Neither is "roles".

---

## 2. Core Concept

### The two genuine reasons

**1. Context isolation.** A subtask would flood the parent's context with detail
the parent does not need. Reading forty files to find one function is the classic
case: the parent needs the answer, not the forty files.

**2. Parallelism.** Independent subtasks can genuinely run at the same time.
Researching five competitors is five independent jobs.

That is the list. If neither applies, one agent with good tools is better.

### The bad reasons

| "Reason" | What is really going on |
|---|---|
| "Each agent has a specialty" | A system prompt is not a specialty. One agent can adopt any role per call. |
| "It mirrors a real team" | Org charts solve human coordination problems, not model ones. |
| "It sounds more sophisticated" | It is, and that is a cost, not a benefit. |
| "Separation of concerns" | Separate your *tools*, not your agents. |

### The cost you are paying

```
ONE AGENT                      SUPERVISOR + 3 SUBAGENTS
1 context                      4 contexts (each with system prompt + tools)
1 failure point                4 failure points + 3 handoffs
1 transcript to debug          4 transcripts and their interleaving
n tokens                       ~2-4n tokens
```

Handoffs are where the quality goes. Every delegation is a lossy translation:
the supervisor compresses the task into words, the subagent interprets those
words, and the gap between intent and interpretation is F12 (delegation drift).

---

## 3. The Decision

```
Does a subtask produce far more detail than the parent needs?
  YES → subagent for context isolation
  NO  ↓
Are there independent subtasks that could run at the same time?
  YES → parallel subagents
  NO  ↓
Use one agent.
```

### Worked examples

| Task | Shape | Why |
|---|---|---|
| Answer a question from a codebase | **Subagent** | Searching produces huge output; parent needs the answer |
| Research 5 competitors | **Parallel subagents** | Genuinely independent |
| Write a report from 3 sources | **One agent** | The sources are small; it needs all of them anyway |
| "Planner, coder, reviewer" | **One agent** | Same context, no isolation, no parallelism |
| Migrate 40 files the same way | **Parallel subagents** | Independent, and each produces noise |

The "planner / coder / reviewer" pattern is the most common mistake. Those three
roles all need the same context. Splitting them means passing that context
around three times and losing something at each hop.

---

## 4. Minimal Implementation

The shape that is almost always right — a supervisor that delegates *narrow,
noisy* work and keeps the reasoning for itself:

```python
@dataclass
class Supervisor:
    model: Model
    tools: ToolRegistry
    subagent_budget: int = 3            # cap the fan-out

    def delegate(self, task: str, tools: list[str], max_turns: int = 8) -> str:
        """Run a subagent in its own context and return only its conclusion.

        The parent never sees the subagent's transcript. That is the entire
        point -- isolation, not collaboration.
        """
        sub = Harness(
            model=self.model,
            tools=self.tools.subset(tools),       # strictly fewer tools
            policy=self.policy.narrowed(tools),   # strictly fewer permissions
            max_turns=max_turns,
        )
        result = sub.run(task)

        # Only the conclusion crosses the boundary.
        return (
            f"Subagent result for: {task}\n"
            f"Status: {result.stop_reason.value}\n"
            f"{result.output}"
        )
```

Two rules encoded there:

- **Fewer tools, fewer permissions.** A subagent summarising a file has no
  business holding write access. A subagent is a *reduction* of the parent's
  authority, never an expansion.
- **Only the conclusion returns.** If you pass the full transcript back you have
  paid for isolation and thrown it away.

---

## 5. Trade-offs

**Parallel speed vs. cost.** Five subagents finish faster and cost roughly five
times more. Worth it when a human is waiting; wasteful in a batch job.

**Deep vs. flat.** Subagents spawning subagents gets expensive and unobservable
fast. Two levels is a sensible hard limit — enforce it in code, because a
recursive delegation bug is F1 with a multiplier.

**Fresh context vs. shared context.** Fresh is the point, and it means the
subagent lacks background the parent has. Everything it needs must be in the
task description, which is exactly where drift creeps in.

---

## 6. Production Notes

- **Cap fan-out in code.** `max_subagents` per run, hard. Without it one
  delegation loop becomes an unbounded fork bomb.
- **Trace subagents under the parent's `run_id`** with their own `sub_id`.
  Otherwise you cannot reconstruct what happened.
- **Attribute cost to the parent run.** Otherwise your cost-per-run metric lies.
- **Time-box every subagent.** A hung subagent hangs the parent.
- Start with one agent. Split only when you can point at the specific context
  flood or the specific parallelism you are buying.

---

## 7. What To Say Out Loud

> "There are two good reasons for multi-agent: context isolation, where a
> subtask would flood the parent with detail it does not need, and genuine
> parallelism. Roles are not a reason — a system prompt is not a specialty, and
> one agent can adopt any role per call. The cost is real: every delegation is a
> lossy handoff where the supervisor compresses intent into words and the
> subagent interprets them, and that gap is where multi-agent systems fail. So
> my default is one agent with good tools, and I split only when I can name the
> specific flood or the specific parallelism I am buying. When I do split,
> subagents get strictly fewer tools and permissions than the parent, and only
> their conclusion crosses back."

---

## 8. Check Yourself

1. Name the two genuine reasons for multi-agent.
2. Why is "planner, coder, reviewer" usually the wrong split?
3. Why must a subagent hold fewer permissions than its parent?
4. What is lost at every handoff, and what failure does that map to?

→ Next: [`delegation-and-subagents.md`](delegation-and-subagents.md)
