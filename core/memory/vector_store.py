"""L6 · Vector store — local hybrid retrieval store for all agents."""
from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

def _tokenize(text: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9]+", text.lower()) if len(token) > 1]


def _json(value: Any) -> str:
    return json.dumps(value or {}, ensure_ascii=False, sort_keys=True)


def _score_text(query: str, text: str) -> float:
    query_tokens = _tokenize(query)
    if not query_tokens:
        return 0.0
    text_lower = text.lower()
    text_tokens = set(_tokenize(text_lower))
    overlap = len(set(query_tokens) & text_tokens)
    if overlap == 0:
        return 0.0
    coverage = overlap / len(set(query_tokens))
    phrase_bonus = 0.0
    if query.lower() in text_lower:
        phrase_bonus = 0.2
    return round(coverage + phrase_bonus, 6)


class VectorStore:
    """Shared local retrieval store — all agents read/write here."""

    def __init__(self, table_name: str = "enterprise_kb") -> None:
        self._path = Path(os.environ.get("RAG_STORE_PATH", "./data/rag/retrieval.sqlite"))
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._table_name = table_name
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._has_fts = False
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    table_name TEXT NOT NULL,
                    text TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT '',
                    agent TEXT NOT NULL DEFAULT '',
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at REAL NOT NULL DEFAULT (strftime('%s','now'))
                )
                """
            )
            try:
                self._conn.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts
                    USING fts5(text, source, agent, metadata, content='', tokenize='porter')
                    """
                )
                self._has_fts = True
            except sqlite3.OperationalError:
                self._has_fts = False
            self._conn.commit()

    def add(self, texts: list[str], source: str = "", agent: str = "", metadata: dict | None = None) -> None:
        metadata_json = _json(metadata)
        with self._lock:
            for text in texts:
                cursor = self._conn.execute(
                    "INSERT INTO documents(table_name, text, source, agent, metadata) VALUES (?, ?, ?, ?, ?)",
                    (self._table_name, text, source, agent, metadata_json),
                )
                row_id = cursor.lastrowid
                if self._has_fts:
                    self._conn.execute(
                        "INSERT INTO documents_fts(rowid, text, source, agent, metadata) VALUES (?, ?, ?, ?, ?)",
                        (row_id, text, source, agent, metadata_json),
                    )
            self._conn.commit()

    def search(self, query: str, limit: int = 5, source: str | None = None, agent: str | None = None) -> list[dict]:
        query = query.strip()
        if not query:
            return []

        with self._lock:
            candidates: list[dict[str, Any]] = []
            if self._has_fts:
                tokens = _tokenize(query)
                match_query = " OR ".join(tokens) if tokens else query.replace('"', ' ')
                clauses = ["documents.rowid = documents_fts.rowid"]
                params: list[Any] = []
                if source:
                    clauses.append("documents.source = ?")
                    params.append(source)
                if agent:
                    clauses.append("documents.agent = ?")
                    params.append(agent)
                params.extend([match_query, limit])
                sql = f"""
                    SELECT
                        documents.text,
                        documents.source,
                        documents.agent,
                        documents.metadata,
                        documents.created_at
                    FROM documents
                    JOIN documents_fts ON {' AND '.join(clauses)}
                    WHERE documents_fts MATCH ?
                    LIMIT ?
                """
                rows = self._conn.execute(sql, params).fetchall()
                candidates = [self._row_to_dict(row) for row in rows]
                for item in candidates:
                    item["score"] = _score_text(query, item["text"])
                candidates.sort(key=lambda item: item.get("score", 0), reverse=True)
                if candidates and candidates[0].get("score", 0) > 0:
                    return candidates[:limit]

            return self._fallback_search(query, limit=limit, source=source, agent=agent)

    def _fallback_search(self, query: str, limit: int, source: str | None, agent: str | None) -> list[dict]:
        rows = self._conn.execute(
            "SELECT text, source, agent, metadata, created_at FROM documents WHERE table_name = ?",
            (self._table_name,),
        ).fetchall()
        scored: list[dict[str, Any]] = []
        for row in rows:
            if source and row["source"] != source:
                continue
            if agent and row["agent"] != agent:
                continue
            item = self._row_to_dict(row)
            item["score"] = _score_text(query, item["text"])
            if item["score"] <= 0:
                continue
            scored.append(item)
        scored.sort(key=lambda item: item.get("score", 0), reverse=True)
        return scored[:limit]

    def _row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        metadata = row["metadata"]
        try:
            parsed_metadata = json.loads(metadata) if metadata else {}
        except Exception:
            parsed_metadata = {"raw": metadata}
        return {
            "text": row["text"],
            "source": row["source"],
            "agent": row["agent"],
            "metadata": parsed_metadata,
            "created_at": row["created_at"],
            "score": 0.0,
        }

    def delete_by_source(self, source: str) -> None:
        with self._lock:
            ids = self._conn.execute(
                "SELECT rowid FROM documents WHERE source = ? AND table_name = ?",
                (source, self._table_name),
            ).fetchall()
            for row in ids:
                self._conn.execute("DELETE FROM documents WHERE rowid = ?", (row[0],))
                if self._has_fts:
                    self._conn.execute("DELETE FROM documents_fts WHERE rowid = ?", (row[0],))
            self._conn.commit()
