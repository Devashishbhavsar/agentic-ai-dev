"""In-memory session store — per-session context window for all agents in a run."""
from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class Message:
    role: str        # "user" | "assistant" | "agent"
    content: str
    agent: str = ""
    timestamp: float = field(default_factory=time.time)


class SessionMemory:
    """Shared short-term memory for a single workflow run."""

    def __init__(self, session_id: str, ttl: int = 3600) -> None:
        self.session_id = session_id
        self.ttl = ttl
        self._messages: list[Message] = []
        self._agent_state: dict[str, dict] = defaultdict(dict)
        self._created_at = time.time()

    @property
    def expired(self) -> bool:
        return (time.time() - self._created_at) > self.ttl

    def add(self, role: str, content: str, agent: str = "") -> None:
        self._messages.append(Message(role=role, content=content, agent=agent))

    def get_messages(self, last_n: int | None = None) -> list[Message]:
        msgs = self._messages
        return msgs[-last_n:] if last_n else msgs

    def as_anthropic_messages(self, last_n: int = 20) -> list[dict]:
        """Format for Anthropic messages API."""
        result = []
        for m in self.get_messages(last_n):
            role = "user" if m.role in ("user", "agent") else "assistant"
            result.append({"role": role, "content": m.content})
        return result

    def set_agent_state(self, agent: str, key: str, value) -> None:
        self._agent_state[agent][key] = value

    def get_agent_state(self, agent: str) -> dict:
        return self._agent_state.get(agent, {})
