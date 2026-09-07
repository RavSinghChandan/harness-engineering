# Projects

Eight layers that compose into `minihar`, a working harness.

Build them in order. Each assumes the previous one exists, and each maps to
failures in [`../01-harness-fundamentals/failure-taxonomy.md`](../01-harness-fundamentals/failure-taxonomy.md).

| # | Project | Adds | Prevents |
|---|---|---|---|
| 01 | [minimal-loop](p01-minimal-loop/) | Turn cycle, budgets, tool dispatch | F1 F2 F3 F8 |
| 02 | tool-registry | Schemas, validation, typed errors | F3 F7 |
| 03 | context-manager | Token budget, compaction, tiers | F4 F9 |
| 04 | permission-layer | Policy, confirmation, sandboxing | F5 F6 |
| 05 | observability | Traces, metrics, replay | F7 F8 |
| 06 | subagents | Delegation, isolation, contracts | F12 |
| 07 | durable-runs | Persistence, resumption, idempotency | F10 F11 |
| 08 | capstone-harness | All of it, wired together | — |

## Convention

Every project is a standalone Python package with its own tests and README.
Tests use a **scripted fake model** — no API key, no network, no flakiness. A
harness is ordinary control-flow code and should be tested like it.

```bash
cd projects/pNN-name && python -m pytest tests/ -q
```
