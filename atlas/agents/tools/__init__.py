"""SP07: tool registry for specialist agents.

Public surface:
- ``Tool``: dataclass describing a callable tool with JSON Schema parameters.
- ``build_registry(engine)``: returns ``dict[str, Tool]`` bound to ``engine``.
- ``TOOL_NAMES``: tuple of the 10 v1 tool names (load-bearing for tests).
"""

from atlas.agents.tools.registry import TOOL_NAMES, Tool, build_registry

__all__ = ["TOOL_NAMES", "Tool", "build_registry"]
