from __future__ import annotations

import json

from core.memory.vector_store import VectorStore


def test_vector_store_search_ranks_best_match_first(tmp_path, monkeypatch):
    monkeypatch.setenv("RAG_STORE_PATH", str(tmp_path / "rag.sqlite"))
    store = VectorStore(table_name="kb")
    store.add([
        "GraphQL is useful for API composition and typed client contracts.",
        "Live dashboards need websocket push and compact refresh intervals.",
    ], source="docs", agent="ingest", metadata={"topic": "dashboards"})

    hits = store.search("websocket dashboard push", limit=2)

    assert hits[0]["text"].startswith("Live dashboards")
    assert hits[0]["source"] == "docs"
    assert hits[0]["agent"] == "ingest"
    assert hits[0]["score"] >= hits[1]["score"]


def test_vector_store_search_can_run_from_worker_thread(tmp_path, monkeypatch):
    monkeypatch.setenv("RAG_STORE_PATH", str(tmp_path / "rag.sqlite"))
    store = VectorStore(table_name="kb")
    store.add(["Parallel agents need thread-safe retrieval context."], source="docs", agent="ingest")

    result: dict[str, object] = {}

    def worker() -> None:
        result["hits"] = store.search("thread-safe retrieval", limit=1)

    import threading

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()

    assert result["hits"][0]["text"].startswith("Parallel agents")
