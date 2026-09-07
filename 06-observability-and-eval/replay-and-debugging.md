# Harness Engineering — Module 6
# Topic: Replay and Debugging

> **F8 — non-reproducibility.** The failure that makes every other failure
> permanent.

---

## 1. Intuition

A normal bug: you get a stack trace, you write a failing test, you fix it, the
test passes forever.

An agent bug: it happened once, at 3am, to one user, and the model is sampling —
so running the same input again gives you a *different* run that works fine.

The trap is thinking you need determinism from the model. You do not. You need
to be able to **replay the harness with the model's decisions held fixed**. Then
the loop, the tools, the budgets and the permissions all become ordinary,
testable code again.

---

## 2. Core Concept

### Record once, replay many

```
LIVE RUN                         REPLAY
  model → "call search"            recorded reply → "call search"
  tool  → 3 results                recorded result → 3 results
  model → "call read_doc"          recorded reply → "call read_doc"
  tool  → ERROR                    recorded result → ERROR
  model → wrong answer             recorded reply → wrong answer
```

In replay, the model is not called. Its outputs are read from the recording. So
the run is fully deterministic, and you can:

- Step through it
- Change your harness code and see if the outcome changes
- Turn it into a regression test that runs in milliseconds

### The two things you must record

**1. Model outputs** — each reply, in order.
**2. Tool outputs** — each result, in order.

With both, the entire run reconstructs. Without model outputs you cannot replay
at all. Without tool outputs your replay hits the network and stops being
deterministic.

### What replay is for

| Question | Replay answers it? |
|---|---|
| Did my new permission check block this? | **Yes** |
| Does my compaction change the outcome? | **Yes** |
| Would a bigger turn budget have helped? | **Yes** |
| Would a better prompt have helped? | **No** — that changes model output |

That last row matters. Replay tests *your* code. Testing prompt changes needs
evaluation against a live model, which is a different tool (see
`evaluating-agents.md`).

---

## 3. Minimal Implementation

```python
import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Recording:
    """Everything needed to re-run a session without a network."""

    run_id: str
    task: str
    model_replies: list[dict] = field(default_factory=list)
    tool_results: list[str] = field(default_factory=list)
    stop_reason: str = ""

    def save(self, directory: str = "recordings") -> Path:
        path = Path(directory) / f"{self.run_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.__dict__, indent=2, default=str))
        return path

    @classmethod
    def load(cls, path: str | Path) -> "Recording":
        return cls(**json.loads(Path(path).read_text()))


class RecordingModel:
    """Wraps a real model and captures what it says."""

    def __init__(self, inner, recording: Recording):
        self.inner, self.recording = inner, recording

    def __call__(self, messages):
        reply = self.inner(messages)
        self.recording.model_replies.append(reply)
        return reply


class ReplayModel:
    """Replays captured replies. No network, fully deterministic."""

    def __init__(self, recording: Recording):
        self.replies = list(recording.model_replies)
        self.index = 0

    def __call__(self, messages):
        if self.index >= len(self.replies):
            # The harness asked for MORE turns than the original run. That is
            # itself a finding -- your change made the agent do more work.
            raise ReplayExhausted(
                f"Replay ran out after {self.index} model calls. "
                "The harness under test is making more calls than the recording."
            )
        reply = self.replies[self.index]
        self.index += 1
        return reply


class ReplayExhausted(RuntimeError):
    pass
```

### Using it as a regression test

```python
def test_the_3am_bug_stays_fixed():
    recording = Recording.load("recordings/a7f3.json")

    harness = Harness(
        model=ReplayModel(recording),
        tools=replay_tools(recording),
        policy=Policy(mode=Mode.ASK_FIRST),   # the fix under test
    )
    result = harness.run(recording.task)

    assert "Denied" in result.transcript_text(), "the write should now be blocked"
```

That test runs in milliseconds, costs nothing, needs no API key, and fails
loudly if someone removes the fix. This is the payoff for recording.

---

## 4. Debugging Workflow

When a run goes wrong:

1. **Find the run** by `run_id` from the user's report or the alert.
2. **Print the tree** (`tracer.as_tree()`). Nine times in ten the bad step is
   visible immediately.
3. **Read the context at that turn**, not the final answer. The question is
   always *what did the model see when it decided that?*
4. **Replay** with your suspected fix.
5. **Keep the recording as a test.**

Step 3 is the one people skip. The output is a symptom; the input is the cause.

---

## 5. Trade-offs

**Storage.** Full recordings are large. Record everything in staging; in
production record failures fully and successes by sampling.

**PII.** A recording is a copy of user data with a long retention. Redact at
record time, not at read time, and treat the store as sensitive.

**Replay drift.** As your harness evolves, old recordings hit `ReplayExhausted`
because the loop now behaves differently. That is a signal, not a nuisance —
though it does mean recordings age. Re-record the ones you keep as tests.

---

## 6. Production Notes

- **Redact at record time.** Secrets in a recording live as long as the file.
- **Name recordings by what they prove**, not just by run_id:
  `refund_without_confirmation_a7f3.json`.
- **Keep a small suite of recordings in the repo** as regression tests. Ten good
  ones catch most harness regressions.
- **Record the harness version** alongside the run. When a replay behaves
  strangely, the first question is what changed.

---

## 7. What To Say Out Loud

> "Agent bugs are hard because the model samples — run the same input twice and
> you get different runs. The trick is that you do not need the model to be
> deterministic, you need to replay the harness with the model's decisions held
> fixed. So I record every model reply and every tool result, and replay reads
> from that recording instead of calling out. Then the loop, budgets,
> permissions and compaction are ordinary deterministic code I can unit-test in
> milliseconds. The best failures become permanent regression tests. What replay
> cannot test is a prompt change, because that changes what the model would say
> — that needs live evaluation instead."

---

## 8. Check Yourself

1. Why does replay not require a deterministic model?
2. What two things must be recorded, and what breaks without each?
3. Why can replay not test a prompt improvement?
4. Your replay raises `ReplayExhausted`. What does that tell you?

→ Next: [`evaluating-agents.md`](evaluating-agents.md)
