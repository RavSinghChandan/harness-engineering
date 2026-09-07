"""Watch a run get traced, costed, redacted, and then replayed for free.

    python demo.py

The last section is the important one: a bug reproduced with no model call.
"""
import tempfile
from pathlib import Path

from minihar import (Event, EventType, Recording, RecordingModel, ReplayModel,
                     ReplayExhausted, Tracer)


def rule(label):
    print(f"\n{'─' * 68}\n  {label}\n{'─' * 68}")


def traced_run() -> Tracer:
    """A representative run: two tools, one denial, one compaction."""
    tracer = Tracer(run_id="a1b2c3d4")

    tracer.record(0, EventType.RUN_START, input="Refund my last order")
    tracer.record(1, EventType.MODEL_CALL, name="opus-5",
                  output="I'll look up the order.", tokens=1_200,
                  cost_usd=0.0036, duration_ms=890)
    tracer.record(1, EventType.TOOL_CALL, name="search_orders",
                  input='{"query": "last order"}',
                  output="ORD-1234: £41.00, shipped", duration_ms=45)
    tracer.record(2, EventType.MODEL_CALL, name="opus-5",
                  output="I'll issue the refund.", tokens=1_450,
                  cost_usd=0.0044, duration_ms=1_120)
    tracer.record(2, EventType.DENIED, name="issue_refund",
                  input='{"order_id": "ORD-1234"}',
                  error="Refunds over £40 need human approval")
    tracer.record(3, EventType.MODEL_CALL, name="haiku-4.5",
                  output="Escalating to a human.", tokens=900,
                  cost_usd=0.0002, duration_ms=310)
    tracer.record(3, EventType.TOOL_CALL, name="escalate",
                  input='{"reason": "refund over limit"}',
                  output="Ticket T-88 created", duration_ms=2_400)
    tracer.record(3, EventType.RUN_END, output="Escalated to a human.")
    return tracer


def demo_tree():
    rule("1. The run as a tree")
    print(traced_run().as_tree())
    print("  note : stored flat (one event per line, ships to any log pipeline);")
    print("         the tree is reconstructed from turn numbers for humans.")


def demo_metrics():
    rule("2. What the trace can answer without re-running anything")
    t = traced_run()

    print(f"  total cost      : ${t.cost():.4f}")
    print(f"  total tokens    : {t.tokens():,}")
    print(f"  cost by model   : " + ", ".join(f"{k} ${v:.4f}" for k, v in t.cost_by_model().items()))
    print(f"  tool call counts: {t.tool_counts()}")
    print(f"  errors/denials  : {[e.name for e in t.errors()]}")
    print(f"\n  slowest steps:")
    for e in t.slowest(3):
        print(f"    {e.duration_ms:>6}ms  {e.type.value:<12} {e.name}")

    print("\n  note : cost_by_model is what tells you a cheap-model routing")
    print("         change actually worked. Aggregate spend would hide it.")


def demo_redaction():
    rule("3. Secrets never reach the trace")
    t = Tracer(run_id="redact01")
    t.record(1, EventType.TOOL_CALL, name="login",
             input='{"user": "rav", "password": "hunter2", "api_key": "sk-live-abc123"}',
             output='{"token": "eyJhbGciOi", "status": "ok"}')

    print(f"  recorded input : {t.events[0].input}")
    print(f"  recorded output: {t.events[0].output}")
    print("\n  note : redaction happens in `record`, so it cannot be forgotten at")
    print("         a call site. A trace is a log, and logs get shipped, indexed")
    print("         and read by people who should not see credentials.")


def demo_truncation():
    rule("4. Big payloads are clipped, not stored whole")
    t = Tracer(run_id="clip0001", truncate_at=120)
    t.record(1, EventType.TOOL_CALL, name="fetch_report",
             output="x" * 5_000)

    stored = t.events[0].output
    print(f"  tool returned : 5,000 chars")
    print(f"  trace stored  : {len(stored)} chars")
    print(f"  ends with     : ...{stored[-40:]!r}")
    print("\n  note : without a clip, one agent reading a large file puts")
    print("         megabytes per run into your logging bill.")


def demo_replay():
    rule("5. Record once, replay forever — free and deterministic")

    # --- record: this is the only part that would cost money in real life ---
    scripted_replies = [
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "c1", "name": "search_orders", "arguments": {"query": "blender"}}]},
        {"role": "assistant", "content": "Your blender order is ORD-1234."},
    ]
    step = {"i": 0}

    def expensive_model(messages):
        reply = scripted_replies[step["i"]]
        step["i"] += 1
        return reply

    recording = Recording(run_id="a1b2c3d4", task="find my blender order",
                          harness_version="p05-demo")
    recorder = RecordingModel(inner=expensive_model, recording=recording)

    recorder([{"role": "user", "content": recording.task}])
    recorder([{"role": "user", "content": "..."}])
    recording.stop_reason = "completed"

    print(f"  recorded {len(recording.model_replies)} model replies")

    with tempfile.TemporaryDirectory() as tmp:
        path = recording.save(directory=tmp, label="blender-lookup")
        print(f"  saved to      : {path.name}")

        loaded = Recording.load(path)
        print(f"  loaded back   : task={loaded.task!r}, version={loaded.harness_version!r}")

        # --- replay: no network, no cost, identical every time ---
        replay = ReplayModel(recording=loaded)
        first = replay([{"role": "user", "content": "anything"}])
        second = replay([{"role": "user", "content": "anything"}])

        print(f"\n  replay call 1 : {first['tool_calls'][0]['name']}")
        print(f"  replay call 2 : {second['content']}")
        print(f"  exhausted     : {replay.exhausted}")

        try:
            replay([{"role": "user", "content": "one too many"}])
        except ReplayExhausted as exc:
            print(f"\n  one more call : ReplayExhausted")
            print(f"    {exc}")

    print("\n  note : that last error is the useful one. It means the harness")
    print("         under test is making MORE calls than the recording holds --")
    print("         a behaviour change, which is exactly what you want CI to")
    print("         catch. The model's decisions are frozen; your code is not.")


if __name__ == "__main__":
    print("\n  P05 — OBSERVABILITY")
    demo_tree()
    demo_metrics()
    demo_redaction()
    demo_truncation()
    demo_replay()
    print(f"\n{'─' * 68}")
    print("  If you cannot replay it, you cannot debug it -- you can only guess.")
    print(f"{'─' * 68}\n")
