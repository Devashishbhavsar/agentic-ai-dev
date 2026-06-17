"""E3 · Kubernetes Agent — generates K8s manifests and Helm charts."""
from __future__ import annotations
import time
from agents.base import BaseAgent, AgentTask, AgentResult
from core.model_router import ModelTier


class KubernetesAgent(BaseAgent):
    name = "kubernetes"
    swarm = "devops"
    default_tier = ModelTier.CODE

    @property
    def system_prompt(self) -> str:
        return (
            "You are the Kubernetes Agent. You generate K8s manifests: Deployments, Services, "
            "Ingress, ConfigMaps, Secrets, HPA, PodDisruptionBudgets, and Helm chart values. "
            "Apply security best practices: resource limits, network policies, RBAC. "
            "Return JSON: manifests (list of {filename, yaml_content}), "
            "helm_values (dict), resource_requirements, rollout_strategy."
        )

    def run(self, task: AgentTask) -> AgentResult:
        t0 = time.monotonic()
        service_spec = task.parameters.get("service_spec", {})
        namespace = task.parameters.get("namespace", "default")
        result = self._llm_json(
            f"Generate K8s manifests for namespace '{namespace}'.\nSpec: {service_spec}"
        )
        return self._make_result(task, result, confidence=0.85,
                                 duration_ms=(time.monotonic() - t0) * 1000)
