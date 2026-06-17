"""Hybrid retrieval service used by agents for production-grade RAG."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.memory.vector_store import VectorStore


@dataclass(frozen=True)
class RetrievalContext:
    query: str
    prompt: str
    citations: list[dict[str, Any]] = field(default_factory=list)
    retrieved_count: int = 0


class RetrievalService:
    """Compact hybrid retrieval over the shared vector store."""

    def __init__(self, store: VectorStore | None = None, max_snippet_chars: int = 220) -> None:
        self.store = store or VectorStore()
        self.max_snippet_chars = max_snippet_chars

    def retrieve(
        self,
        query: str,
        *,
        limit: int = 4,
        source: str | None = None,
        agent: str | None = None,
    ) -> list[dict[str, Any]]:
        return self.store.search(query, limit=limit, source=source, agent=agent)

    def build_context(
        self,
        query: str,
        *,
        limit: int = 4,
        source: str | None = None,
        agent: str | None = None,
    ) -> RetrievalContext:
        hits = self.retrieve(query, limit=limit, source=source, agent=agent)
        if not hits:
            return RetrievalContext(
                query=query,
                prompt="Retrieved context: none",
                citations=[],
                retrieved_count=0,
            )

        citations: list[dict[str, Any]] = []
        lines = ["Retrieved context:"]
        for index, hit in enumerate(hits, start=1):
            snippet = self._truncate(hit.get("text", ""))
            score = float(hit.get("score") or 0.0)
            source_name = hit.get("source") or "unknown"
            agent_name = hit.get("agent") or "unknown"
            citation = {
                "index": index,
                "text": snippet,
                "source": source_name,
                "agent": agent_name,
                "score": round(score, 4),
                "metadata": hit.get("metadata") or {},
            }
            citations.append(citation)
            lines.append(
                f"{index}. {snippet}\n   Source: {source_name} | Agent: {agent_name} | Score: {score:.4f}"
            )

        return RetrievalContext(
            query=query,
            prompt="\n".join(lines),
            citations=citations,
            retrieved_count=len(citations),
        )

    def ingest_document(
        self,
        text: str,
        *,
        source: str = "",
        agent: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.store.add([text], source=source, agent=agent, metadata=metadata)

    def ingest_workflow_summary(
        self,
        *,
        workflow_id: str,
        request: str,
        summary: str,
        pipeline: str = "",
        intent: str = "",
        stage: str = "",
        risk_level: str = "",
    ) -> None:
        text = (
            f"Workflow {workflow_id}: {request}\n"
            f"Pipeline: {pipeline} | Intent: {intent} | Stage: {stage} | Risk: {risk_level}\n"
            f"Summary: {summary}"
        )
        self.ingest_document(
            text,
            source=workflow_id,
            agent="workflow",
            metadata={
                "workflow_id": workflow_id,
                "pipeline": pipeline,
                "intent": intent,
                "stage": stage,
                "risk_level": risk_level,
            },
        )

    def _truncate(self, text: str) -> str:
        clean = " ".join(str(text).split())
        if len(clean) <= self.max_snippet_chars:
            return clean
        return clean[: self.max_snippet_chars - 1] + "…"


_SERVICE: RetrievalService | None = None


def get_retrieval_service() -> RetrievalService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = RetrievalService()
    return _SERVICE
