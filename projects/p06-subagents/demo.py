"""Watch delegation work, and watch every way it goes wrong.

    python demo.py

A subagent is a contractor. You do not hand a contractor your keys and hope.
"""
import json

from minihar import Contract, DelegationResult, Delegator


def rule(label):
    print(f"\n{'─' * 68}\n  {label}\n{'─' * 68}")


class FakeSubagent:
    """Returns a canned string, and records what it was told."""

    def __init__(self, reply, tools=(), max_turns=0):
        self.reply, self.tools, self.max_turns = reply, tools, max_turns
        self.saw_prompt = ""

    def run(self, prompt):
        self.saw_prompt = prompt
        return self.reply


def delegator_returning(*replies, **kw):
    """A Delegator whose subagents emit these replies in order."""
    built = []
    queue = list(replies)

    def build(tools=(), max_turns=0):
        sub = FakeSubagent(queue.pop(0) if queue else "{}", tools, max_turns)
        built.append(sub)
        return sub

    d = Delegator(build_subagent=build, **kw)
    d.built = built
    return d


RESEARCH = Contract(
    goal="Find the refund policy for opened electronics",
    context="Customer bought a laptop 20 days ago, box opened.",
    constraints=("Read only -- do not modify anything",
                 "Cite the document id for every claim"),
    returns={"policy": "the rule in one sentence",
             "doc_id": "where you found it",
             "confidence": "high | medium | low"},
    max_turns=5,
    tools=("search_docs", "read_doc"),
)


def demo_the_contract():
    rule("1. The contract the subagent actually receives")
    print(RESEARCH.as_prompt())
    print("\n  note : the goal is self-contained. No 'the other one', no 'it'.")
    print("         A subagent never saw the parent's conversation, so any")
    print("         pronoun is a guess it has to make on your behalf.")


def demo_happy_path():
    rule("2. A subagent that honours the contract")
    good = json.dumps({"policy": "Opened electronics: 14 days, restocking fee.",
                       "doc_id": "POL-77", "confidence": "high"})
    d = delegator_returning(good)
    result = d.run(RESEARCH)

    print(f"  usable      : {result.usable}")
    print(f"  confidence  : {result.confidence}")
    print(f"  policy      : {result.data['policy']}")
    print(f"  doc_id      : {result.data['doc_id']}")
    print(f"\n  tools granted to the subagent: {d.built[0].tools}")
    print(f"  turn cap given to it         : {d.built[0].max_turns}")
    print("\n  note : it got two read tools, not the parent's full set. The")
    print("         constraint 'read only' is in the prompt AND in the grant.")
    print("         The prompt is the suggestion; the grant is the guarantee.")


def demo_wrong_shape():
    rule("3. A subagent that answers in prose instead of the shape")
    d = delegator_returning("Sure! The policy is 14 days for opened electronics.")
    result = d.run(RESEARCH)

    print(f"  usable      : {result.usable}")
    print(f"  error       : {result.error}")
    print(f"  raw kept    : {result.raw[:56]!r}")
    print("\n  note : a helpful sentence that the supervisor cannot parse. It is")
    print("         marked unusable rather than being pattern-matched with a")
    print("         regex, because guessing here is how wrong data spreads.")


def demo_missing_keys():
    rule("4. A subagent that returns most of the shape")
    partial = json.dumps({"policy": "14 days.", "confidence": "high"})   # no doc_id
    result = delegator_returning(partial).run(RESEARCH)

    print(f"  usable      : {result.usable}")
    print(f"  error       : {result.error}")
    print(f"  data kept   : {result.data}")
    print("\n  note : the policy text is probably right. It is still not usable,")
    print("         because the citation is missing and an uncited claim is")
    print("         exactly what the contract existed to prevent.")


def demo_low_confidence():
    rule("5. A subagent that admits it could not finish")
    honest = json.dumps({"policy": "", "doc_id": "",
                         "confidence": "low"})
    result = delegator_returning(honest).run(RESEARCH)

    print(f"  usable      : {result.usable}")
    print(f"  confidence  : {result.confidence}")
    print("\n  note : this is a SUCCESS of the design. The contract told it to")
    print("         return low confidence rather than invent an answer, and the")
    print("         supervisor now knows to try something else instead of")
    print("         building on a fabrication.")


def demo_fan_out_cap():
    rule("6. The fan-out cap — delegation without limits is a fork bomb")
    good = json.dumps({"policy": "p", "doc_id": "d", "confidence": "high"})
    d = delegator_returning(*[good] * 10, max_subagents=3)

    for i in range(1, 6):
        r = d.run(RESEARCH)
        state = "ran" if r.usable else f"refused ({r.error})"
        print(f"  request {i}: {state}")

    print(f"\n  subagents actually spawned: {d.spawned}")
    print("\n  note : an agent that can delegate can delegate in a loop. Each")
    print("         child costs a full context of its own, so uncapped fan-out")
    print("         is the most expensive bug in this repo.")


def demo_depth_cap():
    rule("7. The depth cap — the telephone game has a limit")
    good = json.dumps({"policy": "p", "doc_id": "d", "confidence": "high"})
    d = delegator_returning(*[good] * 5, max_depth=2)

    for depth in range(4):
        r = d.run(RESEARCH, depth=depth)
        print(f"  depth {depth}: {'allowed' if r.usable else 'refused — ' + r.error}")

    print("\n  note : every hop paraphrases. By depth 3 the task being done is")
    print("         two paraphrases from what the user asked, and nobody in the")
    print("         chain can tell. Depth one is the sane default.")


def demo_the_log():
    rule("8. The log is what makes drift visible")
    good = json.dumps({"policy": "14 days.", "doc_id": "POL-77", "confidence": "high"})
    bad = "I think it is probably about two weeks?"
    d = delegator_returning(good, bad)
    d.run(RESEARCH)
    d.run(RESEARCH)

    for entry in d.log:
        print(f"  goal      : {entry['goal'][:44]}")
        print(f"    returned  : {entry['returned']}")
        print(f"    confidence: {entry['confidence']}  error: {entry['error'] or '—'}")

    print("\n  note : both sides logged. 'The multi-agent system gave a wrong")
    print("         answer' is unanswerable without this; with it you can see")
    print("         which child drifted and what it was actually asked.")


if __name__ == "__main__":
    print("\n  P06 — SUBAGENTS")
    demo_the_contract()
    demo_happy_path()
    demo_wrong_shape()
    demo_missing_keys()
    demo_low_confidence()
    demo_fan_out_cap()
    demo_depth_cap()
    demo_the_log()
    print(f"\n{'─' * 68}")
    print("  A subagent is a contractor: narrow scope, fewer keys, checked work.")
    print(f"{'─' * 68}\n")
