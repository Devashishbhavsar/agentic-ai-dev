"""F5 · Compliance Agent — validates against GDPR, SOX, HIPAA, and enterprise policies."""
from __future__ import annotations
import time
from agents.base import BaseAgent, AgentTask, AgentResult
from core.model_router import ModelTier


class ComplianceAgent(BaseAgent):
    name = "compliance"
    swarm = "qa"
    default_tier = ModelTier.PLANNING

    @property
    def system_prompt(self) -> str:
        return (
            "You are the Compliance Agent. You check systems against regulatory frameworks: "
            "GDPR (data residency, consent, right-to-forget), SOX (audit trails, access controls), "
            "HIPAA (PHI handling), and internal enterprise policies. "
            "Return JSON: framework, controls_checked, passed, failed, "
            "critical_gaps (list), remediation_plan, compliance_score 0-100."
        )

    def run(self, task: AgentTask) -> AgentResult:
        t0 = time.monotonic()
        system_description = task.parameters.get("system_description", "")
        frameworks = task.parameters.get("frameworks", ["GDPR"])
        result = self._llm_json(
            f"Compliance check for: {system_description}\nFrameworks: {frameworks}"
        )
        return self._make_result(task, result, confidence=0.88,
                                 duration_ms=(time.monotonic() - t0) * 1000)
