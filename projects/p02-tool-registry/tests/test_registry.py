"""Tool registry tests. All of these guard F3 (tool misuse).

The assertions check the CONTENT of error messages, not just that an error
happened -- because the content is what the model acts on.
"""
from typing import Literal

import pytest

from minihar import Param, ToolError, ToolRegistry


def orders_registry() -> ToolRegistry:
    reg = ToolRegistry()

    def search_orders(
        query: str,
        max_results: int = 5,
        status: Literal["pending", "shipped", "delivered", "cancelled"] = "pending",
    ) -> str:
        """Search a customer's past orders.

        Use when the user asks about an order they cannot find. For a specific
        known order ID, use get_order instead.
        """
        return f"{max_results} {status} orders matching {query!r}"

    reg.register(
        search_orders,
        query=Param("Free-text over product names, e.g. 'blue running shoes'"),
        max_results=Param("How many orders to return", minimum=1, maximum=20),
        status=Param("Filter by order status"),
    )
    return reg


# ── schema generation ────────────────────────────────────────────────────────

def test_schema_is_generated_from_the_signature():
    schema = orders_registry().schemas()[0]
    assert schema["name"] == "search_orders"
    assert "use get_order instead" in schema["description"].lower()


def test_literal_becomes_an_enum():
    """An enum makes the wrong value impossible to express."""
    props = orders_registry().schemas()[0]["parameters"]["properties"]
    assert props["status"]["enum"] == ["pending", "shipped", "delivered", "cancelled"]


def test_bounds_and_defaults_reach_the_schema():
    props = orders_registry().schemas()[0]["parameters"]["properties"]
    assert props["max_results"]["minimum"] == 1
    assert props["max_results"]["maximum"] == 20
    assert props["max_results"]["default"] == 5


def test_only_parameters_without_defaults_are_required():
    schema = orders_registry().schemas()[0]
    assert schema["parameters"]["required"] == ["query"]


def test_undescribed_parameter_fails_at_registration():
    """Fail now, loudly, rather than in production."""
    reg = ToolRegistry()

    def broken(a: str, b: str) -> str:
        """Missing a description for b."""
        return a

    with pytest.raises(ValueError, match="'b' has no description"):
        reg.register(broken, a=Param("the a"))


# ── validation: every message must teach ─────────────────────────────────────

def test_missing_required_parameter_says_what_to_add():
    out = orders_registry().execute("search_orders", {})
    assert "missing required parameter 'query'" in out
    assert "blue running shoes" in out, "should quote the parameter description"


def test_bad_enum_lists_the_valid_values():
    out = orders_registry().execute(
        "search_orders", {"query": "shoes", "status": "in-transit"}
    )
    assert "must be one of" in out
    assert "shipped" in out
    assert "'in-transit'" in out, "should echo what it received"


def test_out_of_range_integer_states_the_bound():
    out = orders_registry().execute(
        "search_orders", {"query": "shoes", "max_results": 500}
    )
    assert "at most 20" in out and "500" in out


def test_unknown_parameter_lists_the_valid_ones():
    out = orders_registry().execute("search_orders", {"query": "x", "colour": "blue"})
    assert "unknown parameter 'colour'" in out
    assert "max_results" in out


def test_unknown_tool_is_terminal_and_lists_alternatives():
    out = orders_registry().execute("teleport", {})
    assert "no such tool" in out
    assert "search_orders" in out
    assert "Do not retry" in out, "inventing a tool is not worth retrying"


def test_a_valid_call_just_works():
    out = orders_registry().execute(
        "search_orders", {"query": "shoes", "max_results": 3, "status": "shipped"}
    )
    assert out == "3 shipped orders matching 'shoes'"


# ── the loop guard ───────────────────────────────────────────────────────────

def test_the_same_error_three_times_is_treated_as_a_loop():
    """Helpful errors invite retries; something must stop an unfixable one."""
    reg = orders_registry()
    bad = {"query": "shoes", "status": "in-transit"}

    first = reg.execute("search_orders", bad)
    second = reg.execute("search_orders", bad)
    third = reg.execute("search_orders", bad)

    assert "Stop calling this tool" not in first
    assert "Stop calling this tool" not in second
    assert "Stop calling this tool" in third


