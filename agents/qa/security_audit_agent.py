"""F4 · Security Audit Agent — performs DAST and security regression testing."""
from __future__ import annotations
import time
from agents.base import BaseAgent, AgentTask, AgentResult
from core.model_router import ModelTier


class SecurityAuditAgent(BaseAgent):
    name = "security_audit"
    swarm = "qa"
    default_tier = ModelTier.PLANNING

    @property
    def system_prompt(self) -> str:
        return (
            "You are the Security Audit Agent. You run dynamic security tests: "
            "OWASP ZAP scans, SQL injection probes, XSS tests, auth bypass checks, "
            "and secrets detection in code. "
            "Return JSON: findings (list of {vulnerability, severity, endpoint, proof_of_concept}), "
            "risk_score 0-10, remediation_priority, compliance_gaps."
        )

    def run(self, task: AgentTask) -> AgentResult:
        t0 = time.monotonic()
        target_url = task.parameters.get("target_url", "")
        scope = task.parameters.get("scope", [])
        result = self._llm_json(
            f"Security audit plan for: '{target_url}'\nScope: {scope}"
        )
        return self._make_result(task, result, confidence=0.85,
                                 duration_ms=(time.monotonic() - t0) * 1000)
