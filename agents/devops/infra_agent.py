"""E1 · Infrastructure Agent — provisions cloud infrastructure as code."""
from __future__ import annotations
import time
from agents.base import BaseAgent, AgentTask, AgentResult
from core.model_router import ModelTier


class InfraAgent(BaseAgent):
    name = "infra"
    swarm = "devops"
    default_tier = ModelTier.CODE

    @property
    def system_prompt(self) -> str:
        return (
            "You are the Infrastructure Agent. You generate Terraform, Pulumi, or CloudFormation "
            "code to provision cloud infrastructure: VPCs, subnets, security groups, "
            "IAM roles, databases, and compute resources. "
            "Return JSON: iac_code (string), provider, resources_created (list), "
            "estimated_monthly_cost_usd, apply_command."
        )

    def run(self, task: AgentTask) -> AgentResult:
        t0 = time.monotonic()
        spec = task.parameters.get("spec", {})
        provider = task.parameters.get("provider", "aws")
        result = self._llm_json(
            f"Generate IaC for provider '{provider}'.\nSpec: {spec}"
        )
        return self._make_result(task, result, confidence=0.8,
                                 duration_ms=(time.monotonic() - t0) * 1000)
