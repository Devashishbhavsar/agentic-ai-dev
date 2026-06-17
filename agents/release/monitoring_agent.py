"""G4 · Monitoring Agent — post-deploy health checks and alerting."""
from __future__ import annotations
import time
from agents.base import BaseAgent, AgentTask, AgentResult
from core.model_router import ModelTier


class MonitoringAgent(BaseAgent):
    name = "monitoring"
    swarm = "release"
    default_tier = ModelTier.FAST

    @property
    def system_prompt(self) -> str:
        return (
            "You are the Monitoring Agent. You define post-deployment health checks: "
            "synthetic probes, latency baselines, error rate thresholds, "
            "and PagerDuty/Slack alert routing. "
            "Return JSON: health_checks (list of {url, method, expected_status, timeout_ms}), "
            "alert_routes (list of {condition, severity, channel}), "
            "burn_rate_alerts, status (healthy/degraded/down)."
        )

    def run(self, task: AgentTask) -> AgentResult:
        t0 = time.monotonic()
        service = task.parameters.get("service", "")
        metrics_snapshot = task.parameters.get("metrics_snapshot", {})
        result = self._llm_json(
            f"Post-deploy monitoring for '{service}'.\nMetrics: {metrics_snapshot}"
        )
        return self._make_result(task, result, confidence=0.9,
                                 duration_ms=(time.monotonic() - t0) * 1000)
