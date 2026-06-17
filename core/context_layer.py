"""Compact shared context packing for multi-agent runs."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.memory.short_term import SessionMemory


@dataclass(frozen=True)
class ContextLayerPack:
    workflow_id: str
    shared_summary: str
    agent_brief: str
    messages: list[dict[str, str]]
    compressed_turns: int


class ContextLayerBuilder:
    """Builds a compact, reusable prompt bundle for every agent call."""

    def __init__(self, max_messages: int = 4, max_bullets: int = 5, max_chars: int = 220) -> None:
        self.max_messages = max_messages
        self.max_bullets = max_bullets
        self.max_chars = max_chars

    def build(
        self,
        *,
        workflow_id: str,
        user_request: str,
        session: SessionMemory,
        agent_name: str,
        task_label: str = "",
    ) -> ContextLayerPack:
        shared_state = session.get_agent_state("shared")
        orchestrator_state = session.get_agent_state("orchestrator")
        agent_state = session.get_agent_state(agent_name)

        bullets = self._bullets(
            shared_state.get("shared_bullets")
            or orchestrator_state.get("shared_bullets")
            or agent_state.get("shared_bullets")
            or []
        )

        shared_summary_parts = [
            f"workflow={workflow_id}",
            f"request={self._truncate(user_request, 160)}",
            self._kv("intent", orchestrator_state.get("intent")),
            self._kv("pipeline", orchestrator_state.get("pipeline")),
            self._kv("stage", orchestrator_state.get("current_stage") or orchestrator_state.get("stage")),
            self._kv("risk", orchestrator_state.get("risk_level")),
            self._kv("approval", orchestrator_state.get("approval_required")),
            self._kv("agent", orchestrator_state.get("current_agent") or agent_state.get("current_agent")),
        ]
        if bullets:
            shared_summary_parts.append(f"shared={'; '.join(bullets)}")
        shared_summary = " | ".join(part for part in shared_summary_parts if part and not part.endswith("=None"))

        agent_notes = self._bullets(
            agent_state.get("notes")
            or orchestrator_state.get("agent_notes")
            or []
        )
        dependency_text = "; ".join(agent_notes[: self.max_bullets]) if agent_notes else "keep context compact"
        agent_brief = (
            f"Agent: {agent_name} | Task: {task_label or agent_state.get('task_label') or 'general'} | "
            f"Workflow: {workflow_id} | Dependencies: {dependency_text}"
        )

        messages = self._compact_messages(session.get_messages(self.max_messages))
        return ContextLayerPack(
            workflow_id=workflow_id,
            shared_summary=shared_summary,
            agent_brief=agent_brief,
            messages=messages,
            compressed_turns=len(messages),
        )

    def _compact_messages(self, messages: list[Any]) -> list[dict[str, str]]:
        compacted: list[dict[str, str]] = []
        for message in messages[-self.max_messages :]:
            role = getattr(message, "role", "user")
            content = self._truncate(getattr(message, "content", ""), self.max_chars)
            prefix = {
                "user": "user",
                "assistant": "assistant",
                "agent": "agent",
            }.get(role, "message")
            compacted.append({"role": self._role(role), "content": f"[{prefix}] {content}"})
        return compacted

    def _role(self, role: str) -> str:
        return "assistant" if role == "assistant" else "user"

    def _truncate(self, value: Any, limit: int) -> str:
        text = "" if value is None else str(value).strip()
        if len(text) <= limit:
            return text
        return text[: limit - 1] + "…"

    def _kv(self, key: str, value: Any) -> str:
        if value in (None, "", [], {}):
            return ""
        if isinstance(value, bool):
            value = "yes" if value else "no"
        return f"{key}={value}"

    def _bullets(self, value: Any) -> list[str]:
        if isinstance(value, list):
            return [self._truncate(item, 120) for item in value if str(item).strip()][: self.max_bullets]
        if isinstance(value, str) and value.strip():
            return [self._truncate(value, 120)]
        return []
