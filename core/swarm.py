"""L3 · Ruflo swarm engine — fans tasks to agent groups in parallel with consensus."""
from __future__ import annotations

import concurrent.futures
import uuid
from dataclasses import dataclass, field
from typing import Any

from agents.base import AgentTask, AgentResult, BaseAgent
from core.model_router import ModelRouter, ModelTier, RoutingContext
from core.memory.short_term import SessionMemory


@dataclass
class SwarmResult:
    workflow_id: str
    results: list[AgentResult] = field(default_factory=list)
    consensus: dict = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)


class QueenAgent:
    """Governs consensus across swarm results before returning to OpenClaw."""

    def __init__(self, router: ModelRouter) -> None:
        self._router = router

    def reach_consensus(
        self,
        results: list[AgentResult],
        threshold: float = 0.7,
    ) -> dict:
        """Merge results — high-confidence agents win, conflicts flagged."""
        merged: dict[str, Any] = {}
        conflict_keys: list[str] = []

        for r in results:
            if r.status != "success":
                continue
            for key, value in r.results.items():
                if key not in merged:
                    merged[key] = {"value": value, "confidence": r.confidence_score or 0.5,
                                   "source": r.agent_name}
                else:
                    existing_conf = merged[key]["confidence"]
                    new_conf = r.confidence_score or 0.5
                    if abs(new_conf - existing_conf) < 0.1:
                        conflict_keys.append(key)
                    elif new_conf > existing_conf:
                        merged[key] = {"value": value, "confidence": new_conf,
                                       "source": r.agent_name}

        avg_confidence = (
            sum(r.confidence_score or 0 for r in results if r.status == "success")
            / max(1, len([r for r in results if r.status == "success"]))
        )

        return {
            "merged": {k: v["value"] for k, v in merged.items()},
            "conflicts": conflict_keys,
            "average_confidence": avg_confidence,
            "passed_threshold": avg_confidence >= threshold,
        }


class SwarmEngine:
    """L3 · Ruflo — parallel agent execution with Queen-governed consensus."""

    def __init__(
        self,
        router: ModelRouter | None = None,
        session: SessionMemory | None = None,
        max_workers: int = 8,
    ) -> None:
        self._router = router or ModelRouter()
        self._session = session
        self._max_workers = max_workers
        self._queen = QueenAgent(self._router)

    def run_swarm(
        self,
        agents: list[BaseAgent],
        task_params: dict,
        workflow_id: str | None = None,
        consensus_threshold: float = 0.7,
    ) -> SwarmResult:
        """Fan one task out to all agents in parallel, then merge via Queen."""
        workflow_id = workflow_id or str(uuid.uuid4())
        results: list[AgentResult] = []

        def _run_agent(agent: BaseAgent) -> AgentResult:
            task = AgentTask(
                task_id=str(uuid.uuid4()),
                workflow_id=workflow_id,
                operation=task_params.get("operation", "run"),
                parameters=task_params,
            )
            try:
                return agent.run(task)
            except Exception as e:
                return AgentResult(
                    task_id=task.task_id,
                    agent_name=agent.name,
                    operation=task.operation,
                    status="failure",
                    error=str(e),
                )

        with concurrent.futures.ThreadPoolExecutor(max_workers=self._max_workers) as pool:
            futures = {pool.submit(_run_agent, a): a for a in agents}
            for future in concurrent.futures.as_completed(futures):
                results.append(future.result())

        consensus = self._queen.reach_consensus(results, threshold=consensus_threshold)
        return SwarmResult(workflow_id=workflow_id, results=results, consensus=consensus)
