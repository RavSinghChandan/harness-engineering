# Harness Engineering

**The layer between a model and a working product.**

Prompt engineering shapes one call. Context engineering shapes what the model
sees. **Harness engineering shapes everything around the model** — the loop that
decides when to call it, the tools it can reach, the permissions it operates
under, the memory it carries, and the evidence you keep when it goes wrong.

A model is a function. A harness is a system.

---

## Who this is for

Engineers who can already call an LLM API and now have to make it *reliable* —
running unattended, holding permissions, touching real systems, and being
answerable when it misbehaves.

Assumes: Python, HTTP, basic async. Does not assume ML background.

---

## Why this discipline exists

Every serious agent product converges on the same problems:

| The problem | Where it bites |
|---|---|
| The loop never terminates | Cost explosion, hung requests |
| The model calls a tool wrongly | Corrupted data, failed writes |
| Context grows past the window | Silent truncation, forgotten instructions |
| A tool has more authority than the task | Destructive action nobody approved |
| Nobody can explain what happened | No audit trail, no way to fix it |

None of these are model problems. They are **harness** problems, and they are
solved with ordinary engineering: control flow, schemas, budgets, logs.

---

## Folder architecture

```
harness-engineering/
│
├── 01-harness-fundamentals/          — What a harness is and why it exists
│   ├── what-is-a-harness.md
│   ├── model-vs-harness-boundary.md
│   ├── anatomy-of-an-agent-turn.md
│   ├── failure-taxonomy.md
│   └── when-not-to-use-an-agent.md
│
├── 02-agent-loop-engineering/        — The control loop itself
│   ├── the-core-loop.md
│   ├── termination-and-budgets.md
│   ├── retry-backoff-and-idempotency.md
│   ├── interrupts-and-resumption.md
│   └── streaming-and-partial-output.md
│
├── 03-tool-design/                   — The agent's hands
│   ├── tool-schema-design.md
│   ├── errors-as-feedback.md
│   ├── tool-selection-and-routing.md
│   ├── dangerous-tools-and-confirmation.md
│   └── tool-testing.md
│
├── 04-context-and-memory/            — What the model sees
│   ├── context-assembly.md
│   ├── compaction-and-summarisation.md
│   ├── memory-tiers.md
│   ├── retrieval-in-the-loop.md
│   └── prompt-caching-economics.md
│
├── 05-permissions-and-safety/        — What it is allowed to do
│   ├── permission-models.md
│   ├── sandboxing-and-isolation.md
│   ├── prompt-injection-through-tools.md
│   ├── secrets-and-credentials.md
│   └── human-in-the-loop.md
│
├── 06-observability-and-eval/        — Knowing what happened
│   ├── tracing-an-agent-run.md
│   ├── metrics-that-matter.md
│   ├── evaluating-agents.md
│   ├── replay-and-debugging.md
│   └── regression-suites.md
│
├── 07-multi-agent-harness/           — More than one agent
│   ├── when-multi-agent-helps.md
│   ├── delegation-and-subagents.md
│   ├── message-passing.md
│   └── shared-state-and-conflicts.md
│
├── 08-production-harness/            — Running it for real
│   ├── deployment-shapes.md
│   ├── concurrency-and-queueing.md
│   ├── cost-control.md
│   ├── rate-limits-and-quotas.md
│   └── incident-response.md
│
├── 09-frameworks-landscape/          — What already exists
│   ├── build-vs-adopt.md
│   ├── langgraph.md
│   ├── openai-agents-sdk.md
│   ├── claude-agent-sdk.md
│   └── mcp-model-context-protocol.md
│
├── 10-interview-mastery/             — Explaining it out loud
│   ├── system-design-questions.md
│   ├── failure-story-framework.md
│   └── whiteboard-a-harness.md
│
└── projects/                         — Build the framework, piece by piece
    ├── p01-minimal-loop/
    ├── p02-tool-registry/
    ├── p03-context-manager/
    ├── p04-permission-layer/
    ├── p05-observability/
    ├── p06-subagents/
    ├── p07-durable-runs/
    └── p08-capstone-harness/
```

---

## How the projects work

Each project is a **working Python package** that adds one layer. By P08 they
compose into `minihar`, a small but complete harness you could actually ship.

| # | Project | Adds | Tests |
|---|---|---|---|
| 01 | Minimal loop | The turn cycle, budgets, termination | 13 |
| 02 | Tool registry | Schemas from code, validation, teaching errors | 18 |
| 03 | Context manager | Token budgets, assembly, compaction | 18 |
| 04 | Permission layer | Effect-based policy, injection containment | 18 |
| 05 | Observability | Traces, cost attribution, offline replay | 17 |
| 06 | Subagents | Delegation contracts, capped fan-out | 14 |
| 07 | Durable runs | Checkpoints, idempotent side effects | 16 |
| 08 | Capstone | All of it, wired together | 16 |

**130 tests, all passing, no API key required.** Tests drive a scripted fake
model — a harness is ordinary control-flow code and deserves fast deterministic
tests.

```bash
./run-all-tests.sh                                    # every project

cd projects/p01-minimal-loop && python -m pytest -q   # just one
```

Each project is self-contained, with its package at the project root, so run
pytest from inside the project directory rather than from the repo root.

---

## How to use this repo

**First pass** — read `01` end to end, then build `p01`. Do not skip to the
frameworks section; you will not understand what they are solving.

**Revision** — each topic file opens with an Intuition section and closes with
a "What to say out loud" section. On a revision pass, read only those two.

**Reference** — the failure taxonomy in `01` maps every later topic to the
failure it prevents. Start there when something breaks in your own system.

---

## The one idea

> The model is the least controllable part of your system.
> Everything else is yours. Engineer that.
