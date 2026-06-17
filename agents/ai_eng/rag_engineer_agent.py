"""C2 · RAG Engineer Agent — builds and tunes retrieval-augmented generation pipelines."""
from __future__ import annotations
import time
from agents.base import BaseAgent, AgentTask, AgentResult
from core.model_router import ModelTier


class RAGEngineerAgent(BaseAgent):
    name = "rag_engineer"
    swarm = "ai_eng"
    default_tier = ModelTier.BALANCED

    @property
    def system_prompt(self) -> str:
        return (
            "You are the RAG Engineer Agent. You design retrieval-augmented generation pipelines: "
            "chunking strategy, embedding model selection, retrieval method (semantic/hybrid/BM25), "
            "re-ranking, and context window packing. "
            "Return JSON: pipeline_config (chunking, embedding_model, retrieval_method, "
            "top_k, reranker, context_budget_tokens), evaluation_metrics."
        )

    def run(self, task: AgentTask) -> AgentResult:
        t0 = time.monotonic()
        domain = task.parameters.get("domain", "")
        doc_types = task.parameters.get("doc_types", [])
        result = self._llm_json(
            f"Design RAG pipeline for domain '{domain}' with doc types: {doc_types}"
        )
        return self._make_result(task, result, confidence=0.83,
                                 duration_ms=(time.monotonic() - t0) * 1000)
