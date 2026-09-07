# Harness Engineering — Module 6
# Topic: Evaluating Agents

---

## 1. Intuition

Evaluating a chatbot means judging one answer. Evaluating an agent means judging
a *trajectory*: which tools it called, in what order, what it did to the world,
and only then whether the final answer was right.

An agent can produce a perfect answer having deleted a file it should not have
touched. Judge the answer alone and that run passes.

---

## 2. Core Concept

### Three things to evaluate, in order of usefulness

**1. Outcome** — did the world end up in the right state? The strongest signal
and the easiest to check, when the task has a verifiable result:

```python
def check_outcome(task: Task, final_state: dict) -> bool:
    return task.assertion(final_state)      # "order ORD-1234 is cancelled"
```

**2. Trajectory** — did it get there sensibly? Two runs can both succeed while
one took 3 turns and the other 22.

```python
@dataclass
class TrajectoryCheck:
    max_turns: int
    required_tools: set[str]         # must have called these
    forbidden_tools: set[str]        # must NOT have called these
    max_cost_usd: float
```

`forbidden_tools` is the safety half of evaluation, and the one that gets left
out. "Answered correctly and never called `delete_file`" is a stronger pass than
"answered correctly".

**3. Answer quality** — is the text good? Weakest signal, hardest to automate,
and the one everyone starts with. Do it last, on a sample, with a rubric.

### Building an eval set

Twenty real tasks beat two hundred invented ones. Sources, in order of value:

1. **Production failures.** Every incident becomes a permanent test case.
2. **Real user requests**, sampled across the distribution.
3. **Edge cases you know about** — empty results, ambiguity, missing permissions.
4. **Adversarial cases** — injection attempts, impossible requests.

Category 4 is the one that separates a serious eval set from a demo. An agent
should refuse an impossible task rather than fabricate; that is testable:

```python
Task(
    id="impossible-refund",
    prompt="Refund order ORD-0000",           # does not exist
    assertion=lambda s: s["refunds_issued"] == 0,
    trajectory=TrajectoryCheck(
        max_turns=4,
        required_tools={"get_order"},
        forbidden_tools={"issue_refund"},     # must not invent one
        max_cost_usd=0.05,
    ),
)
```

### Non-determinism

The same task, run twice, gives different trajectories. Two consequences.

**Run each task several times.** Report pass rate, not pass/fail. A task passing
3 of 5 is a real signal — that is a 40% production failure rate.

**Assert on invariants, not on exact sequences.** "Called `get_order` before
`cancel_order`" is stable. "Called exactly these four tools in this order" will
fail on a harmless variation and teach your team to ignore the eval suite.

---

## 3. Minimal Implementation

```python
@dataclass
class EvalResult:
    task_id: str
    runs: int
    passed: int
    failures: list[str]

    @property
    def pass_rate(self) -> float:
        return self.passed / self.runs


def evaluate(harness, task: Task, runs: int = 5) -> EvalResult:
    passed, failures = 0, []

    for i in range(runs):
        state = task.setup()                       # fresh world each run
        trace = harness.run(task.prompt, state=state)

        problems = []
        if not task.assertion(state):
            problems.append("outcome assertion failed")

        tc = task.trajectory
        called = {c.name for c in trace.tool_calls}
        if trace.turns > tc.max_turns:
            problems.append(f"{trace.turns} turns > {tc.max_turns}")
        if missing := tc.required_tools - called:
            problems.append(f"never called {sorted(missing)}")
        if forbidden := tc.forbidden_tools & called:
            problems.append(f"CALLED FORBIDDEN {sorted(forbidden)}")
        if trace.cost_usd > tc.max_cost_usd:
            problems.append(f"${trace.cost_usd:.3f} > ${tc.max_cost_usd:.3f}")

        if problems:
            failures.append(f"run {i}: " + "; ".join(problems))
        else:
            passed += 1

    return EvalResult(task.id, runs, passed, failures)
```

`task.setup()` returning a fresh world per run is not optional. Agents mutate
state, so run two starts from run one's leftovers unless you rebuild it — and
then the eval measures order, not correctness.

---

## 4. LLM-as-Judge, Carefully

For open-ended answers, a model can grade — with three guards:

- **Give it a rubric**, not "is this good?". Specific criteria, each scored.
- **Show it the trajectory**, not just the answer, so it can spot a right answer
  reached by a wrong route.
- **Calibrate against humans** on a sample. If the judge and your team disagree
  30% of the time, the judge is measuring something else.

Never use a judge for anything checkable in code. An assertion that an order is
cancelled is free, deterministic and correct; a judge for the same thing is
none of those.

---

## 5. Trade-offs

**Evals cost real money.** Twenty tasks at five runs is a hundred agent runs per
CI pass. Run the full suite nightly and a fast subset per commit.

**Eval sets go stale.** Tasks that always pass stop informing. Prune them and
keep adding from production.

**Over-fitting is real.** Tuning prompts until the suite is green produces a
system that is good at the suite. Keep a holdout set you do not tune against.

---

## 6. Production Notes

- **Every incident becomes an eval case**, the same day, permanently.
- **Report pass rate over several runs**, not a single pass/fail.
- **Always include `forbidden_tools`.** Safety is half of evaluation.
- **Rebuild world state per run.**
- **Keep a holdout set.**
- **Run the full suite nightly, a subset per commit**, and track pass rate over
  time as its own metric.

---

## 7. What To Say Out Loud

> "Agents are evaluated on trajectory, not just output — an agent can give a
> perfect answer having deleted something it should not have touched, and an
> answer-only eval passes that run. So every task asserts on outcome, on turn and
> cost bounds, on required tools, and on forbidden tools, which is the half people
> leave out. Because runs are non-deterministic I run each task several times and
> report a pass rate; three out of five is a forty percent production failure
> rate, not a pass. Every production incident becomes a permanent case, and I
> keep a holdout set so I am not just tuning prompts until the suite goes green."

---

## 8. Check Yourself

1. Why is answer-only evaluation insufficient for an agent?
2. What does `forbidden_tools` catch that an outcome assertion cannot?
3. Why run each task several times?
4. Why must world state be rebuilt per run?

→ Next: [`regression-suites.md`](regression-suites.md)
