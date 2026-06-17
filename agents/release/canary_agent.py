"""G3 · Canary Agent — manages progressive traffic shifting and canary analysis."""
from __future__ import annotations
import time
from agents.base import BaseAgent, AgentTask, AgentResult
from core.model_router import ModelTier


class CanaryAgent(BaseAgent):
    name = "canary"
    swarm = "release"
    default_tier = ModelTier.BALANCED

    @property
    def system_prompt(self) -> str:
        return (
            "You are the Canary Agent. You design and monitor canary deployments: "
            "define traffic split percentages, success metrics, promotion criteria, "
            "and automated rollback triggers. "
            "Return JSON: canary_config (initial_traffic_pct, promotion_steps, "
            "analysis_interval_minutes, success_criteria, rollback_criteria), "
            "analysis_result (promote/rollback/hold), reason."
        )

    def run(self, task: AgentTask) -> AgentResult:
        t0 = time.monotonic()
        metrics = task.parameters.get("metrics", {})
        baseline = task.parameters.get("baseline_metrics", {})
        result = self._llm_json(
            f"Canary analysis.\nCurrent metrics: {metrics}\nBaseline: {baseline}"
        )
        return self._make_result(task, result, confidence=0.88,
                                 duration_ms=(time.monotonic() - t0) * 1000)
