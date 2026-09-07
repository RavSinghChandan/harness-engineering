# Harness Engineering — Module 9
# Topic: Claude Agent SDK

---

## 1. Intuition

The Claude Agent SDK is the harness behind Claude Code, made available as a
library. That origin is the most useful thing to know about it: it was not
designed as a general agent abstraction, it was extracted from a production
agent that does long, file-touching, permission-sensitive work.

So the things it takes seriously are the things that hurt in that setting —
permissions, context compaction, subagents — rather than graph topology.

---

## 2. What It Actually Gives You

| Harness concern | The SDK's answer |
|---|---|
| Loop control | Built in, with turn limits |
| Tools | Built-in file, bash and search tools, plus your own |
| Permissions | **First class** — modes, allow/deny lists, a callback hook |
| Context | Automatic compaction when the window fills |
| Subagents | First class, with their own tools and prompts |
| MCP | Native client — external tool servers |
| Hooks | Pre and post tool-use interception |
| Observability | Structured message stream |
| Durability | Session resumption; not full checkpointing |

Permissions being first class is the differentiator. Most frameworks leave the
entire content of Module 5 to you; this one ships an effect-aware model.

---

## 3. The Shape

```python
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions

options = ClaudeAgentOptions(
    system_prompt="You are a code review assistant.",
    allowed_tools=["Read", "Grep", "Glob"],          # a whitelist, in code
    permission_mode="acceptEdits",                    # default | acceptEdits | plan
    max_turns=20,
    cwd="/path/to/repo",
)

async with ClaudeSDKClient(options=options) as client:
    await client.query("Review the changes on this branch")
    async for message in client.receive_response():
        handle(message)
```

The `allowed_tools` whitelist is enforcement, not instruction. A tool absent
from that list cannot be called however the model is prompted — which is
precisely the property Module 5 argues for.

### The permission callback

The more interesting hook is programmatic decisions per call:

```python
async def can_use_tool(tool_name: str, tool_input: dict, context) -> dict:
    if tool_name == "Bash" and "rm -rf" in tool_input.get("command", ""):
        return {"behavior": "deny", "message": "Destructive command blocked."}

    if tool_name == "Write" and not is_inside(tool_input["file_path"], REPO_ROOT):
        return {"behavior": "deny", "message": "Writes are limited to the repository."}

    if tool_name == "Write" and is_sensitive(tool_input["file_path"]):
        return {"behavior": "ask", "message": f"Modify {tool_input['file_path']}?"}

    return {"behavior": "allow"}
```

Three behaviours — allow, deny, ask — matching the effect model from Module 5.
This is where your policy lives, and it is a real enforcement point rather than
a suggestion.

### Subagents

```python
options = ClaudeAgentOptions(
    agents={
        "researcher": {
            "description": "Searches and summarises. Read-only.",
            "prompt": "Find relevant information. Do not modify anything.",
            "tools": ["Read", "Grep", "WebSearch"],     # narrowed, enforced
        },
    },
)
```

Note the subagent's tool list is enforced, not requested. "Do not modify
anything" in the prompt is the suggestion; the absent write tool is the
guarantee. Both are present, which is the correct pattern from Module 7.

---

## 4. What You Still Own

**Cost budgets.** `max_turns` bounds turns, not dollars. Track token usage from
the message stream and stop on spend.

**Domain permission policy.** The mechanism is provided; the rules are yours.
Which paths, which commands, which amounts — all of that is your callback.

**Business-level evaluation.** The message stream gives you the raw material;
the eval suite from Module 6 is still yours to write.

**Durability across processes.** Session resumption exists, but if you need
checkpoint-and-resume-anywhere in a worker pool, build it on top.

---

## 5. Trade-offs

**Opinionated.** It works the way Claude Code works: filesystem-oriented,
long-running, tool-heavy. Aligned with that shape, you get a lot free. Against
it, you are fighting the grain.

**Automatic compaction is convenient and opaque.** Something you needed can be
summarised away. Keep critical facts in structured state you re-inject, exactly
as Module 4 prescribes — do not rely on the transcript surviving.

**Provider-specific.** Claude models. That is the trade.

**Built-in tools are powerful.** `Bash` in particular is close to arbitrary
execution. Whitelist deliberately and use the permission callback; do not enable
it broadly and hope.

---

## 6. When To Choose It

Choose it for **file-touching, long-running, permission-sensitive** work —
coding agents, repository automation, anything operating on a real filesystem
where an unguarded write is expensive.

The permission model and compaction are worth real money in that setting. For a
short API-calling agent with three tools, it is more machinery than the task
needs.

---

## 7. What To Say Out Loud

> "The Claude Agent SDK is the harness from Claude Code as a library, so it takes
> seriously the things that hurt in that setting: permissions, compaction and
> subagents. Permissions are first class — an enforced tool whitelist plus a
> per-call callback returning allow, deny or ask, which maps directly onto the
> effect model I would build anyway. Subagents get narrowed tool lists that are
> enforced rather than requested. What I still own is cost budgets, since
> `max_turns` bounds turns and not dollars, and the domain policy itself — the
> mechanism is given, the rules are mine. I also keep critical facts in
> structured state rather than trusting the transcript, because automatic
> compaction is convenient and opaque."

---

## 8. Check Yourself

1. Why is `allowed_tools` enforcement rather than instruction?
2. What are the three permission behaviours, and how do they map to effects?
3. What does `max_turns` fail to bound?
4. Why keep critical facts outside the transcript despite automatic compaction?

→ Next: [`mcp-model-context-protocol.md`](mcp-model-context-protocol.md)
