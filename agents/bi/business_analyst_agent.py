"""A2 · Business Analyst Agent — translates requirements into data questions and KPI hypotheses."""
from __future__ import annotations
import time
from agents.base import BaseAgent, AgentTask, AgentResult
from core.model_router import ModelTier


class BusinessAnalystAgent(BaseAgent):
    name = "business_analyst"
    skill_tasks = ["bi_pipeline", "analytics"]
    swarm = "bi"
    default_tier = ModelTier.PLANNING

    @property
    def system_prompt(self) -> str:
        return (
            "You are a senior Business Analyst in a multi-agent BI platform. "
            "Given structured requirements, you: identify the business questions being asked, "
            "propose KPI hypotheses, identify potential data gaps, define success metrics, "
            "and write an analysis plan. "
            "Return JSON with: business_questions, kpi_hypotheses, data_gaps, "
            "success_metrics, analysis_plan."
        )

    def run(self, task: AgentTask) -> AgentResult:
        t0 = time.monotonic()
        requirements = task.parameters.get("requirements", {})
        result = self._llm_json(
            f"Analyze these BI requirements and produce an analysis plan:\n\n{requirements}"
        )
        return self._make_result(task, result, confidence=0.85,
                                 duration_ms=(time.monotonic() - t0) * 1000)
