"""A1 · Requirements Agent — parses natural language BI requests into structured specs."""
from __future__ import annotations
import time
from agents.base import BaseAgent, AgentTask, AgentResult
from core.model_router import ModelTier


class RequirementsAgent(BaseAgent):
    name = "requirements"
    swarm = "bi"
    default_tier = ModelTier.BALANCED

    @property
    def system_prompt(self) -> str:
        return (
            "You are the Requirements Agent in a BI platform. "
            "Your job is to parse natural language business requests and extract: "
            "desired metrics, data sources needed, target audience, time range, filters, "
            "output format (dashboard/report/alert), and acceptance criteria. "
            "Ask clarifying questions when the request is ambiguous. "
            "Return structured JSON with keys: metrics, data_sources, audience, time_range, "
            "filters, output_format, acceptance_criteria, clarifying_questions."
        )

    def run(self, task: AgentTask) -> AgentResult:
        t0 = time.monotonic()
        request_text = task.parameters.get("request", "")
        result = self._llm_json(
            f"Parse this BI request into a structured specification:\n\n{request_text}"
        )
        return self._make_result(task, result, confidence=0.9,
                                 duration_ms=(time.monotonic() - t0) * 1000)
