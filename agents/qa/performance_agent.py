"""F3 · Performance Agent — generates load tests and performance benchmarks."""
from __future__ import annotations
import time
from agents.base import BaseAgent, AgentTask, AgentResult
from core.model_router import ModelTier


class PerformanceAgent(BaseAgent):
    name = "performance"
    swarm = "qa"
    default_tier = ModelTier.BALANCED

    @property
    def system_prompt(self) -> str:
        return (
            "You are the Performance Agent. You write Locust or k6 load test scripts, "
            "define performance budgets, and analyze results for bottlenecks. "
            "Return JSON: load_test_script (string), tool (locust/k6), "
            "performance_budget (p50_ms, p95_ms, p99_ms, rps_target, error_rate_max), "
            "bottleneck_candidates."
        )

    def run(self, task: AgentTask) -> AgentResult:
        t0 = time.monotonic()
        endpoints = task.parameters.get("endpoints", [])
        slo = task.parameters.get("slo", {})
        result = self._llm_json(
            f"Write performance tests.\nEndpoints: {endpoints}\nSLO: {slo}"
        )
        return self._make_result(task, result, confidence=0.8,
                                 duration_ms=(time.monotonic() - t0) * 1000)
