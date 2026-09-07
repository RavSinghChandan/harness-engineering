# Harness Engineering — Module 2
# Topic: Streaming and Partial Output

---

## 1. Intuition

A 60-second agent run with no output feels broken. The same run, showing what it
is doing as it happens, feels fast — even though it takes exactly as long.

Streaming is mostly a perception problem, and the cheapest win is not streaming
tokens at all. It is **streaming events**: "searching…", "reading 3 files…".
Those tell the user something true and cost you nothing.

---

## 2. Core Concept

### Two things you can stream

**Tokens** — the model's text, character by character. Familiar from chat.
**Events** — what the harness is doing. Far more useful for agents.

For a research agent, "Reading competitor pricing pages (2 of 5)" is worth more
than watching prose appear. Users want to know it is *working*, and roughly
*where* it is.

### The event stream

```python
def run_streaming(self, task: str):
    yield Event("run_started", task=task)

    while True:
        yield Event("thinking", turn=turn)
        reply = self.model(messages)

        if not reply.tool_calls:
            for chunk in reply.stream():          # tokens, at the end
                yield Event("token", text=chunk)
            yield Event("run_finished", reason="completed")
            return

        for call in reply.tool_calls:
            yield Event("tool_started", name=call.name, summary=describe(call))
            result = self.tools.execute(call)
            yield Event("tool_finished", name=call.name, ok=not result.startswith("Error"))
```

The user sees a live sequence of real steps. No new model capability required.

### What not to stream

**Intermediate reasoning.** It is often wrong, changes its mind, and mentions
things the final answer discards. Showing it makes the agent look confused even
when the answer is good.

**Tool arguments verbatim.** They may contain paths, ids or user data. Stream a
*summary*: "Searching orders" rather than the raw JSON.

**Partial writes.** Never tell the user something happened until it has.

---

## 3. Minimal Implementation

Server-sent events are usually the right transport — simpler than WebSockets and
sufficient for one-way updates:

```python
import json
from dataclasses import asdict, dataclass, field
import time


@dataclass
class Event:
    kind: str
    at: float = field(default_factory=time.time)
    data: dict = field(default_factory=dict)

    def to_sse(self) -> str:
        return f"event: {self.kind}\ndata: {json.dumps(asdict(self))}\n\n"


def sse_endpoint(task: str):
    """Flush per event; buffering defeats the entire purpose."""
    def generate():
        try:
            for event in harness.run_streaming(task):
                yield event.to_sse()
        except Exception as exc:
            # A stream that just stops is indistinguishable from a hang.
            yield Event("error", data={"message": str(exc)}).to_sse()
        finally:
            yield Event("done").to_sse()          # always terminate explicitly
    return StreamingResponse(generate(), media_type="text/event-stream")
```

The `finally` matters. A client waiting on a stream that silently ends will hang
until its own timeout, and the user sees a spinner forever.

---

## 4. Partial Results

When a budget trips mid-run, return what exists — clearly labelled:

```python
return {
    "output": best_effort_summary(state),
    "complete": False,                    # structural, not a comment
    "stop_reason": reason.value,
    "artefacts": state.files_written,     # real work already done
}
```

Three rules: never claim success, return the work, name the reason. Half a
research summary has value; a truncated one presented as finished is a lie.

---

## 5. Trade-offs

**Streaming complicates cancellation.** A client disconnect should stop the run,
so the generator needs to notice and set the interrupt flag — otherwise you keep
paying for output nobody is reading.

**Events leak internals.** "Calling internal_pricing_api" tells the user more
about your architecture than you meant. Map tool names to human phrases.

**Buffering kills it.** Proxies, gzip and frameworks all buffer by default. Test
through your real deployment path, not just locally.

---

## 6. Production Notes

- **Flush after every event**, and disable buffering at the proxy.
- **Always send a terminal event**, including on error.
- **Heartbeat every 15 seconds** during long tool calls, or intermediaries drop
  an idle connection.
- **Detect client disconnect and cancel the run.** Otherwise you pay for tokens
  nobody receives.
- **Log the event stream** alongside the trace; "what did the user actually see?"
  is a real support question.

---

## 7. What To Say Out Loud

> "For agents the useful thing to stream is events, not tokens — 'reading 3 of 5
> pages' tells the user more than watching prose appear, and it needs no special
> model support. I do not stream intermediate reasoning, because it is often
> wrong and changes its mind, which makes a good answer look confused. The
> stream always terminates explicitly, including on error, because a stream that
> just stops is indistinguishable from a hang. And a client disconnect cancels
> the run, or you keep paying for output nobody is reading."

---

## 8. Check Yourself

1. Why are events more useful than tokens for an agent?
2. Why not stream intermediate reasoning?
3. Why must the stream always send a terminal event?
4. What happens if you ignore client disconnects?
