# Harness Engineering — Module 7
# Topic: Shared State and Conflicts

---

## 1. Intuition

Two agents run in parallel. Both read the same file, both edit it, both write it
back. The second write erases the first, and nothing anywhere reports an error.

This is F10 — concurrency corruption — and it is the failure mode that most
resembles ordinary distributed systems work. The difference is that agents are
non-deterministic, so the bug appears in one run out of twenty and you cannot
reproduce it on demand.

---

## 2. Core Concept

### The safe default: no shared mutable state

Most parallel agent work does not need it. Give each agent its own workspace and
merge afterwards:

```python
results = [run_agent(task, workspace=root / f"agent-{i}")
           for i, task in enumerate(tasks)]
merged = merge(results)                    # one writer, one place, deliberate
```

Merging is code you control and can test. Concurrent writes are timing you do
not control and cannot test reliably. Prefer the first every time you can.

### When state must be shared

Three mechanisms, in increasing order of cost.

**1. Append-only.** No conflicts are possible because nothing is overwritten:

```python
class Blackboard:
    def post(self, agent: str, finding: str) -> None:
        with self._lock:
            self._entries.append(Entry(time.time(), agent, finding))
```

This covers most cases. Agents accumulating findings do not need to overwrite
each other; they need to add.

**2. Optimistic concurrency.** Read a version, write only if unchanged:

```python
def update(self, key: str, new_value: str, *, expected_version: int) -> bool:
    with self._lock:
        current = self._store.get(key)
        if current and current.version != expected_version:
            return False                    # somebody else wrote; caller retries
        self._store[key] = Versioned(new_value, expected_version + 1)
        return True
```

The write either succeeds or is rejected. Silent loss is impossible, which is
the entire point.

**3. Ownership.** Partition the state so exactly one agent can write each key.
No locks, no versions, no conflicts — just a rule enforced at the boundary:

```python
def write(self, agent: str, key: str, value: str) -> None:
    if self.owner_of(key) != agent:
        raise PermissionError(f"{agent} does not own {key!r}")
    self._store[key] = value
```

Partitioning is usually the best answer when you can find a clean partition,
because it removes the problem rather than managing it.

### Files are the sharp edge

Agents write files, and file writes are not atomic by default. A crashed
mid-write leaves a truncated file that looks valid — F11, partial-write damage.

Write to a temporary file in the same directory, then rename:

```python
def atomic_write(path: Path, content: str) -> None:
    tmp = path.with_suffix(path.suffix + f".tmp-{os.getpid()}")
    tmp.write_text(content)
    os.replace(tmp, path)            # atomic on POSIX and Windows
```

Same directory matters: `os.replace` is only atomic within a filesystem. And the
pid suffix stops two agents colliding on the temporary file itself.

For read-modify-write on a shared file, take a lock:

```python
import fcntl
from contextlib import contextmanager

@contextmanager
def locked(path: Path):
    lock = path.with_suffix(".lock")
    with open(lock, "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)
```

---

## 3. Detecting Corruption

Silent loss is the danger, so make it loud. Log every write with agent, key and
version, then look for the pattern:

```python
def detect_lost_updates(writes: list[WriteLog]) -> list[str]:
    """Two writes to one key at the same version means one was lost."""
    seen: dict[tuple[str, int], str] = {}
    lost = []
    for w in writes:
        prior = seen.get((w.key, w.base_version))
        if prior and prior != w.agent:
            lost.append(f"{w.key}: {w.agent} overwrote {prior} at v{w.base_version}")
        seen[(w.key, w.base_version)] = w.agent
    return lost
```

Run this over production write logs. It finds the one-in-twenty race that you
could never reproduce locally.

---

## 4. Trade-offs

**Locks serialise, which cancels the parallelism you wanted.** If agents spend
most of their time holding a lock, run them sequentially and keep the simplicity.

**Optimistic concurrency needs retry logic**, and a retrying agent burns turns
and budget. Cap the retries and fail loudly rather than looping.

**Separate workspaces cost disk and a merge step**, and merging can itself
conflict. But the conflict surfaces in code you wrote, at a time you chose,
which is far better than a race.

---

## 5. Production Notes

- **Default to no shared mutable state.** Separate workspaces, explicit merge.
- **Prefer append-only** when state must be shared.
- **Never do a bare read-modify-write** on shared state — version it or lock it.
- **All file writes atomic**, via temp-and-rename in the same directory.
- **Log every write with agent, key and base version**, and run lost-update
  detection over the logs.
- **Cap retries** and surface the failure rather than looping.

---

## 6. What To Say Out Loud

> "My default is no shared mutable state — each agent gets its own workspace and
> I merge deliberately afterwards, because merging is code I control and test
> while concurrent writes are timing I do not. Where state must be shared, I go
> append-only first, then ownership partitioning, then optimistic concurrency
> with versions, so a conflicting write is rejected rather than silently losing
> someone's work. File writes are temp-and-rename in the same directory so a
> crash cannot leave a truncated file that still parses. And I log every write
> with its base version, because the lost-update race shows up once in twenty
> runs and you will never reproduce it locally."

---

## 7. Check Yourself

1. Why prefer separate workspaces with a merge step over shared state?
2. Why is append-only conflict-free?
3. Why must the temp file be in the same directory as the target?
4. How do you detect a lost update after the fact?

→ Next: [`../08-production-harness/deployment-shapes.md`](../08-production-harness/deployment-shapes.md)
