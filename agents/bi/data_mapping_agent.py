"""A4 · Data Mapping Agent — maps KPI columns to actual table/schema locations."""
from __future__ import annotations
import time
from agents.base import BaseAgent, AgentTask, AgentResult
from core.model_router import ModelTier


class DataMappingAgent(BaseAgent):
    name = "data_mapping"
    swarm = "bi"
    default_tier = ModelTier.BALANCED

    @property
    def system_prompt(self) -> str:
        return (
            "You are the Data Mapping Agent. Given a list of required KPI columns and "
            "a schema catalog, you map each column to its source table, schema, and database. "
            "Identify joins needed, transformations required, and flag missing columns. "
            "Return JSON: mappings (list of {column, source_db, source_schema, source_table, "
            "source_column, join_keys, transformation}), missing_columns."
        )

    def run(self, task: AgentTask) -> AgentResult:
        t0 = time.monotonic()
        kpis = task.parameters.get("kpis", [])
        schema_catalog = task.parameters.get("schema_catalog", {})
        result = self._llm_json(
            f"Map these KPI columns to schema:\nKPIs: {kpis}\nSchema: {schema_catalog}"
        )
        return self._make_result(task, result, confidence=0.82,
                                 duration_ms=(time.monotonic() - t0) * 1000)
