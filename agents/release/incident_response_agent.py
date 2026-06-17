"""G5 · Incident Response Agent — coordinates incident triage and postmortems."""
from __future__ import annotations
import time
from agents.base import BaseAgent, AgentTask, AgentResult
from core.model_router import ModelTier


class IncidentResponseAgent(BaseAgent):
    name = "incident_response"
    swarm = "release"
    default_tier = ModelTier.PLANNING

    @property
    def system_prompt(self) -> str:
        return (
            "You are the Incident Response Agent. You triage production incidents: "
            "classify severity (P0-P3), identify blast radius, coordinate runbooks, "
            "draft communication (status page, Slack), and write postmortems (5-whys). "
            "Return JSON: severity, blast_radius, immediate_actions (list), "
            "runbook_steps (list), comms_draft (string), postmortem (root_cause, timeline, "
            "action_items)."
        )

    def run(self, task: AgentTask) -> AgentResult:
        t0 = time.monotonic()
        alert = task.parameters.get("alert", {})
        logs = task.parameters.get("logs", "")
        result = self._llm_json(
            f"Triage incident.\nAlert: {alert}\nLogs (last 50 lines): {logs[-2000:]}"
        )
        return self._make_result(task, result, confidence=0.82,
                                 duration_ms=(time.monotonic() - t0) * 1000)
