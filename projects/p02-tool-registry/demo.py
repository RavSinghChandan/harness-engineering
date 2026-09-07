"""Watch schemas get generated, calls get validated, and errors teach.

    python demo.py

The theme: an error is a turn in a conversation, not the end of one.
"""
import json

from minihar import ErrorKind, Param, ToolError, ToolRegistry


registry = ToolRegistry()


def search_orders(query: str, limit: int = 5) -> str:
    """Search orders by text. Returns ids and one-line summaries.

    Use get_order for the full record of a specific id.
    """
    return f"3 orders matching {query!r} (showing {limit})"


def get_order(order_id: str) -> str:
    """Fetch one order by its exact id."""
    if not order_id.startswith("ORD-"):
        raise ToolError(
            tool="get_order",
            problem="malformed order id",
            received=order_id,
            suggestion="Ids look like ORD-1234. Use search_orders to find one.",
        )
    if order_id == "ORD-0000":
        raise ToolError(
            tool="get_order",
            problem="no such order",
            received=order_id,
            suggestion="Confirm the id with the customer.",
            kind=ErrorKind.TERMINAL,
        )
    return f"{order_id}: 2 items, shipped, £41.00"


def check_stock(sku: str) -> str:
    """Check warehouse stock. May be temporarily unavailable."""
    raise ToolError(
        tool="check_stock",
        problem="warehouse API unreachable",
        kind=ErrorKind.WAIT_AND_RETRY,
    )


# Every parameter must be described. The registry refuses to register a tool
# otherwise -- an undocumented parameter is a selection bug waiting to happen.
registry.register(
    search_orders,
    query=Param(description="Free-text search over order contents"),
    limit=Param(description="Max results to return, 1-20", minimum=1, maximum=20),
)
registry.register(
    get_order,
    order_id=Param(description="Exact order id, e.g. ORD-1234", pattern=r"^ORD-\d+$"),
)
registry.register(
    check_stock,
    sku=Param(description="Warehouse SKU, e.g. SKU-9"),
)


def rule(label):
    print(f"\n{'─' * 68}\n  {label}\n{'─' * 68}")


def demo_schemas():
    rule("1. Schemas generated from signatures + docstrings")
    schema = registry.schemas()[0]
    print(json.dumps(schema, indent=2)[:520])
    print("\n  note : nobody hand-wrote this JSON. The type hints, defaults and")
    print("         docstring produced it, so the schema cannot drift from the code.")


def demo_validation():
    rule("2. Validation happens before the function runs")
    for label, args in [
        ("missing required arg", {}),
        ("unknown arg",          {"query": "widgets", "colour": "red"}),
        ("wrong type",           {"query": "widgets", "limit": "five"}),
    ]:
        print(f"\n  {label}:")
        print(f"    {registry.execute('search_orders', args)}")
    print("\n  note : search_orders never executed. Bad calls stop at the gate.")


def demo_error_kinds():
    rule("3. Three error kinds, three different next moves")

    print("\n  FIX_AND_RETRY — the model can correct this itself:")
    print(f"    {registry.execute('get_order', {'order_id': '1234'})}")

    print("\n  WAIT_AND_RETRY — same call may work shortly:")
    print(f"    {registry.execute('check_stock', {'sku': 'SKU-9'})}")

    print("\n  TERMINAL — retrying is pointless, tell the user:")
    print(f"    {registry.execute('get_order', {'order_id': 'ORD-0000'})}")

    print("\n  note : each message ends with what to do next. 'Invalid input'")
    print("         would leave the model guessing, and it would guess wrong.")


def demo_unknown_tool():
    rule("4. Unknown tool names the real ones")
    print(f"  {registry.execute('find_order', {'q': 'x'})}")
    print("\n  note : the model now knows the actual vocabulary.")


def demo_loop_guard():
    rule("5. Loop guard — the same failing call, three times")

    # A fresh registry: the guard counts a consecutive streak, and earlier
    # demos already failed this tool once.
    guard_demo = ToolRegistry(repeat_limit=3)
    guard_demo.register(
        get_order,
        order_id=Param(description="Exact order id, e.g. ORD-1234"),
    )

    for attempt in range(1, 4):
        msg = guard_demo.execute("get_order", {"order_id": "bad-id"})
        print(f"  attempt {attempt}: {msg}")

    print("\n  note : attempts 1 and 2 got the helpful message. Attempt 3 hit")
    print("         the limit and told the model to stop and talk to the user.")

    good = guard_demo.execute("get_order", {"order_id": "ORD-77"})
    print(f"\n  then a success: {good}")
    after = guard_demo.execute("get_order", {"order_id": "bad-id"})
    print(f"  and the streak reset: {after}")
    print("\n  note : success clears the streak. A loop is consecutive failures,")
    print("         not a lifetime tally -- otherwise a long run trips falsely.")


def demo_happy_path():
    rule("6. A call that works")
    print(f"  {registry.execute('get_order', {'order_id': 'ORD-1234'})}")


if __name__ == "__main__":
    print("\n  P02 — TOOL REGISTRY")
    demo_schemas()
    demo_validation()
    demo_error_kinds()
    demo_unknown_tool()
    demo_loop_guard()
    demo_happy_path()
    print(f"\n{'─' * 68}")
    print("  Every failure above returned a string the model could act on.")
    print("  Not one of them raised into the loop.")
    print(f"{'─' * 68}\n")
