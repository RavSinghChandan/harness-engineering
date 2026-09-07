# Harness Engineering — Module 8
# Topic: Rate Limits and Quotas

---

## 1. Intuition

Rate limits are the provider protecting themselves. Quotas are you protecting
yourself. They look similar — both cap usage — but they fail in opposite
directions, and confusing them is how a single runaway loop bills a month's
budget in an afternoon.

Hit a rate limit and you get a 429 and back off. Blow a quota and nobody tells
you until the invoice.

---

## 2. Core Concept

### Handling 429s

A 429 is routine, not an incident. The provider usually tells you how long to
wait, and the only real rule is to honour that rather than guess:

```python
def call_with_retry(fn, *, max_attempts: int = 5):
    for attempt in range(max_attempts):
        try:
            return fn()
        except RateLimitError as exc:
            if attempt == max_attempts - 1:
                raise
            wait = exc.retry_after or (2 ** attempt)     # honour the header
            wait += random.uniform(0, wait * 0.1)        # jitter
            time.sleep(wait)
```

The jitter is not decoration. Without it, every worker that got a 429 at the
same moment retries at the same moment, and you rate limit yourself again — the
thundering herd. A few percent of randomness spreads them out.

And retry in exactly one place. Retries at the HTTP client, the model wrapper
and the agent loop multiply: three layers of five attempts is 125 calls for one
logical request. See
[`../02-agent-loop-engineering/retry-backoff-and-idempotency.md`](../02-agent-loop-engineering/retry-backoff-and-idempotency.md).

### Quotas are yours to enforce

The provider will happily let you spend without limit. Four layers, each capping
the one above:

```python
@dataclass
class QuotaLayers:
    per_run_usd: float = 0.50          # one task cannot run away
    per_user_daily_usd: float = 10.00  # one user cannot drain the budget
    per_org_daily_usd: float = 500.00  # the whole system has a ceiling
    per_org_monthly_usd: float = 10_000.00
```

The per-run cap is the one that saves you. Most cost incidents are a single run
looping, not many users — and a per-run budget stops it in seconds, while a
daily cap only notices after the damage.

### Checking before, recording after

```python
class QuotaEnforcer:
    def check(self, user: str, org: str, estimated_usd: float) -> Verdict:
        if self.run_spend + estimated_usd > self.limits.per_run_usd:
            return Verdict(False, "run budget exhausted", stop_reason="budget_exceeded")
        if self.day_spend(user) + estimated_usd > self.limits.per_user_daily_usd:
            return Verdict(False, "daily limit reached for this user")
        if self.day_spend(org) + estimated_usd > self.limits.per_org_daily_usd:
            return Verdict(False, "organisation daily limit reached")
        return Verdict(True)

    def record(self, user: str, org: str, actual_usd: float) -> None:
        self.run_spend += actual_usd
        self._add(user, actual_usd)
        self._add(org, actual_usd)
```

Estimate before, record actual after. The estimate need not be precise — it just
has to stop you starting a call that would obviously breach the cap.

### Degrading rather than failing

At 80% of a daily quota, do not stop. Degrade:

| Usage | Response |
|---|---|
| < 80% | Normal |
| 80–95% | Cheaper model for background work; warn |
| 95–100% | Interactive only; batch work queued for tomorrow |
| 100% | Reject with a clear message and a reset time |

A system that degrades stays useful. One that stops dead at 100% has an outage
with no warning, and support finds out from users.

---

## 3. Distributed Enforcement

Per-process quota counters do not work with multiple workers: eight workers each
allowing $10 a day is $80. Counters must be shared and atomic:

```python
def record_spend(redis, key: str, usd: float, ttl: int) -> float:
    pipe = redis.pipeline()
    pipe.incrbyfloat(key, usd)
    pipe.expire(key, ttl)                  # daily key expires on its own
    total, _ = pipe.execute()
    return float(total)
```

`incrbyfloat` is atomic, so concurrent workers cannot lose an increment. The TTL
means daily keys clean themselves up rather than needing a reset job.

Record spend even when the run fails. Failed calls cost money, and quota that
only counts successes systematically under-reports the spend that matters most.

---

## 4. Trade-offs

**Estimating cost before a call is imprecise.** Output length is unknown until
it arrives. Estimate conservatively and reconcile after — being slightly
cautious is much cheaper than being slightly generous.

**Hard caps cut off legitimate work.** A user with a genuinely large task hits
the per-run limit and gets a partial result. That is the correct behaviour, but
the message must say what happened and how to proceed — not "error".

**Shared counters add a dependency.** If Redis is down, fail closed on org-level
caps (safety) and open on per-user ones (availability). Losing the ceiling is a
much worse outcome than briefly losing fairness.

---

## 5. Production Notes

- **Honour `retry_after`; always add jitter.**
- **Retry in exactly one layer.**
- **Per-run cap is non-negotiable** — it is what stops a runaway loop.
- **Estimate before, record actual after**, including on failures.
- **Use atomic shared counters** with TTLs.
- **Degrade at 80% and 95%** rather than stopping dead at 100%.
- **Alert on the rate of spend, not only the total.** A 3× normal burn rate at
  noon is the signal; the daily total is the confirmation, too late.

---

## 6. What To Say Out Loud

> "Rate limits are the provider's protection, quotas are mine. On a 429 I honour
> `retry_after` with jitter, and retry in exactly one layer — three layers of five
> attempts is a hundred and twenty-five calls for one request. Quotas are four
> nested caps: per run, per user per day, per org per day, per org per month. The
> per-run cap is the one that matters, because most cost incidents are a single
> run looping rather than many users, and a daily cap only notices after the
> damage. Counters are atomic and shared, spend is recorded even on failures, and
> I alert on burn *rate*, because by the time the daily total is alarming the
> money is gone."

---

## 7. Check Yourself

1. Why does retry need jitter?
2. Why is the per-run cap the most important layer?
3. Why record spend on failed calls?
4. Why alert on burn rate rather than total?

→ Next: [`cost-control.md`](cost-control.md)
