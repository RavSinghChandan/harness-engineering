# Harness Engineering — Module 8
# Topic: Concurrency and Queueing

---

## 1. Intuition

Ten users submit tasks. Each run takes 90 seconds and makes twenty model calls.
Run them all at once and you hit the provider's rate limit, every run starts
failing on retry, and the total time is worse than if you had run them in
sequence.

Concurrency in an agent system is not bounded by your CPU. It is bounded by a
resource you do not own — the provider's rate limit — and the queue exists to
respect that boundary rather than crash into it.

---

## 2. Core Concept

### Three limits, three places to enforce

| Limit | Set by | Enforced |
|---|---|---|
| Concurrent runs | Your capacity | Worker pool size |
| Requests per minute | The provider | A shared limiter |
| Tokens per minute | The provider | A shared limiter |

The token limit is the one people forget, and it is usually the binding one. Ten
concurrent agents, each sending a 20,000-token context, is 200,000 tokens per
call round — enough to exceed a generous quota on its own.

### Fair queueing

A single FIFO queue lets one user with fifty tasks starve everyone else. Round
robin over per-user queues fixes it:

```python
class FairQueue:
    """Round robin across users, so one heavy user cannot starve the rest."""

    def __init__(self):
        self._queues: dict[str, deque] = {}
        self._order: deque[str] = deque()

    def put(self, user: str, task: Task) -> None:
        with self._lock:
            if user not in self._queues:
                self._queues[user] = deque()
                self._order.append(user)
            self._queues[user].append(task)

    def get(self) -> tuple[str, Task] | None:
        with self._lock:
            for _ in range(len(self._order)):
                user = self._order[0]
                self._order.rotate(-1)           # next user gets the next turn
                if self._queues[user]:
                    return user, self._queues[user].popleft()
            return None
```

Fifty tasks from one user then interleave with everyone else's, instead of
blocking them.

### The shared token limiter

Rate limiting per worker does not work: eight workers each allowing 100 requests
a minute is 800 against a 100 limit. The limiter must be shared across all
workers — Redis, or a single coordinating process:

```python
class TokenBucket:
    """Shared across workers. Reserve before the call, refund the unused part."""

    def acquire(self, tokens: int, timeout: float = 60.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                self._refill()
                if self._available >= tokens:
                    self._available -= tokens
                    return True
            time.sleep(0.1)
        return False

    def refund(self, tokens: int) -> None:
        with self._lock:
            self._available = min(self._capacity, self._available + tokens)
```

Reserve on an *estimate* before the call, then refund the difference once the
response reports actual usage. Reserving after the fact means the limit is only
noticed once it has already been breached.

### Backpressure

When the queue grows faster than it drains, reject rather than accumulate:

```python
def submit(user: str, task: Task) -> dict:
    if queue.depth() > MAX_DEPTH:
        return {"error": "System at capacity. Try again shortly.",
                "retry_after": estimate_wait()}
    queue.put(user, task)
    return {"run_id": ..., "position": queue.position(user)}
```

An unbounded queue is not resilience. It is a slow-motion outage: everything is
accepted, nothing completes in a useful time, and memory grows until the process
dies. Rejecting early with an honest wait estimate is better service than
accepting work you cannot do.

---

## 3. Sizing the Pool

Start from the provider limit and work backwards, not from CPU count:

```python
# Provider: 400,000 tokens/minute
# Typical run: 20 calls x 15,000 tokens = 300,000 tokens over ~90 seconds
#            = 200,000 tokens/minute per run
# So: 400,000 / 200,000 = 2 concurrent runs.

MAX_CONCURRENT = provider_tokens_per_minute // tokens_per_minute_per_run
```

Two concurrent runs on an eight-core box looks wasteful and is correct. The CPU
is idle because the work is waiting on a network call — adding workers adds rate
limit errors, not throughput.

Then check memory: each in-flight run holds its transcript and retrieved
documents. Take the lower of the two numbers.

---

## 4. Priority Without Starvation

Interactive runs should beat batch runs, but batch work must still finish:

```python
class PriorityFairQueue:
    def get(self) -> tuple[str, Task] | None:
        # Serve interactive first, but force a batch item every N picks
        # so batch work cannot be starved indefinitely.
        self._picks += 1
        if self._picks % 5 == 0 and self._batch:
            return self._batch.get()
        return self._interactive.get() or self._batch.get()
```

Strict priority starves the lower tier forever under sustained load. The
every-fifth rule guarantees progress at a small cost to interactive latency.

---

## 5. Trade-offs

**A shared limiter is a coordination point**, meaning a Redis round trip per
call and a dependency that can fail. Fail open with a conservative local limit
rather than blocking all work when the limiter is unreachable.

**Fair queueing adds bookkeeping** and slightly worse throughput than pure FIFO.
Worth it the moment you have more than one user.

**Backpressure means visible rejections.** Users prefer "try again in two
minutes" to a request that hangs for ten and then fails.

---

## 6. Production Notes

- **Size the pool from the provider's token limit**, then check against memory.
  Ignore CPU count.
- **Share the rate limiter across workers.** Per-worker limits multiply.
- **Reserve on estimate, refund on actual.**
- **Bound the queue** and reject with an honest `retry_after`.
- **Round robin per user**, and guarantee progress for lower-priority tiers.
- **Chart queue depth and wait time** — depth rising steadily means the pool is
  undersized or runs are getting longer.

---

## 7. What To Say Out Loud

> "Agent concurrency is bounded by the provider's token limit, not by CPU — so I
> size the worker pool by dividing the tokens-per-minute quota by what a typical
> run consumes, which often gives a small number like two on an eight-core box.
> That looks wasteful and is correct, because more workers buy rate limit errors
> rather than throughput. The limiter is shared across workers, since per-worker
> limits multiply, and it reserves on an estimate then refunds the unused part.
> The queue is bounded and round robins per user, because an unbounded queue is
> not resilience — it is a slow outage where everything is accepted and nothing
> finishes."

---

## 8. Check Yourself

1. Why is CPU count the wrong basis for pool size?
2. Why must the rate limiter be shared rather than per-worker?
3. Why reserve tokens before the call rather than after?
4. Why is an unbounded queue worse than rejecting work?

→ Next: [`rate-limits-and-quotas.md`](rate-limits-and-quotas.md)
