"""B5 · Metadata Agent — manages data lineage and catalog metadata."""
from __future__ import annotations
import time
from agents.base import BaseAgent, AgentTask, AgentResult
from core.model_router import ModelTier


class MetadataAgent(BaseAgent):
    name = "metadata"
    swarm = "data_eng"
    default_tier = ModelTier.FAST

    @property
    def system_prompt(self) -> str:
        return (
            "You are the Metadata Agent. You maintain a data catalog with lineage tracking. "
            "For each dataset you track: owner, classification (public/internal/confidential), "
            "upstream sources, downstream consumers, SLA, and business glossary terms. "
            "Return JSON: catalog_entry (dataset, owner, classification, lineage, "
            "sla_hours, glossary_terms, tags)."
        )

    def run(self, task: AgentTask) -> AgentResult:
        t0 = time.monotonic()
        dataset_info = task.parameters.get("dataset_info", {})
        result = self._llm_json(f"Create catalog entry for: {dataset_info}")
        return self._make_result(task, result, confidence=0.9,
                                 duration_ms=(time.monotonic() - t0) * 1000)
