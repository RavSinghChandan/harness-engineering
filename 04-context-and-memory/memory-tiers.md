# Harness Engineering — Module 4
# Topic: Memory Tiers

---

## 1. Intuition

"Give the agent memory" sounds like one feature. It is at least four, with
different lifetimes, different costs and different failure modes.

Conflating them produces the two classic bugs: an agent that forgets what you
told it thirty seconds ago, and an agent that remembers something wrong forever.

---

## 2. Core Concept

### The four tiers

| Tier | Lifetime | Where it lives | What it holds |
|---|---|---|---|
| Working | One turn | The prompt | Current task, recent messages |
| Session | One run | Transcript + state object | Everything this run has done |
| Persistent | Across runs | Database / files | Facts about the user or project |
| Shared | Across agents | Queue / store | Handoffs between agents |

Each answers a different question:

- **Working** — what am I doing right now?
- **Session** — what have I already tried?
- **Persistent** — what do I know about this user?
- **Shared** — what did the other agent find?

### The mistake that causes "it forgot"

Compaction dropped it from working memory, and nothing wrote it to session
state. Anything that must survive compaction has to live in *structured state*,
not in the transcript:

```python
@dataclass
class SessionState:
    goal: str                                   # never compacted away
    constraints: list[str] = field(default_factory=list)
    facts: dict[str, str] = field(default_factory=dict)
    files_written: list[str] = field(default_factory=list)
    tried_and_failed: list[str] = field(default_factory=list)
```

`tried_and_failed` is the one people leave out, and it is exactly why compacted
agents loop: the record of the failed attempt was in the messages that got
summarised away, so the model tries it again.

Render this state into the prompt on every turn, as a compact block separate
from the message history. It costs a few hundred tokens and it is the cheapest
bug fix in agent engineering.

### The mistake that causes "it remembers something wrong"

Persistent memory written without verification. The model inferred "this user
prefers TypeScript" from one message, stored it, and now applies it forever.

Three guards, all on the record itself:

```python
@dataclass
class Memory:
    fact: str
    source: str                # which run, which message
    confidence: str            # "stated" | "inferred"
    written_at: float
    expires_at: float | None = None
```

- **Source** — so a wrong memory can be traced back to its origin.
- **Confidence** — `inferred` facts are advisory; `stated` ones are binding.
- **Expiry** — preferences go stale. A fact with no expiry is a fact you can
  only correct by hand.

Write `stated` memories automatically. `inferred` ones should need either a
confirmation or repeated evidence before they persist.

---

## 3. Minimal Implementation

```python
class MemoryStore:
    """The persistent tier. Deliberately small, deliberately explicit."""

    def __init__(self, path: Path):
        self.path = path
        self._memories: dict[str, Memory] = self._load()

    def remember(self, key: str, fact: str, *, source: str,
                 confidence: str = "inferred", ttl_days: int | None = 90) -> None:
        expires = time.time() + ttl_days * 86400 if ttl_days else None
        self._memories[key] = Memory(fact, source, confidence, time.time(), expires)
        self._save()

    def recall(self, *, include_inferred: bool = True) -> list[Memory]:
        now = time.time()
        live = [m for m in self._memories.values()
                if m.expires_at is None or m.expires_at > now]
        if not include_inferred:
            live = [m for m in live if m.confidence == "stated"]
        return live

    def forget(self, key: str) -> None:
        self._memories.pop(key, None)
        self._save()

    def render(self) -> str:
        """Into the prompt. Capped, or memory eats the context window."""
        recent = sorted(self.recall(), key=lambda m: m.written_at, reverse=True)[:20]
        if not recent:
            return ""
        return "Known about this user:\n" + "\n".join(f"- {m.fact}" for m in recent)
```

The `[:20]` cap is not decoration. Unbounded memory grows until it is the
dominant cost of every call, and most of what it holds is stale.

---

## 4. Shared Memory Between Agents

Shared state is the tier that corrupts silently, because two agents write at
once. The safe default is **append-only**:

```python
class Blackboard:
    """Agents append findings. Nobody overwrites anybody."""

    def post(self, agent: str, finding: str) -> None:
        with self._lock:
            self._entries.append((time.time(), agent, finding))

    def read(self, since: float = 0.0) -> list[tuple[float, str, str]]:
        return [e for e in self._entries if e[0] > since]
```

If agents genuinely must overwrite a shared value, that needs versions and
conflict resolution — see
[`../07-multi-agent-harness/shared-state-and-conflicts.md`](../07-multi-agent-harness/shared-state-and-conflicts.md).

---

## 5. Trade-offs

**Persistent memory is a privacy surface.** You are storing facts about people.
It needs the same retention policy, deletion path and access control as any
other user data.

**More memory is not better.** Every remembered fact is prompt tokens on every
call, and stale facts actively mislead. Cap and expire.

**Structured state is work.** Someone must decide what belongs in it and keep it
updated as the run proceeds. That work is the whole difference between an agent
that survives compaction and one that does not.

---

## 6. Production Notes

- **Render session state every turn**, outside the message history, so
  compaction cannot take it.
- **Track `tried_and_failed`** — the specific cure for post-compaction looping.
- **Cap and expire persistent memory.** Ninety days is a sane default for a
  preference.
- **Store source and confidence.** A wrong memory you cannot trace is one you
  cannot fix.
- **Let users see and delete what you remember.** Usually a legal requirement,
  and also the fastest debugging tool you will have.

---

## 7. What To Say Out Loud

> "Memory is four tiers, not one: working, session, persistent, shared. 'The
> agent forgot' almost always means something lived only in the transcript and
> compaction removed it — so anything that must survive goes into structured
> session state rendered on every turn, especially the list of what has already
> been tried, which is what stops a compacted agent looping. 'The agent
> remembers something wrong' means an inferred fact was stored as if it were
> stated, so every memory carries source, confidence and expiry, and only stated
> facts are written automatically."

---

## 8. Check Yourself

1. Name the four tiers and the question each answers.
2. Why does a compacted agent start repeating failed attempts?
3. Why store confidence on a persistent memory?
4. Why is unbounded memory a cost problem as well as a correctness problem?

→ Next: [`retrieval-in-the-loop.md`](retrieval-in-the-loop.md)
