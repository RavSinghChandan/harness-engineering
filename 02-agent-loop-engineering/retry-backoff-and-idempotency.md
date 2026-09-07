# Harness Engineering — Module 2
# Topic: Retry, Backoff and Idempotency

> **F11 — partial-write damage.** The agent died halfway through and left the
> world inconsistent.

---

## 1. Intuition

Agents retry constantly — the model retries tools, your client retries the
model, your queue retries the run. Each layer is reasonable alone. Together they
multiply: three retries at each of three layers is twenty-seven attempts.

And every retry of a *write* is a chance to do the same thing twice.

---

## 2. Core Concept

### Retry only what is safe to repeat

| Failure | Retry? |
|---|---|
| Timeout, 502, 503, connection reset | **Yes** — transient |
| 429 rate limit | **Yes**, after the `Retry-After` delay |
| 400 bad request | **No** — it will fail identically |
| 401, 403 | **No** — credentials will not fix themselves |
| 404 | **No** — the thing does not exist |
| 500 on a **write** | **Only if idempotent** — it may have succeeded |

That last row is the dangerous one. A 500 does not tell you whether the write
landed. Retrying without idempotency risks a double refund.

### Backoff, and why jitter matters

```python
delay = min(base * 2 ** attempt, cap)
delay = delay * (0.5 + random.random())      # jitter
```

Without jitter, every client that failed at the same moment retries at the same
moment — a thundering herd that keeps the service down. Jitter is one line and
it is not optional.

### Idempotency: the real fix

```python
def issue_refund(order_id: str, amount: float, idempotency_key: str) -> str:
    """The same key twice returns the first result. It does not refund twice."""
    if existing := refunds.get(idempotency_key):
        return f"Already refunded: {existing.id}"
    result = payment_provider.refund(order_id, amount, key=idempotency_key)
    refunds.put(idempotency_key, result)
    return f"Refunded {amount} for {order_id}."
```

The key must be **derived from the action**, not random — otherwise a retry
generates a new key and defeats the whole mechanism:

```python
key = sha256(f"{run_id}:{order_id}:{amount}".encode()).hexdigest()[:32]
```

Same run, same order, same amount → same key → one refund, however many retries
happen at any layer.

---

## 3. Minimal Implementation

```python
import random
import time
from dataclasses import dataclass

RETRYABLE = {408, 429, 500, 502, 503, 504}


@dataclass
class RetryPolicy:
    max_attempts: int = 3
    base_delay: float = 0.5
    cap: float = 20.0

    def delay_for(self, attempt: int, retry_after: float | None = None) -> float:
        if retry_after is not None:                 # the server told us; obey it
            return retry_after
        raw = min(self.base_delay * 2 ** attempt, self.cap)
        return raw * (0.5 + random.random())        # jitter: avoid the herd

    def should_retry(self, status: int | None, idempotent: bool) -> bool:
        if status is None:                          # connection error
            return idempotent
        if status not in RETRYABLE:
            return False
        if status >= 500 and not idempotent:
            return False        # it may have succeeded; do not repeat a write
        return True


def with_retry(fn, policy: RetryPolicy, idempotent: bool = False):
    last = None
    for attempt in range(policy.max_attempts):
        try:
            return fn()
        except TransientError as exc:
            last = exc
            if not policy.should_retry(exc.status, idempotent):
                raise
            if attempt == policy.max_attempts - 1:
                break
            time.sleep(policy.delay_for(attempt, exc.retry_after))
    raise last
```

### Do not stack retries

Pick **one** layer to retry at. Retrying in the tool *and* the client *and* the
queue turns a brief outage into a self-inflicted denial of service. The tool
layer is usually right, because it knows whether the operation is idempotent.

---

## 4. Trade-offs

**Retries vs. latency.** Three retries with backoff can add thirty seconds while
a user waits. Cap total retry time, not just attempts.

**Idempotency keys need storage.** Somewhere must remember which keys ran, and
for how long. A day is usually enough; a permanent ledger is a permanent cost.

**Safety vs. throughput.** Refusing to retry non-idempotent writes means some
recoverable failures become user-visible. That is the right trade for anything
involving money.

---

## 5. Production Notes

- **Give every write an idempotency key**, derived deterministically.
- **Retry at one layer only.** Write down which one.
- **Always jitter.**
- **Obey `Retry-After`.** Guessing when a provider told you is rude and slower.
- **Count retries in your trace.** A rising retry rate is an early warning of an
  upstream problem, usually before the error rate moves.

---

## 6. What To Say Out Loud

> "Retries multiply across layers, so I retry at one layer only and write down
> which. What I retry depends on whether the operation is idempotent: a 500 on a
> write does not tell me whether it landed, so retrying without an idempotency
> key risks a double refund. The key has to be derived from the action — run id,
> order, amount — not random, or a retry generates a new key and defeats the
> mechanism. And backoff always has jitter, because without it every client that
> failed together retries together and keeps the service down."

---

## 7. Check Yourself

1. Why is a 500 on a write more dangerous than a 500 on a read?
2. Why must an idempotency key be derived rather than random?
3. What goes wrong without jitter?
4. Why retry at only one layer?

→ Next: [`interrupts-and-resumption.md`](interrupts-and-resumption.md)
