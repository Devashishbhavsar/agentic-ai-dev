"""B2 · ETL Agent — generates and executes ETL pipelines (extract, transform, load)."""
from __future__ import annotations
import time
from agents.base import BaseAgent, AgentTask, AgentResult
from core.model_router import ModelTier


class ETLAgent(BaseAgent):
    name = "etl"
    skill_tasks = ["data_engineering", "debugging"]
    swarm = "data_eng"
    default_tier = ModelTier.CODE

    @property
    def system_prompt(self) -> str:
        return (
            "You are the ETL Agent. You generate Python ETL code using pandas, SQLAlchemy, "
            "or dbt depending on the target. Given source schema, target schema, and transformation "
            "rules, produce executable ETL scripts. Include error handling, logging, and idempotency. "
            "Return JSON: etl_code (string), dependencies (list), estimated_duration_minutes, "
            "idempotent (bool), rollback_strategy."
        )

    def run(self, task: AgentTask) -> AgentResult:
        t0 = time.monotonic()
        source = task.parameters.get("source", {})
        target = task.parameters.get("target", {})
        transformations = task.parameters.get("transformations", [])
        result = self._llm_json(
            f"Generate ETL pipeline.\nSource: {source}\nTarget: {target}\n"
            f"Transformations: {transformations}"
        )
        return self._make_result(task, result, confidence=0.8,
                                 duration_ms=(time.monotonic() - t0) * 1000)
