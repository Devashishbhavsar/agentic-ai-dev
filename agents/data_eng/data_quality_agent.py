"""B3 · Data Quality Agent — validates data against quality rules."""
from __future__ import annotations
import time
from agents.base import BaseAgent, AgentTask, AgentResult
from core.model_router import ModelTier


class DataQualityAgent(BaseAgent):
    name = "data_quality"
    skill_tasks = ["data_engineering", "quality_assurance"]
    swarm = "data_eng"
    default_tier = ModelTier.BALANCED

    @property
    def system_prompt(self) -> str:
        return (
            "You are the Data Quality Agent. You define and evaluate data quality rules: "
            "completeness (null %), uniqueness, referential integrity, range checks, "
            "format validation, and freshness. "
            "Return JSON: quality_report (overall_score 0-1, passed_rules, failed_rules, "
            "critical_issues, recommendations)."
        )

    def run(self, task: AgentTask) -> AgentResult:
        t0 = time.monotonic()
        data_profile = task.parameters.get("data_profile", {})
        rules = task.parameters.get("rules", [])
        result = self._llm_json(
            f"Evaluate data quality.\nProfile: {data_profile}\nRules: {rules}"
        )
        return self._make_result(task, result, confidence=0.92,
                                 duration_ms=(time.monotonic() - t0) * 1000)
