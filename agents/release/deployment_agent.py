"""G2 · Deployment Agent — executes deployments to target environments."""
from __future__ import annotations
import time
from agents.base import BaseAgent, AgentTask, AgentResult
from core.model_router import ModelTier


class DeploymentAgent(BaseAgent):
    name = "deployment"
    swarm = "release"
    default_tier = ModelTier.BALANCED

    @property
    def system_prompt(self) -> str:
        return (
            "You are the Deployment Agent. You plan and execute deployments: "
            "generate deployment manifests, kubectl apply commands, Helm upgrade commands, "
            "ArgoCD sync, and rollback procedures. "
            "Return JSON: deployment_plan (steps list), rollback_plan, "
            "estimated_downtime_seconds, health_check_endpoints, success_criteria."
        )

    def run(self, task: AgentTask) -> AgentResult:
        t0 = time.monotonic()
        service = task.parameters.get("service", "")
        environment = task.parameters.get("environment", "staging")
        version = task.parameters.get("version", "latest")
        result = self._llm_json(
            f"Plan deployment of '{service}' v{version} to '{environment}'."
        )
        return self._make_result(task, result, confidence=0.87,
                                 duration_ms=(time.monotonic() - t0) * 1000)
