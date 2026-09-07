"""Watch the loop stop four different ways.

    python demo.py

No API key. The "model" is a scripted function, so every run below is
deterministic -- which is the point. You are watching the harness, not the
model.
"""
from minihar import Harness, StopReason


# --- tools -----------------------------------------------------------------

def get_weather(city: str) -> str:
    return f"{city}: 18C, cloudy"


def flaky_tool() -> str:
    raise ConnectionError("upstream timed out")


TOOLS = {"get_weather": get_weather, "flaky_tool": flaky_tool}


# --- scripted models -------------------------------------------------------
# Each returns the next reply in a fixed sequence, ignoring the conversation.
# Real models are non-deterministic; for demonstrating the harness that would
# only add noise.

def scripted(*replies):
    """Return a model that emits these replies in order, then repeats the last."""
    state = {"i": 0}

    def model(messages):
        i = min(state["i"], len(replies) - 1)
        state["i"] += 1
        return replies[i]

    return model


def call(name, **arguments):
    return {"role": "assistant", "content": "", "tool_calls": [
        {"id": f"c{abs(hash(name)) % 1000}", "name": name, "arguments": arguments}
    ]}


def say(text):
    return {"role": "assistant", "content": text}


# --- the four exits --------------------------------------------------------

def show(label: str, result) -> None:
    print(f"\n{'─' * 68}")
    print(f"  {label}")
    print(f"{'─' * 68}")
    print(f"  stop_reason : {result.stop_reason.value}")
    print(f"  ok          : {result.ok}")
    print(f"  turns       : {result.turns}")
    print(f"  output      : {result.output[:60]}")


def demo_completed():
    """The happy path: tool call, then an answer."""
    model = scripted(
        call("get_weather", city="Bengaluru"),
        say("It is 18C and cloudy in Bengaluru."),
    )
    show("1. COMPLETED — the model answered",
         Harness(model=model, tools=TOOLS).run("weather in Bengaluru?"))


def demo_turn_budget():
    """Busy but never finishing. Each call differs, so no_progress never fires.

    This is the loop that progress detection cannot catch -- the model is
    genuinely doing new things, just never concluding. Only the turn cap saves
    you, which is why you need both guards and not just the clever one.
    """
    cities = ["Paris", "Lima", "Oslo", "Cairo", "Perth", "Delhi", "Tokyo"]
    model = scripted(*[call("get_weather", city=c) for c in cities])
    result = Harness(model=model, tools=TOOLS, max_turns=4, repeat_limit=3).run("weather?")
    show("2. TURN_BUDGET — every call different, so only the cap stops it", result)
    print("  note        : no_progress cannot fire; the calls are never identical")


def demo_no_progress():
    """Identical calls mean the model is stuck, not working."""
    model = scripted(call("get_weather", city="Paris"))
    result = Harness(model=model, tools=TOOLS, max_turns=50, repeat_limit=3).run("weather?")
    show("3. NO_PROGRESS — same call 3x, stopped at turn 3 not turn 50", result)
    print("  note        : max_turns was 50, so the cap would have burned 47")
    print("                more turns. Progress detection is the cheaper guard,")
    print("                but demo 2 shows why it is not sufficient alone.")


def demo_tool_error_is_not_fatal():
    """A tool raising does NOT end the run. The model reads the error."""
    model = scripted(
        call("flaky_tool"),
        say("The upstream service is down; try again shortly."),
    )
    result = Harness(model=model, tools=TOOLS).run("check the service")
    show("4. Tool raised — run still COMPLETED", result)

    tool_msg = [m for m in result.messages if m.get("role") == "tool"][0]
    print(f"  model saw   : {tool_msg['content']}")
    print("  note        : a crash became a conversation")


def demo_unknown_tool():
    """The error text names the real tools, so the model can correct itself."""
    model = scripted(
        call("get_wether", city="Paris"),      # typo
        call("get_weather", city="Paris"),     # corrected
        say("18C and cloudy."),
    )
    result = Harness(model=model, tools=TOOLS).run("weather?")
    show("5. Unknown tool — model recovered on the next turn", result)
    for m in result.messages:
        if m.get("role") == "tool":
            print(f"  tool msg    : {m['content'][:60]}")


if __name__ == "__main__":
    print("\n  P01 — MINIMAL LOOP")
    print("  Every run ends for a named reason. Here are all four.")
    demo_completed()
    demo_turn_budget()
    demo_no_progress()
    demo_tool_error_is_not_fatal()
    demo_unknown_tool()
    print(f"\n{'─' * 68}")
    print("  Four exits, all reachable, none of them a crash.")
    print(f"{'─' * 68}\n")
