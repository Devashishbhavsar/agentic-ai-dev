"""D5 · Security Agent — performs SAST, threat modeling, and security hardening."""
from __future__ import annotations
import time
from agents.base import BaseAgent, AgentTask, AgentResult
from core.model_router import ModelTier


class SecurityAgent(BaseAgent):
    name = "security"
    swarm = "sw_eng"
    default_tier = ModelTier.PLANNING

    @property
    def system_prompt(self) -> str:
        return (
            "You are the Security Agent. You perform threat modeling (STRIDE), static analysis "
            "of code for OWASP Top 10 vulnerabilities, dependency CVE scanning, "
            "and produce hardening recommendations. "
            "Return JSON: threat_model (threats, mitigations), vulnerabilities "
            "(list of {cve, severity, location, fix}), hardening_checklist, risk_score 0-10."
        )

    def run(self, task: AgentTask) -> AgentResult:
        t0 = time.monotonic()
        code = task.parameters.get("code", "")
        architecture = task.parameters.get("architecture", {})
        result = self._llm_json(
            f"Security review.\nArchitecture: {architecture}\nCode snippet: {code[:2000]}"
        )
        return self._make_result(task, result, confidence=0.8,
                                 duration_ms=(time.monotonic() - t0) * 1000)
