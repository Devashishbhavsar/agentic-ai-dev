"""A5 · Stakeholder Agent — aligns output format with audience needs."""
from __future__ import annotations
import time
from agents.base import BaseAgent, AgentTask, AgentResult
from core.model_router import ModelTier


class StakeholderAgent(BaseAgent):
    name = "stakeholder"
    swarm = "bi"
    default_tier = ModelTier.FAST

    @property
    def system_prompt(self) -> str:
        return (
            "You are the Stakeholder Alignment Agent. You tailor BI outputs for specific audiences: "
            "executives (summary, high-level KPIs), analysts (detailed breakdowns), "
            "developers (raw data access), product managers (trend/funnel views). "
            "Return JSON: audience_profiles (list of {role, preferred_format, key_metrics, "
            "detail_level, delivery_channel})."
        )

    def run(self, task: AgentTask) -> AgentResult:
        t0 = time.monotonic()
        audience = task.parameters.get("audience", "executives")
        kpis = task.parameters.get("kpis", [])
        result = self._llm_json(
            f"Define output format for audience '{audience}' with KPIs:\n{kpis}"
        )
        return self._make_result(task, result, confidence=0.9,
                                 duration_ms=(time.monotonic() - t0) * 1000)
