"""E5 · Observability Agent — sets up metrics, tracing, and alerting."""
from __future__ import annotations
import time
from agents.base import BaseAgent, AgentTask, AgentResult
from core.model_router import ModelTier


class ObservabilityAgent(BaseAgent):
    name = "observability"
    swarm = "devops"
    default_tier = ModelTier.BALANCED

    @property
    def system_prompt(self) -> str:
        return (
            "You are the Observability Agent. You configure Prometheus scrape configs, "
            "Grafana dashboards (JSON), OpenTelemetry instrumentation, and alert rules. "
            "Return JSON: prometheus_config (string), grafana_dashboard (dict), "
            "alert_rules (list of {name, expr, severity}), "
            "otel_instrumentation_guide (string)."
        )

    def run(self, task: AgentTask) -> AgentResult:
        t0 = time.monotonic()
        service = task.parameters.get("service", "")
        slo = task.parameters.get("slo", {"availability": 0.999, "latency_p99_ms": 500})
        result = self._llm_json(
            f"Set up observability for service '{service}'.\nSLO: {slo}"
        )
        return self._make_result(task, result, confidence=0.85,
                                 duration_ms=(time.monotonic() - t0) * 1000)
