# Harness Engineering — Module 2
# Topic: Interrupts and Resumption

---

## 1. Intuition

Long runs get interrupted. A user clicks stop, a deploy rolls the pod, a
provider times out, an approval is needed. The question is never *whether* — it
is whether the interruption leaves you with something you can continue, and a
world that is not half-changed.

There are two very different kinds, and conflating them causes bugs:

- **Pause** — we intend to continue. State must survive.
- **Cancel** — we do not. State can be discarded, but side effects cannot.

---

## 2. Core Concept

### Interrupt at a safe point

```
   model call ──── SAFE ──── tool call ──── UNSAFE ──── tool returns ──── SAFE
```

Interrupting between turns is clean. Interrupting *during* a write is F11 — you
do not know whether it landed.

```python
while True:
    if self.interrupted:            # top of the turn: the only safe place
        return self._checkpoint_and_stop()

    reply = self.model(messages)
    for call in reply.tool_calls:
        result = self.tools.execute(call)   # never interrupted mid-flight
        messages.append(result)
```

Checking only at the top of a turn means a cancel may take one turn to take
effect. That is the correct trade: a slightly slower stop beats a corrupt state.

### The three sources

| Source | Kind | Response |
|---|---|---|
| User clicks stop | Cancel | Checkpoint, stop, no resume |
| Deploy or crash | Pause | Checkpoint, resume automatically |
| Awaiting approval | Pause | Checkpoint, resume on decision |
| Budget exhausted | Cancel | Return partial, do not resume |

Note the last row. A budget stop is *deliberate*; resuming it silently undoes
the operator's decision.

### Resumption needs three things

1. **The transcript** — the model has no memory; without messages there is no run.
2. **The completed-actions ledger** — so side effects are not repeated (P07).
3. **The budget so far** — otherwise a resumed run gets a fresh full budget, and
   an interrupt becomes a way to bypass your cost ceiling.

That third one is easy to miss and is a genuine cost bug.

---

## 3. Minimal Implementation

```python
import signal
from dataclasses import dataclass


@dataclass
class Interruptible:
    """Cooperative interruption. No thread killing, no partial writes."""

    paused: bool = False
    cancelled: bool = False

    def install_signal_handlers(self) -> None:
        def request_pause(signum, frame):
            self.paused = True          # set a flag; do not unwind here
        signal.signal(signal.SIGTERM, request_pause)   # deploys send this

    @property
    def should_stop(self) -> bool:
        return self.paused or self.cancelled

    @property
    def reason(self) -> str:
        return "cancelled" if self.cancelled else "interrupted"


def run_with_interrupts(harness, task, store, control: Interruptible):
    state = store.load(harness.run_id) or new_state(task)

    while True:
        if control.should_stop:
            state.stop_reason = control.reason
            store.save(state)                       # resumable iff "interrupted"
            return state

        stop = harness.check_budgets(state)          # budgets carried across resume
        if stop:
            state.stop_reason = stop.value
            store.save(state)
            return state

        harness.one_turn(state)
        store.save(state)                            # checkpoint every turn
```

Signal handlers set a **flag**. They never raise, because raising inside a
handler can unwind the stack in the middle of a write.

---

## 4. Trade-offs

**Checkpoint frequency.** Every turn is safe and adds a write per turn. Every
five turns is faster and loses up to five turns of work. For expensive runs,
every turn is cheap by comparison.

**Responsiveness vs. safety.** Checking mid-tool would stop faster and risks
partial writes. Turn boundaries only.

**Auto-resume vs. manual.** Automatic resumption is convenient and will happily
resume a run that was failing. Resume automatically once, then require a human.

---

## 5. Production Notes

- **Handle SIGTERM.** Your orchestrator sends it before SIGKILL; that window is
  your chance to checkpoint.
- **Carry budgets across resumption**, or interrupts become a cost bypass.
- **Never resume a run that hit a budget or was cancelled.** Only `interrupted`.
- **Cap resume attempts.** A run that has resumed five times is stuck, not
  unlucky.
- **Tell the user.** "Paused, resuming shortly" beats silence.

---

## 6. What To Say Out Loud

> "I distinguish pause from cancel: pause means we intend to continue so state
> must survive, cancel means we do not. Interruption is cooperative and only
> happens at the top of a turn — never mid-tool, because interrupting a write
> leaves you not knowing whether it landed. Signal handlers set a flag rather
> than raising, since raising can unwind in the middle of something. Resumption
> needs three things: the transcript, the ledger of completed actions so side
> effects are not repeated, and the budget consumed so far — miss that last one
> and an interrupt becomes a way to bypass your cost ceiling."

---

## 7. Check Yourself

1. Why is the top of a turn the only safe interrupt point?
2. Why do signal handlers set a flag rather than raise?
3. What are the three things resumption needs, and what breaks without each?
4. Why must a budget-exhausted run not resume?

→ Next: [`streaming-and-partial-output.md`](streaming-and-partial-output.md)
