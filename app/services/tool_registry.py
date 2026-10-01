from __future__ import annotations

from typing import Any, Protocol


class Tool(Protocol):
    name: str
    description: str

    def run(self, args: dict[str, Any]) -> dict[str, Any]:
        ...


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        tool = self._tools.get(name)
        if tool is None:
            raise KeyError(f"Tool '{name}' is not registered.")
        return tool

    def invoke(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        tool = self._tools.get(name)
        if tool is None:
            raise KeyError(f"Tool '{name}' is not registered.")
        return tool.run(args)

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())
