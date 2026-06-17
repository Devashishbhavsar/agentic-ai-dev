"""Semantic cache — avoids re-calling LLMs for semantically identical queries."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path


class SemanticCache:
    """Simple file-backed cache. Replace with Redis for production."""

    def __init__(self, cache_dir: str = "./data/cache", ttl: int = 86400) -> None:
        self._dir = Path(cache_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self.ttl = ttl
        self.hits = 0
        self.misses = 0

    def _key(self, prompt: str, model: str) -> str:
        return hashlib.sha256(f"{model}::{prompt}".encode()).hexdigest()

    def get(self, prompt: str, model: str = "") -> str | None:
        path = self._dir / self._key(prompt, model)
        if not path.exists():
            self.misses += 1
            return None
        data = json.loads(path.read_text())
        if time.time() - data["ts"] > self.ttl:
            path.unlink()
            self.misses += 1
            return None
        self.hits += 1
        return data["response"]

    def set(self, prompt: str, response: str, model: str = "") -> None:
        path = self._dir / self._key(prompt, model)
        path.write_text(json.dumps({"response": response, "ts": time.time()}))

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0
