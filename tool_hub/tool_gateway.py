"""L7 · MCP Tool Hub — unified interface to 14 MCP servers."""
from __future__ import annotations

import os
import httpx
from dataclasses import dataclass


@dataclass
class MCPTool:
    name: str
    server_url: str
    description: str


REGISTERED_TOOLS: list[MCPTool] = [
    MCPTool("github",       "http://localhost:3001", "Repos, PRs, issues"),
    MCPTool("jira",         "http://localhost:3002", "Tickets, sprints"),
    MCPTool("confluence",   "http://localhost:3003", "Wiki, docs"),
    MCPTool("slack",        "http://localhost:3004", "Messages, alerts"),
    MCPTool("notion",       "http://localhost:3005", "Notes, databases"),
    MCPTool("figma",        "http://localhost:3006", "Designs, components"),
    MCPTool("linear",       "http://localhost:3007", "Issues, roadmap"),
    MCPTool("database",     "http://localhost:3008", "SQL queries, schema"),
    MCPTool("browser",      "http://localhost:3009", "Web scraping"),
    MCPTool("filesystem",   "http://localhost:3010", "Read/write files"),
    MCPTool("kubernetes",   "http://localhost:3011", "Cluster management"),
    MCPTool("aws",          "http://localhost:3012", "Cloud infra"),
    MCPTool("azure",        "http://localhost:3013", "Cloud infra"),
    MCPTool("gcp",          "http://localhost:3014", "Cloud infra"),
]


class MCPToolGateway:
    """Routes tool calls to the appropriate MCP server."""

    def __init__(self, timeout: int = 30) -> None:
        self._timeout = timeout
        self._tools: dict[str, MCPTool] = {t.name: t for t in REGISTERED_TOOLS}

    def list_tools(self) -> list[dict]:
        return [{"name": t.name, "description": t.description} for t in REGISTERED_TOOLS]

    def call(self, tool_name: str, method: str, params: dict) -> dict:
        tool = self._tools.get(tool_name)
        if not tool:
            raise ValueError(f"Unknown tool: {tool_name}. Available: {list(self._tools)}")
        with httpx.Client(timeout=self._timeout) as client:
            response = client.post(
                f"{tool.server_url}/mcp/{method}",
                json={"tool": tool_name, "params": params},
            )
            response.raise_for_status()
            return response.json()

    def health_check(self) -> dict[str, str]:
        results: dict[str, str] = {}
        for tool in REGISTERED_TOOLS:
            try:
                with httpx.Client(timeout=3) as client:
                    r = client.get(f"{tool.server_url}/health")
                    results[tool.name] = "ok" if r.status_code == 200 else "degraded"
            except Exception:
                results[tool.name] = "offline"
        return results
