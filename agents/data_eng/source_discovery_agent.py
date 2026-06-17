"""B1 · Source Discovery Agent — discovers available data sources and their schemas."""
from __future__ import annotations
import time
from agents.base import BaseAgent, AgentTask, AgentResult
from core.model_router import ModelTier


class SourceDiscoveryAgent(BaseAgent):
    name = "source_discovery"
    swarm = "data_eng"
    default_tier = ModelTier.BALANCED

    @property
    def system_prompt(self) -> str:
        return (
            "You are the Source Discovery Agent. You identify and profile available data sources "
            "(databases, warehouses, files, APIs). For each source you document: connection details, "
            "schema overview, row counts, freshness, access level, and relevance to the request. "
            "Return JSON: sources (list of {name, type, connection_string_template, "
            "schemas, estimated_rows, last_updated, relevance_score})."
        )

    def run(self, task: AgentTask) -> AgentResult:
        t0 = time.monotonic()
        query = task.parameters.get("query", "")
        available_sources = task.parameters.get("available_sources", [])
        result = self._llm_json(
            f"Discover relevant sources for: '{query}'\nAvailable: {available_sources}"
        )
        return self._make_result(task, result, confidence=0.85,
                                 duration_ms=(time.monotonic() - t0) * 1000)
