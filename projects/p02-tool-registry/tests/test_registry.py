"""Tool registry tests. All of these guard F3 (tool misuse).

The assertions check the CONTENT of error messages, not just that an error
happened -- because the content is what the model acts on.
"""
from typing import Literal

import pytest

from minihar import Param, ToolRegistry


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
