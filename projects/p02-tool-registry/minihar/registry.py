"""Tool registration, schema generation, and validation.

The schema is the only interface the model has -- it cannot read the
implementation. So the schema is generated FROM the implementation, which stops
the two drifting apart.
"""
from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, get_args, get_origin, get_type_hints

from .errors import ErrorKind, ToolError


@dataclass(frozen=True)
class Param:
    """What the model needs to know about one parameter."""

    description: str
    minimum: int | None = None
    maximum: int | None = None
    pattern: str | None = None


@dataclass(frozen=True)
class Tool:
    fn: Callable[..., Any]
    params: dict[str, Param]

    @property
    def name(self) -> str:
        return self.fn.__name__

    def schema(self) -> dict[str, Any]:
        hints = get_type_hints(self.fn)
        properties: dict[str, Any] = {}
        required: list[str] = []

        for name, sig_param in inspect.signature(self.fn).parameters.items():
            note = self.params.get(name)
            if note is None:
                # Fail at import time. An undescribed parameter is a guaranteed
                # future bug, and the model can only see what we write here.
                raise ValueError(
                    f"{self.name}: parameter {name!r} has no description."
                )

            annotation = hints.get(name, str)
            entry: dict[str, Any] = {"description": note.description}

            if get_origin(annotation) is Literal:
                entry["type"] = "string"
                entry["enum"] = list(get_args(annotation))
            elif annotation is int:
                entry["type"] = "integer"
            elif annotation is bool:
                entry["type"] = "boolean"
            else:
                entry["type"] = "string"

            for key in ("minimum", "maximum", "pattern"):
                value = getattr(note, key)
                if value is not None:
                    entry[key] = value

            if sig_param.default is inspect.Parameter.empty:
                required.append(name)
            else:
                entry["default"] = sig_param.default

            properties[name] = entry

        return {
            "name": self.name,
            "description": inspect.getdoc(self.fn) or "",
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        }


@dataclass
class ToolRegistry:
    """Holds tools, validates calls against their schemas, and runs them."""

    repeat_limit: int = 3
    _tools: dict[str, Tool] = field(default_factory=dict)
    _error_counts: dict[tuple[str, str], int] = field(default_factory=dict)

    def register(self, fn: Callable[..., Any], **params: Param) -> Callable[..., Any]:
        tool = Tool(fn=fn, params=params)
        tool.schema()          # validate the schema now, not at first call
        self._tools[tool.name] = tool
        return fn

    def schemas(self) -> list[dict[str, Any]]:
        return [t.schema() for t in self._tools.values()]

    def execute(self, name: str, arguments: dict[str, Any] | None = None) -> str:
        """Validate then run. Always returns a string the model can read."""
        arguments = arguments or {}

        tool = self._tools.get(name)
        if tool is None:
            known = ", ".join(sorted(self._tools)) or "none"
            return ToolError(
                tool=name,
                problem="no such tool",
                suggestion=f"Available tools: {known}.",
                kind=ErrorKind.TERMINAL,
            ).as_message()

        try:
            self._validate(tool, arguments)
            result = str(tool.fn(**arguments))
        except ToolError as err:
            return self._maybe_loop_guard(err)
        except TypeError as exc:
            return ToolError(
                tool=name, problem="wrong arguments", received=str(exc)
            ).as_message()
        except Exception as exc:
            # Unexpected: a bug in our code, not a model mistake. A human needs
            # the stack trace; the model only needs a sentence.
            return ToolError(
                tool=name,
                problem=f"{type(exc).__name__}: {exc}",
                kind=ErrorKind.TERMINAL,
            ).as_message()
        else:
            # Success breaks the streak: the model is making progress again.
            self._error_counts = {
                k: v for k, v in self._error_counts.items() if k[0] != name
            }
            return result

    def _validate(self, tool: Tool, arguments: dict[str, Any]) -> None:
        schema = tool.schema()
        properties = schema["parameters"]["properties"]

        for missing in set(schema["parameters"]["required"]) - set(arguments):
            raise ToolError(
                tool=tool.name,
                problem=f"missing required parameter {missing!r}",
                suggestion=f"Add {missing!r}: {properties[missing]['description']}",
            )

        for key, value in arguments.items():
            spec = properties.get(key)
            if spec is None:
                raise ToolError(
                    tool=tool.name,
                    problem=f"unknown parameter {key!r}",
                    suggestion=f"Valid parameters: {', '.join(sorted(properties))}.",
                )

            if "enum" in spec and value not in spec["enum"]:
                raise ToolError(
                    tool=tool.name,
                    problem=f"{key!r} must be one of {spec['enum']}",
                    received=repr(value),
                )

            if spec["type"] == "integer":
                if not isinstance(value, int) or isinstance(value, bool):
                    raise ToolError(
                        tool=tool.name,
                        problem=f"{key!r} must be an integer",
                        received=repr(value),
                    )
                low, high = spec.get("minimum"), spec.get("maximum")
                if low is not None and value < low:
                    raise ToolError(
                        tool=tool.name,
                        problem=f"{key!r} must be at least {low}",
                        received=repr(value),
                    )
                if high is not None and value > high:
                    raise ToolError(
                        tool=tool.name,
                        problem=f"{key!r} must be at most {high}",
                        received=repr(value),
                    )

    def _maybe_loop_guard(self, err: ToolError) -> str:
        """The same error `repeat_limit` times running is a loop, not a retry.

        The count is per (tool, problem) and is cleared by any successful call
        to that tool -- see `execute`. Without that reset the counter would
        accumulate across unrelated parts of a long run and trip early on a
        model that had actually recovered in between.
        """
        key = (err.tool, err.problem)
        count = self._error_counts.get(key, 0) + 1
        self._error_counts[key] = count

        if count >= self.repeat_limit:
            return (
                f"Error in {err.tool}: {err.problem}. This has now failed "
                f"{count} times in a row with the same problem. Stop calling "
                "this tool and explain the situation to the user."
            )
        return err.as_message()
