"""minihar — tool registry: schemas, validation, and errors the model can act on."""
from .errors import ErrorKind, ToolError
from .registry import Param, Tool, ToolRegistry

__all__ = ["ErrorKind", "ToolError", "Param", "Tool", "ToolRegistry"]
