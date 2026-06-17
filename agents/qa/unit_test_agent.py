"""F1 · Unit Test Agent — generates unit tests for code artifacts."""
from __future__ import annotations
import time
from agents.base import BaseAgent, AgentTask, AgentResult
from core.model_router import ModelTier


class UnitTestAgent(BaseAgent):
    name = "unit_test"
    skill_tasks = ["testing", "quality_assurance"]
    swarm = "qa"
    default_tier = ModelTier.CODE

    @property
    def system_prompt(self) -> str:
        return (
            "You are the Unit Test Agent. You write pytest unit tests with high coverage: "
            "happy path, edge cases, error conditions, and boundary values. "
            "Use fixtures, parametrize, and mock external dependencies. "
            "Return JSON: test_files (list of {path, content}), "
            "coverage_target_pct, commands, edge_cases_covered."
        )

    def run(self, task: AgentTask) -> AgentResult:
        t0 = time.monotonic()
        code = task.parameters.get("code", "")
        result = self._llm_json(f"Generate unit tests for:\n\n{code}")
        return self._make_result(task, result, confidence=0.85,
                                 duration_ms=(time.monotonic() - t0) * 1000)
