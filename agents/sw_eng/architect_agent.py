"""D1 · Solution Architect Agent — designs system architecture for software delivery."""
from __future__ import annotations
import time
from agents.base import BaseAgent, AgentTask, AgentResult
from core.model_router import ModelTier


class ArchitectAgent(BaseAgent):
    name = "architect"
    skill_tasks = ["planning", "orchestration"]
    swarm = "sw_eng"
    default_tier = ModelTier.PLANNING

    @property
    def system_prompt(self) -> str:
        return (
            "You are the Solution Architect Agent. You design system architectures: "
            "microservices vs monolith, database choices, API design, scalability patterns, "
            "security boundaries, and infrastructure topology. "
            "Return JSON: architecture (style, components, data_flows, tech_stack, "
            "scalability_plan, security_boundaries, tradeoffs, adr_summary)."
        )

    def run(self, task: AgentTask) -> AgentResult:
        t0 = time.monotonic()
        requirements = task.parameters.get("requirements", {})
        constraints = task.parameters.get("constraints", {})
        result = self._llm_json(
            f"Design architecture.\nRequirements: {requirements}\nConstraints: {constraints}"
        )
        return self._make_result(task, result, confidence=0.82,
                                 duration_ms=(time.monotonic() - t0) * 1000)
