"""B4 · Schema Agent — introspects and documents database schemas."""
from __future__ import annotations
import time
from agents.base import BaseAgent, AgentTask, AgentResult
from core.model_router import ModelTier


class SchemaAgent(BaseAgent):
    name = "schema"
    swarm = "data_eng"
    default_tier = ModelTier.FAST

    @property
    def system_prompt(self) -> str:
        return (
            "You are the Schema Agent. You analyze database DDL and produce human-readable schema "
            "documentation including: table descriptions, column types/constraints, "
            "primary/foreign keys, indexes, and join relationships. "
            "Return JSON: tables (list of {name, description, columns, primary_key, "
            "foreign_keys, indexes, row_estimate})."
        )

    def run(self, task: AgentTask) -> AgentResult:
        t0 = time.monotonic()
        ddl = task.parameters.get("ddl", "")
        result = self._llm_json(f"Document this schema:\n\n{ddl}")
        return self._make_result(task, result, confidence=0.95,
                                 duration_ms=(time.monotonic() - t0) * 1000)
