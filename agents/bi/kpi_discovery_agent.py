"""A3 · KPI Discovery Agent — identifies relevant KPIs and their calculation formulas."""
from __future__ import annotations
import time
from agents.base import BaseAgent, AgentTask, AgentResult
from core.model_router import ModelTier


class KPIDiscoveryAgent(BaseAgent):
    name = "kpi_discovery"
    swarm = "bi"
    default_tier = ModelTier.BALANCED

    @property
    def system_prompt(self) -> str:
        return (
            "You are the KPI Discovery Agent. Given a business domain and analysis plan, "
            "you identify all relevant KPIs, their definitions, formulas, dimensions, "
            "benchmarks, and the data columns needed to compute them. "
            "Return JSON: kpis (list of {name, definition, formula, dimensions, "
            "required_columns, benchmark, visualization_type})."
        )

    def run(self, task: AgentTask) -> AgentResult:
        t0 = time.monotonic()
        domain = task.parameters.get("domain", "")
        analysis_plan = task.parameters.get("analysis_plan", {})
        result = self._llm_json(
            f"Discover KPIs for domain '{domain}' with this analysis plan:\n\n{analysis_plan}"
        )
        return self._make_result(task, result, confidence=0.88,
                                 duration_ms=(time.monotonic() - t0) * 1000)
