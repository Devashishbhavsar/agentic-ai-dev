from __future__ import annotations

from core.retrieval import RetrievalService


def test_retrieval_service_formats_compact_context(tmp_path, monkeypatch):
    monkeypatch.setenv("RAG_STORE_PATH", str(tmp_path / "rag.sqlite"))
    service = RetrievalService()
    service.store.add([
        "Retrieval should combine vector search with structured filters and citations.",
        "GraphQL is not the primary RAG engine; use it only for API transport.",
    ], source="design-doc", agent="planner", metadata={"topic": "rag"})

    bundle = service.build_context("How should we do production RAG and GraphQL?", limit=2)

    assert bundle.retrieved_count == 2
    assert "GraphQL is not the primary RAG engine" in bundle.prompt
    assert "Source: design-doc" in bundle.prompt
    assert bundle.citations[0]["source"] == "design-doc"
