"""E4 · Terraform Agent — writes and validates Terraform modules."""
from __future__ import annotations
import time
from agents.base import BaseAgent, AgentTask, AgentResult
from core.model_router import ModelTier


class TerraformAgent(BaseAgent):
    name = "terraform"
    swarm = "devops"
    default_tier = ModelTier.CODE

    @property
    def system_prompt(self) -> str:
        return (
            "You are the Terraform Agent. You write modular Terraform: "
            "main.tf, variables.tf, outputs.tf, and backend.tf. "
            "Follow naming conventions, use data sources, and avoid hardcoded values. "
            "Return JSON: tf_files (list of {filename, content}), "
            "variable_defaults, outputs, backend_config, plan_preview."
        )

    def run(self, task: AgentTask) -> AgentResult:
        t0 = time.monotonic()
        infra_spec = task.parameters.get("infra_spec", {})
        provider = task.parameters.get("provider", "aws")
        result = self._llm_json(
            f"Write Terraform for '{provider}' provider.\nSpec: {infra_spec}"
        )
        return self._make_result(task, result, confidence=0.82,
                                 duration_ms=(time.monotonic() - t0) * 1000)
