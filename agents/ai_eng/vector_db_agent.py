"""C3 · Vector DB Agent — manages embeddings, index tuning, and similarity search."""
from __future__ import annotations
import time
from agents.base import BaseAgent, AgentTask, AgentResult
from core.model_router import ModelTier
from core.memory.vector_store import VectorStore


class VectorDBAgent(BaseAgent):
    name = "vector_db"
    swarm = "ai_eng"
    default_tier = ModelTier.FAST

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._store = VectorStore()

    @property
    def system_prompt(self) -> str:
        return (
            "You are the Vector DB Agent. You manage document ingestion into vector stores, "
            "tune index parameters (HNSW ef, M), monitor index health, and execute semantic searches. "
            "Return JSON: operation_result (inserted_count, search_results, index_stats)."
        )

    def run(self, task: AgentTask) -> AgentResult:
        t0 = time.monotonic()
        operation = task.operation
        if operation == "ingest":
            texts = task.parameters.get("texts", [])
            source = task.parameters.get("source", "")
            self._store.add(texts, source=source, agent=self.name)
            result = {"inserted_count": len(texts), "source": source}
        elif operation == "search":
            query = task.parameters.get("query", "")
            limit = task.parameters.get("limit", 5)
            hits = self._store.search(query, limit=limit)
            result = {"search_results": hits, "query": query}
        else:
            result = {"error": f"Unknown operation: {operation}"}
        return self._make_result(task, result, confidence=1.0,
                                 duration_ms=(time.monotonic() - t0) * 1000)
