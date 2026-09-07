# Harness Engineering — Module 8
# Topic: Deployment Shapes

---

## 1. Intuition

A web request finishes in 200ms. An agent run takes 90 seconds and makes twenty
outbound calls, most of them spent waiting.

That single difference — long, mostly idle, occasionally very long — is what
breaks agents when they are deployed like ordinary web services. Load balancers
time out, autoscalers see idle CPU and scale down mid-run, and serverless
platforms kill the process at their hard limit.

---

## 2. Core Concept

### Four shapes

| Shape | Latency | Max duration | Survives restart | Use for |
|---|---|---|---|---|
| Synchronous request | Immediate | ~30s | No | Short, interactive |
| Streaming request | Immediate | Minutes | No | Interactive, long |
| Background job | Deferred | Hours | Yes | Batch, heavy |
| Durable workflow | Deferred | Days | Yes | Approvals, multi-day |

The mistake almost everyone makes is starting with the first shape and keeping
it too long. It works in development, where tasks are small, and fails in
production, where a user asks something genuinely hard.

### Synchronous — only for short work

```python
@app.post("/agent")
def run_agent(task: str) -> dict:
    result = harness.run(task, budget=Budget(max_turns=5, max_seconds=25))
    return {"output": result.output}
```

Viable only with a hard budget below the platform's timeout. Note 25 seconds
against a 30-second limit: the budget must trip *before* the platform kills you,
or the user gets a generic gateway error instead of your partial result.

### Background job — the reliable default

```python
@app.post("/agent")
def submit(task: str) -> dict:
    run_id = str(uuid.uuid4())
    store.create(run_id, status="queued", task=task)
    queue.enqueue(execute_run, run_id)
    return {"run_id": run_id, "status": "queued"}


@app.get("/agent/{run_id}")
def status(run_id: str) -> dict:
    return store.get(run_id)                    # queued | running | done | failed
```

Submit returns immediately; the client polls or subscribes. No timeout pressure,
work survives a web restart, and you can retry a failed run without the user
resubmitting.

The cost is a queue, a worker pool and a status store — real operational
surface, and the reason people put it off. Put it in before the first production
incident rather than after.

### Durable workflow — when a human is in the loop

If a run can pause for approval, the process cannot hold state in memory. It
must checkpoint and be resumable from storage:

```python
def execute_run(run_id: str) -> None:
    state = store.load_checkpoint(run_id) or State(task=store.get_task(run_id))

    while not state.done:
        step = harness.step(state)
        state = step.state
        store.save_checkpoint(run_id, state)     # after every step

        if step.needs_approval:
            store.update(run_id, status="awaiting_approval", request=step.request)
            return                               # exit; resumed by the approval

    store.update(run_id, status="done", output=state.output)
```

Checkpoint after *every* step, not every few. The saving is what makes a
worker restart cost one step instead of the whole run.

---

## 3. What Breaks in Practice

**Load balancer timeouts.** Default is often 60 seconds. A streaming response
still needs a heartbeat, or an idle connection is dropped mid-run.

**Autoscaling on CPU.** An agent waiting on the model uses almost no CPU, so the
autoscaler sees idle workers and removes them — with runs in flight. Scale on
queue depth or in-flight runs, never CPU.

**Graceful shutdown.** A deploy sends SIGTERM. Without handling it, in-flight
runs die at whatever point they had reached, possibly having written half their
changes:

```python
def handle_sigterm(signum, frame) -> None:
    shutdown.set()                     # loop checks it at each turn boundary

signal.signal(signal.SIGTERM, handle_sigterm)
```

Check the flag at turn boundaries only, checkpoint, and exit. Interrupting
mid-tool-call is how you get F11, partial-write damage. See
[`../02-agent-loop-engineering/interrupts-and-resumption.md`](../02-agent-loop-engineering/interrupts-and-resumption.md).

**Memory growth.** Long runs accumulate transcript, tool results and retrieved
documents. A worker handling many long runs concurrently can exhaust memory
where a short-request service never would. Cap concurrency per worker by memory,
not by CPU count.

**Serverless hard limits.** Most platforms cap at a few minutes and cannot be
extended. Fine for the synchronous shape, unusable for the others.

---

## 4. Trade-offs

**Background jobs add operational surface.** A queue, workers, a status store,
and a dead-letter path. Worth it as soon as any run exceeds thirty seconds.

**Durable workflows add serialisation constraints.** Everything in state must be
serialisable, which rules out open connections and file handles in state. It is
a discipline, and it is the same discipline that makes replay possible.

**Polling is chatty.** Server-sent events on the status endpoint are usually
better than clients polling every second.

---

## 5. Production Notes

- **Budget below the platform timeout**, with margin, so your error is returned
  rather than the gateway's.
- **Scale on queue depth or in-flight runs**, never CPU.
- **Handle SIGTERM**, check it at turn boundaries, checkpoint, exit.
- **Heartbeat streaming responses** every 15 seconds.
- **Cap per-worker concurrency by memory.**
- **Make run ids client-supplied or idempotent**, so a retried submit does not
  start the work twice.
- **Dead-letter failed runs** with their trace attached, not just a message.

---

## 6. What To Say Out Loud

> "Agent runs are long and mostly idle, which is what breaks them when they are
> deployed like normal web services. Anything over about thirty seconds becomes a
> background job: submit returns a run id immediately, workers execute, the client
> polls or subscribes. Autoscaling goes on queue depth rather than CPU, because
> an agent waiting on the model looks idle and the autoscaler will remove workers
> with runs in flight. SIGTERM sets a flag checked at turn boundaries so a deploy
> checkpoints rather than tearing a run apart mid-write. And the run budget sits
> below the platform timeout with margin, so the user gets my partial result
> instead of a gateway error."

---

## 7. Check Yourself

1. Why must the budget be below the platform timeout?
2. Why is CPU-based autoscaling wrong for agents?
3. Why check the shutdown flag only at turn boundaries?
4. What must be true of everything in a durable workflow's state?

→ Next: [`concurrency-and-queueing.md`](concurrency-and-queueing.md)
