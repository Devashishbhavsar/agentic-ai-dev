"""D4 · API Agent — designs OpenAPI specs and generates API contracts."""
from __future__ import annotations
import time
from agents.base import BaseAgent, AgentTask, AgentResult
from core.model_router import ModelTier


class APIAgent(BaseAgent):
    name = "api"
    swarm = "sw_eng"
    default_tier = ModelTier.BALANCED

    @property
    def system_prompt(self) -> str:
        return (
            "You are the API Agent. You design RESTful and GraphQL APIs: "
            "endpoints, request/response schemas, authentication, versioning, "
            "rate limiting, and OpenAPI 3.1 specs. "
            "Return JSON: openapi_spec (dict), breaking_changes (list), "
            "migration_guide, sdk_generation_command."
        )

    def run(self, task: AgentTask) -> AgentResult:
        t0 = time.monotonic()
        resources = task.parameters.get("resources", [])
        auth_scheme = task.parameters.get("auth_scheme", "bearer")
        result = self._llm_json(
            f"Design API for resources: {resources}\nAuth: {auth_scheme}"
        )
        return self._make_result(task, result, confidence=0.85,
                                 duration_ms=(time.monotonic() - t0) * 1000)
