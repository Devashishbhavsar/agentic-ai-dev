"""Base class for all 35 Hermes agents."""
from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from core.model_router import ModelRouter, RoutingContext, ModelTier
from core.context_layer import ContextLayerBuilder
from core.retrieval import get_retrieval_service
from core.memory.short_term import SessionMemory
from skill_hub.injector import SkillInjector


@dataclass
class AgentTask:
    task_id: str
    workflow_id: str
    operation: str
    parameters: dict = field(default_factory=dict)
    context: dict = field(default_factory=dict)
    parent_task_id: str | None = None


@dataclass
class AgentResult:
    task_id: str
    agent_name: str
    operation: str
    status: str        # "success" | "failure" | "partial" | "skipped"
    results: dict = field(default_factory=dict)
    confidence_score: float | None = None
    evidence_links: list[dict] = field(default_factory=list)
    tool_trace: list[dict] = field(default_factory=list)
    cost_estimate: dict = field(default_factory=dict)
    duration_ms: float = 0.0
    error: str | None = None


class BaseAgent(ABC):
    """All Hermes agents extend this. Provides model routing, memory, skill injection, and structured output."""

    name: str = "base"
    swarm: str = "base"
    default_tier: ModelTier = ModelTier.BALANCED

    # Subclasses declare their tasks to get auto-injected skills, e.g. ["debugging", "testing"]
    skill_tasks: list[str] = []

    def __init__(
        self,
        router: ModelRouter | None = None,
        session: SessionMemory | None = None,
    ) -> None:
        self._router = router or ModelRouter()
        self._session = session
        self._tool_trace: list[dict] = []
        self._skill_injector = SkillInjector()
        self._context_builder = ContextLayerBuilder(max_messages=4, max_bullets=4)
        self._retrieval = get_retrieval_service()

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """Defines the agent's role, tools, and output format."""
        ...

    @property
    def enriched_system_prompt(self) -> str:
        """System prompt enriched with skills from the SkillHub for this agent's role/tasks."""
        return self._skill_injector.enrich(
            self.system_prompt,
            role=self.name,
            tasks=self.skill_tasks,
            max_skills=2,  # inject top 2 skills to keep prompts tight
        )

    def active_skills(self) -> list[dict]:
        """Return which skills are active for this agent (for logging/debugging)."""
        return self._skill_injector.skills_for_display(role=self.name, tasks=self.skill_tasks)

    @abstractmethod
    def run(self, task: AgentTask) -> AgentResult:
        """Execute the task and return a structured result."""
        ...

    def _llm(
        self,
        user_message: str,
        tier: ModelTier | None = None,
        max_tokens: int = 512,
        json_mode: bool = False,
        **kwargs,
    ) -> str:
        ctx = RoutingContext(
            tier=tier or self.default_tier,
            agent_name=self.name,
            requires_json=json_mode,
        )
        messages: list[dict] = []
        retrieval_source = None
        if self._session:
            retrieval_source = (
                self._session.get_agent_state("shared").get("workflow_id", "")
                or self._session.get_agent_state("orchestrator").get("workflow_id", "")
                or self._session.session_id
            )
        retrieval_pack = self._retrieval.build_context(
            user_message,
            limit=3,
            source=retrieval_source,
            agent=self.name,
        )
        system_prompt = "\n\n".join(
            part for part in [
                self.enriched_system_prompt,
                retrieval_pack.prompt,
            ] if part
        )
        self._trace(
            "retrieval",
            {
                "query": user_message[:500],
                "hits": retrieval_pack.retrieved_count,
            },
            retrieval_pack.citations,
        )
        if self._session:
            workflow_id = retrieval_source or self._session.session_id
            context_pack = self._context_builder.build(
                workflow_id=workflow_id,
                user_request=user_message,
                session=self._session,
                agent_name=self.name,
                task_label=kwargs.get("task_label", ""),
            )
            system_prompt = "\n\n".join(
                part for part in [
                    system_prompt,
                    f"Shared context: {context_pack.shared_summary}",
                    context_pack.agent_brief,
                ] if part
            )
            messages = context_pack.messages
        messages.append({"role": "user", "content": user_message})

        self._trace(
            "llm_request",
            {
                "tier": (tier or self.default_tier).value,
                "json_mode": json_mode,
                "message": user_message[:500],
            },
            "pending",
        )
        response = self._router.complete(
            messages=messages,
            system=system_prompt,
            ctx=ctx,
            max_tokens=max_tokens,
            **kwargs,
        )
        self._trace(
            "llm_response",
            {
                "tier": (tier or self.default_tier).value,
                "json_mode": json_mode,
            },
            response,
        )
        if self._session:
            self._session.add("assistant", response, agent=self.name)
        return response

    def _llm_json(self, user_message: str, tier: ModelTier | None = None) -> dict:
        # Skill: systematic-debugging — hypothesis → observe → test → verify
        # Attempt 1: clean parse
        raw = self._llm(
            user_message + "\n\nRespond with valid JSON only. No markdown, no explanation. Be concise.",
            tier=tier,
            max_tokens=700,
            json_mode=True,
        )
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass

        # Hypothesis: response was truncated or wrapped — try to extract {...}
        import re
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass

        # Fallback: ask the model to repair the broken JSON
        repair_raw = self._llm(
            f"The following JSON is malformed. Fix it and return only valid JSON:\n{raw[:800]}",
            tier=tier,
            max_tokens=700,
            json_mode=True,
        )
        repair_raw = repair_raw.strip()
        if repair_raw.startswith("```"):
            repair_raw = repair_raw.split("```")[1]
            if repair_raw.startswith("json"):
                repair_raw = repair_raw[4:]
        try:
            return json.loads(repair_raw.strip())
        except json.JSONDecodeError:
            # Last resort: return partial result rather than crash
            return {"raw_response": raw[:500], "parse_error": True}

    def _trace(self, tool: str, input: Any, output: Any) -> None:
        entry = {"tool": tool, "input": input, "output": str(output)[:500]}
        self._tool_trace.append(entry)
        try:
            from core.runtime import get_runtime_monitor

            get_runtime_monitor().record_agent_trace(
                kind="tool",
                tool=tool,
                input=input,
                output=output,
            )
        except Exception:
            pass

    def _make_result(
        self,
        task: AgentTask,
        results: dict,
        status: str = "success",
        confidence: float | None = None,
        duration_ms: float = 0.0,
        error: str | None = None,
    ) -> AgentResult:
        return AgentResult(
            task_id=task.task_id,
            agent_name=self.name,
            operation=task.operation,
            status=status,
            results=results,
            confidence_score=confidence,
            tool_trace=list(self._tool_trace),
            duration_ms=duration_ms,
            error=error,
        )