def test_different_errors_do_not_share_a_counter():
    reg = orders_registry()
    for _ in range(2):
        reg.execute("search_orders", {"query": "x", "status": "nope"})
        reg.execute("search_orders", {})
    assert "Stop calling this tool" not in reg.execute(
        "search_orders", {"query": "x", "max_results": 999}
    )


# ── error kinds ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    ("arguments", "expected_phrase"),
    [
        pytest.param({}, "missing required parameter", id="missing-required"),
        pytest.param({"query": "x", "status": "bad"}, "must be one of", id="bad-enum"),
        pytest.param({"query": "x", "max_results": 0}, "at least 1", id="below-minimum"),
        pytest.param({"query": "x", "max_results": "five"}, "must be an integer", id="wrong-type"),
    ],
)
def test_every_validation_failure_explains_itself(arguments, expected_phrase):
    assert expected_phrase in orders_registry().execute("search_orders", arguments)


def test_a_raising_tool_does_not_escape():
    reg = ToolRegistry()

    def explode(x: str) -> str:
        """Always fails."""
        raise RuntimeError("boom")

    reg.register(explode, x=Param("anything"))
    out = reg.execute("explode", {"x": "hi"})
    assert "RuntimeError: boom" in out
    assert "Do not retry" in out


# --- the loop guard --------------------------------------------------------
#
# The same error repeating means the model is not learning from it. These tests
# were added after a demo showed the counter tripping early and reporting an
# inflated count, because it accumulated across the whole registry lifetime
# rather than counting a consecutive streak.


def flaky_registry(repeat_limit: int = 3) -> ToolRegistry:
    """A registry whose tool fails on a bad id and succeeds on a good one."""
    reg = ToolRegistry(repeat_limit=repeat_limit)

    def get_order(order_id: str) -> str:
        """Fetch one order."""
        if not order_id.startswith("ORD-"):
            raise ToolError(
                tool="get_order", problem="malformed order id", received=order_id
            )
        return f"{order_id}: ok"

    reg.register(get_order, order_id=Param("Order id like ORD-1234"))
    return reg


def test_loop_guard_stays_quiet_below_the_limit():
    reg = flaky_registry(repeat_limit=3)
    for _ in range(2):
        assert "failed" not in reg.execute("get_order", {"order_id": "bad"})


def test_loop_guard_fires_exactly_on_the_limit():
    reg = flaky_registry(repeat_limit=3)
    messages = [reg.execute("get_order", {"order_id": "bad"}) for _ in range(3)]

    assert "failed" not in messages[0]
    assert "failed" not in messages[1]
    assert "3 times in a row" in messages[2]
    assert "Stop calling this tool" in messages[2]


def test_loop_guard_counts_the_streak_not_the_lifetime():
    """A success in between resets the count -- the model recovered."""
    reg = flaky_registry(repeat_limit=3)

    reg.execute("get_order", {"order_id": "bad"})       # streak 1
    reg.execute("get_order", {"order_id": "bad"})       # streak 2
    reg.execute("get_order", {"order_id": "ORD-1"})     # success: streak cleared

    # Without the reset this next call would be the 3rd failure and would trip.
    assert "failed" not in reg.execute("get_order", {"order_id": "bad"})


def test_loop_guard_is_per_problem_not_per_tool():
    """Two different problems on one tool are not one loop."""
    reg = ToolRegistry(repeat_limit=2)

    def check(mode: str) -> str:
        """Fails differently depending on mode."""
        raise ToolError(tool="check", problem=f"problem-{mode}")

    reg.register(check, mode=Param("Which failure to raise"))

    assert "failed" not in reg.execute("check", {"mode": "a"})
    assert "failed" not in reg.execute("check", {"mode": "b"})   # different problem
    assert "2 times in a row" in reg.execute("check", {"mode": "a"})
