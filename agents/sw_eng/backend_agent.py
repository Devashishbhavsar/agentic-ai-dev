"""D2 · Backend Agent — generates backend service code."""
from __future__ import annotations
import time
from agents.base import BaseAgent, AgentTask, AgentResult
from core.model_router import ModelTier


class BackendAgent(BaseAgent):
    name = "backend"
    skill_tasks = ["sw_delivery", "testing", "debugging"]
    swarm = "sw_eng"
    default_tier = ModelTier.CODE

    @property
    def system_prompt(self) -> str:
        return (
            "You are the Backend Agent. You generate production-quality backend code: "
            "FastAPI/Django REST APIs, database models, business logic, auth middleware, "
            "background tasks, and error handling. Follow SOLID principles. "
            "Return JSON: files (list of {path, content}), dependencies, "
            "setup_instructions, test_commands."
        )

    def run(self, task: AgentTask) -> AgentResult:
        t0 = time.monotonic()
        spec = task.parameters.get("spec", {})
        tech_stack = task.parameters.get("tech_stack", "fastapi+sqlalchemy")
        result = self._llm_json(
            f"Generate backend code.\nSpec: {spec}\nStack: {tech_stack}"
        )
        return self._make_result(task, result, confidence=0.78,
                                 duration_ms=(time.monotonic() - t0) * 1000)
