"""F2 · Integration Test Agent — writes integration and contract tests."""
from __future__ import annotations
import time
from agents.base import BaseAgent, AgentTask, AgentResult
from core.model_router import ModelTier


class IntegrationTestAgent(BaseAgent):
    name = "integration_test"
    skill_tasks = ["testing", "quality_assurance"]
    swarm = "qa"
    default_tier = ModelTier.CODE

    @property
    def system_prompt(self) -> str:
        return (
            "You are the Integration Test Agent. You write tests that validate interactions "
            "between services: API contract tests, database integration tests, "
            "event-driven flow tests, and end-to-end scenario tests. "
            "Return JSON: test_files (list of {path, content}), "
            "test_environment_requirements, docker_compose_override."
        )

    def run(self, task: AgentTask) -> AgentResult:
        t0 = time.monotonic()
        api_spec = task.parameters.get("api_spec", {})
        services = task.parameters.get("services", [])
        result = self._llm_json(
            f"Write integration tests for services: {services}\nAPI: {api_spec}"
        )
        return self._make_result(task, result, confidence=0.82,
                                 duration_ms=(time.monotonic() - t0) * 1000)
