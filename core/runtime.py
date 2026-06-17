"""Runtime monitor for live workflows, active agents, traces, and recent model usage."""
from __future__ import annotations

import json
from collections import Counter, deque
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Callable, Iterator


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None = None) -> str:
    return (dt or _utc_now()).astimezone(timezone.utc).isoformat()


def _stage_bucket(stage: str, status: str, current_agent: str) -> str:
    normalized = (stage or "").lower()
    status_norm = (status or "").lower()
    if status_norm in {"pending_approval", "review", "needs_review"}:
        return "review"
    if status_norm in {"done", "success", "finished"}:
        return "done"
    if normalized in {"queued", "classified"}:
        return "inbox"
    if normalized.startswith("pipeline:") or normalized.startswith("0") or current_agent:
        return "in_progress"
    return "assigned"


def _board_card_from_workflow(run: dict[str, Any], agent: dict[str, Any] | None = None, trace: dict[str, Any] | None = None) -> dict[str, Any]:
    stage = agent.get("stage") if agent else run.get("stage", "")
    status = agent.get("status") if agent else run.get("status", "")
    current_agent = agent.get("agent_name") if agent else run.get("current_agent", "")
    card = {
        "workflow_id": run.get("workflow_id", ""),
        "title": run.get("request", "")[:96] or run.get("workflow_id", ""),
        "agent_name": current_agent or (trace or {}).get("agent_name", ""),
        "stage": stage or "queued",
        "task": agent.get("task") if agent else run.get("stage", ""),
        "status": status or run.get("status", "running"),
        "pipeline": run.get("pipeline", ""),
        "intent": run.get("intent", ""),
        "risk_level": run.get("risk_level", "low"),
        "approval_required": bool(run.get("approval_required", False)),
        "duration_ms": round(float(agent.get("duration_ms", 0.0) if agent else run.get("duration_ms", 0.0)), 2),
        "updated_at": run.get("updated_at", ""),
        "summary": run.get("summary", ""),
        "model": agent.get("model", "") if agent else "",
    }
    if trace:
        card["trace"] = {
            "kind": trace.get("kind", ""),
            "tool": trace.get("tool", ""),
            "output": trace.get("output", ""),
            "timestamp": trace.get("timestamp", ""),
        }
    return card


def _build_task_board(active_workflows: list[dict[str, Any]], active_agents: list[dict[str, Any]], recent_runs: list[dict[str, Any]], recent_traces: list[dict[str, Any]]) -> dict[str, Any]:
    def _latest_display_trace(traces: list[dict[str, Any]]) -> dict[str, Any] | None:
        for trace in reversed(traces):
            if trace.get("kind", "") not in {"agent_start", "agent_end"}:
                return trace
        return None

    columns = [
        {"id": "inbox", "label": "Inbox", "cards": []},
        {"id": "assigned", "label": "Assigned", "cards": []},
        {"id": "in_progress", "label": "In Progress", "cards": []},
        {"id": "review", "label": "Review", "cards": []},
        {"id": "done", "label": "Done", "cards": []},
    ]
    column_map = {column["id"]: column for column in columns}

    agent_map: dict[str, list[dict[str, Any]]] = {}
    active_agent_name_counts: Counter[tuple[str, str]] = Counter()
    for agent in active_agents:
        workflow_id = agent.get("workflow_id", "")
        agent_name = agent.get("agent_name", "")
        agent_map.setdefault(workflow_id, []).append(agent)
        if workflow_id and agent_name:
            active_agent_name_counts[(workflow_id, agent_name)] += 1

    workflow_trace_map: dict[str, list[dict[str, Any]]] = {}
    activity_trace_map: dict[str, list[dict[str, Any]]] = {}
    unscoped_agent_trace_map: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for trace in recent_traces:
        workflow_id = trace.get("workflow_id", "")
        activity_key = trace.get("activity_key", "")
        agent_name = trace.get("agent_name", "")
        workflow_trace_map.setdefault(workflow_id, []).append(trace)
        if activity_key:
            activity_trace_map.setdefault(activity_key, []).append(trace)
        elif workflow_id and agent_name:
            unscoped_agent_trace_map.setdefault((workflow_id, agent_name), []).append(trace)

    for run in active_workflows:
        wf_id = run.get("workflow_id", "")
        workflow_agents = agent_map.get(wf_id, [])
        workflow_traces = workflow_trace_map.get(wf_id, [])
        latest_trace = workflow_traces[-1] if workflow_traces else None
        if workflow_agents:
            for agent in workflow_agents:
                agent_name = agent.get("agent_name", "")
                activity_key = agent.get("activity_key", "")
                agent_trace = _latest_display_trace(
                    activity_trace_map.get(activity_key, []) if activity_key else []
                )
                if agent_trace is None and active_agent_name_counts.get((wf_id, agent_name), 0) == 1:
                    agent_trace = _latest_display_trace(
                        unscoped_agent_trace_map.get((wf_id, agent_name), [])
                    )
                card = _board_card_from_workflow(run, agent=agent, trace=agent_trace)
                bucket = _stage_bucket(card["stage"], card["status"], card["agent_name"])
                column_map[bucket]["cards"].append(card)
        else:
            card = _board_card_from_workflow(run, trace=latest_trace)
            bucket = _stage_bucket(card["stage"], card["status"], card["agent_name"])
            column_map[bucket]["cards"].append(card)

    for run in recent_runs[:10]:
        card = {
            "workflow_id": run.get("workflow_id", ""),
            "title": run.get("request", "")[:96] or run.get("workflow_id", ""),
            "agent_name": run.get("current_agent", "") or run.get("summary", "")[:32],
            "stage": run.get("stage", "finished"),
            "task": run.get("summary", "")[:72],
            "status": run.get("status", "done"),
            "pipeline": run.get("pipeline", ""),
            "intent": run.get("intent", ""),
            "risk_level": run.get("risk_level", "low"),
            "approval_required": bool(run.get("approval_required", False)),
            "duration_ms": round(float(run.get("duration_ms", 0.0)), 2),
            "updated_at": run.get("finished_at", ""),
            "summary": run.get("summary", ""),
            "model": "",
        }
        bucket = _stage_bucket(card["stage"], card["status"], card["agent_name"])
        column_map[bucket]["cards"].append(card)

    for column in columns:
        column["cards"] = sorted(
            column["cards"],
            key=lambda card: (card.get("updated_at", ""), card.get("duration_ms", 0)),
            reverse=True,
        )
        column["count"] = len(column["cards"])

    return {
        "columns": columns,
        "total_cards": sum(column["count"] for column in columns),
    }


def _preview(value: Any, limit: int = 360) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, default=str, ensure_ascii=False)
        except Exception:
            text = str(value)
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


@dataclass
class AgentActivity:
    workflow_id: str
    agent_name: str
    swarm: str
    stage: str
    task: str
    activity_key: str = ""
    model: str = ""
    status: str = "running"
    started_at: str = field(default_factory=_iso)
    ended_at: str | None = None
    duration_ms: float = 0.0


@dataclass
class WorkflowRun:
    workflow_id: str
    request: str
    user_id: str
    channel: str
    pipeline: str = ""
    intent: str = ""
    risk_level: str = "low"
    status: str = "running"
    stage: str = "queued"
    current_agent: str = ""
    approval_required: bool = False
    sub_goals: list[str] = field(default_factory=list)
    started_at: str = field(default_factory=_iso)
    updated_at: str = field(default_factory=_iso)
    finished_at: str | None = None
    duration_ms: float = 0.0
    summary: str = ""


@dataclass
class ModelCallEvent:
    timestamp: str
    workflow_id: str
    agent_name: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: float


@dataclass
class TraceEvent:
    timestamp: str
    workflow_id: str
    agent_name: str
    kind: str
    tool: str
    activity_key: str = ""
    stage: str = ""
    task: str = ""
    model: str = ""
    input: str = ""
    output: str = ""


_current_workflow_id: ContextVar[str] = ContextVar("current_workflow_id", default="")
_current_agent_name: ContextVar[str] = ContextVar("current_agent_name", default="")
_current_activity_key: ContextVar[str] = ContextVar("current_activity_key", default="")


def _resolve_activity_key(*, workflow_id: str, agent_name: str, activity_key: str = "") -> str:
    if activity_key:
        return activity_key
    current_workflow_id = _current_workflow_id.get()
    current_agent_name = _current_agent_name.get()
    current_activity_key = _current_activity_key.get()
    if (
        current_activity_key
        and workflow_id == current_workflow_id
        and agent_name == current_agent_name
    ):
        return current_activity_key
    return ""


class RuntimeMonitor:
    def __init__(self) -> None:
        self._lock = RLock()
        self._workflows: dict[str, WorkflowRun] = {}
        self._active_agents: dict[str, AgentActivity] = {}
        self._recent_runs: deque[dict[str, Any]] = deque(maxlen=50)
        self._recent_events: deque[dict[str, Any]] = deque(maxlen=160)
        self._recent_traces: deque[dict[str, Any]] = deque(maxlen=240)
        self._workflow_connections: deque[dict[str, Any]] = deque(maxlen=24)
        self._last_finished_by_workflow: dict[str, dict[str, Any]] = {}
        self._model_calls: deque[ModelCallEvent] = deque(maxlen=240)
        self._listeners: dict[int, Callable[[dict[str, Any]], None]] = {}
        self._listener_seq = 0
        self._revision = 0
        self._agent_activity_seq = 0

    def register_listener(self, listener: Callable[[dict[str, Any]], None]) -> int:
        with self._lock:
            self._listener_seq += 1
            token = self._listener_seq
            self._listeners[token] = listener
            return token

    def unregister_listener(self, token: int) -> None:
        with self._lock:
            self._listeners.pop(token, None)

    def _next_agent_key_locked(self, workflow_id: str, agent_name: str, stage: str, task: str) -> str:
        self._agent_activity_seq += 1
        return f"{workflow_id}:{agent_name}:{stage}:{task}:{self._agent_activity_seq}"

    def _latest_active_agent_for_workflow_locked(self, workflow_id: str) -> AgentActivity | None:
        active_agents = [
            agent for agent in self._active_agents.values()
            if agent.workflow_id == workflow_id
        ]
        if not active_agents:
            return None
        return max(
            active_agents,
            key=lambda agent: (agent.started_at, agent.agent_name, agent.stage, agent.task),
        )

    def _workflow_is_idle_locked(self, workflow_id: str) -> bool:
        return not any(
            agent.workflow_id == workflow_id
            for agent in self._active_agents.values()
        )

    def _snapshot_locked(self) -> dict[str, Any]:
        active_workflows = [asdict(run) for run in self._workflows.values()]
        active_agents = [asdict(agent) for agent in self._active_agents.values()]
        recent_runs = list(self._recent_runs)
        recent_events = list(self._recent_events)
        recent_traces = list(self._recent_traces)
        workflow_connections = list(self._workflow_connections)
        model_calls = list(self._model_calls)

        pipeline_counts = Counter(run.get("pipeline", "unknown") or "unknown" for run in recent_runs)
        status_counts = Counter(run.get("status", "unknown") or "unknown" for run in recent_runs)
        model_counts = Counter(call.model for call in model_calls)
        model_costs = Counter()
        model_latency = Counter()
        for call in model_calls:
            model_costs[call.model] += call.cost_usd
            model_latency[call.model] += call.latency_ms

        trend_points = [
            {
                "timestamp": call.timestamp,
                "model": call.model,
                "latency_ms": round(call.latency_ms, 2),
                "cost_usd": round(call.cost_usd, 6),
            }
            for call in model_calls[-30:]
        ]

        return {
            "revision": self._revision,
            "generated_at": _iso(),
            "summary": {
                "active_workflows": len(active_workflows),
                "active_agents": len(active_agents),
                "recent_runs": len(recent_runs),
                "recent_events": len(recent_events),
                "recent_traces": len(recent_traces),
                "total_model_calls": len(model_calls),
                "total_model_cost_usd": round(sum(model_costs.values()), 6),
                "avg_latency_ms": round(
                    sum(model_latency.values()) / max(1, len(model_calls)),
                    2,
                ),
            },
            "active_workflows": active_workflows,
            "active_agents": active_agents,
            "recent_runs": recent_runs,
            "recent_events": recent_events[-24:],
            "recent_traces": recent_traces[-40:],
            "pipeline_counts": dict(pipeline_counts),
            "status_counts": dict(status_counts),
            "model_usage": {
                model: {
                    "calls": model_counts[model],
                    "cost_usd": round(model_costs[model], 6),
                    "avg_latency_ms": round(model_latency[model] / max(1, model_counts[model]), 2),
                }
                for model in model_counts
            },
            "trend_points": trend_points,
            "workflow_connections": workflow_connections,
            "task_board": _build_task_board(active_workflows, active_agents, recent_runs, recent_traces),
        }

    def _notify(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        with self._lock:
            snapshot = self._snapshot_locked()
            listeners = list(self._listeners.values())
        message = {
            "type": event_type,
            "timestamp": _iso(),
            "revision": snapshot["revision"],
            "payload": payload or {},
            "snapshot": snapshot,
        }
        for listener in listeners:
            try:
                listener(message)
            except Exception:
                continue

    def start_workflow(self, *, workflow_id: str, request: str, user_id: str, channel: str) -> None:
        with self._lock:
            self._revision += 1
            self._workflows[workflow_id] = WorkflowRun(
                workflow_id=workflow_id,
                request=request,
                user_id=user_id,
                channel=channel,
            )
            self._last_finished_by_workflow.pop(workflow_id, None)
            self._recent_events.append({
                "type": "workflow_started",
                "workflow_id": workflow_id,
                "timestamp": _iso(),
                "request": request[:140],
            })
        self._notify("workflow_started", {"workflow_id": workflow_id, "request": request[:140]})

    def update_workflow(
        self,
        workflow_id: str,
        *,
        pipeline: str | None = None,
        stage: str | None = None,
        status: str | None = None,
        intent: str | None = None,
        risk_level: str | None = None,
        approval_required: bool | None = None,
        current_agent: str | None = None,
        sub_goals: list[str] | None = None,
    ) -> None:
        payload: dict[str, Any] | None = None
        with self._lock:
            run = self._workflows.get(workflow_id)
            if not run:
                return
            self._revision += 1
            if pipeline is not None:
                run.pipeline = pipeline
            if stage is not None:
                run.stage = stage
            if status is not None:
                run.status = status
            if intent is not None:
                run.intent = intent
            if risk_level is not None:
                run.risk_level = risk_level
            if approval_required is not None:
                run.approval_required = approval_required
            if current_agent is not None:
                run.current_agent = current_agent
            if sub_goals is not None:
                run.sub_goals = list(sub_goals)
            run.updated_at = _iso()
            payload = {
                "workflow_id": workflow_id,
                "pipeline": run.pipeline,
                "stage": run.stage,
                "status": run.status,
                "current_agent": run.current_agent,
            }
            self._recent_events.append({
                "type": "workflow_updated",
                "workflow_id": workflow_id,
                "timestamp": run.updated_at,
                "pipeline": run.pipeline,
                "stage": run.stage,
                "status": run.status,
                "current_agent": run.current_agent,
            })
        self._notify("workflow_updated", payload)

    def finish_workflow(
        self,
        workflow_id: str,
        *,
        status: str,
        summary: str = "",
        approval_required: bool | None = None,
    ) -> None:
        payload: dict[str, Any] | None = None
        with self._lock:
            run = self._workflows.pop(workflow_id, None)
            if not run:
                return
            self._revision += 1
            run.status = status
            run.summary = summary
            run.finished_at = _iso()
            run.updated_at = run.finished_at
            if approval_required is not None:
                run.approval_required = approval_required
            run.duration_ms = (
                _utc_now() - datetime.fromisoformat(run.started_at)
            ).total_seconds() * 1000
            self._last_finished_by_workflow.pop(workflow_id, None)
            payload = asdict(run)
            self._recent_runs.appendleft(payload)
            self._recent_events.append({
                "type": "workflow_finished",
                "workflow_id": workflow_id,
                "timestamp": run.finished_at,
                "status": status,
                "duration_ms": round(run.duration_ms, 2),
            })
        self._notify("workflow_finished", payload)

    @contextmanager
    def track_agent(
        self,
        *,
        workflow_id: str,
        agent_name: str,
        swarm: str,
        stage: str,
        task: str,
        model: str = "",
    ) -> Iterator[None]:
        key = ""
        activity = AgentActivity(
            workflow_id=workflow_id,
            agent_name=agent_name,
            swarm=swarm,
            stage=stage,
            task=task,
            model=model,
        )
        with self._lock:
            self._revision += 1
            previous = self._last_finished_by_workflow.get(workflow_id)
            if previous and previous.get("agent_name") and previous.get("agent_name") != agent_name and self._workflow_is_idle_locked(workflow_id):
                self._workflow_connections.append({
                    "workflow_id": workflow_id,
                    "from_agent": previous.get("agent_name", ""),
                    "to_agent": agent_name,
                    "signal": "handoff",
                    "timestamp": activity.started_at,
                    "status": "recent",
                })
            key = self._next_agent_key_locked(workflow_id, agent_name, stage, task)
            activity.activity_key = key
            self._active_agents[key] = activity
            self._recent_events.append({
                "type": "agent_started",
                "workflow_id": workflow_id,
                "agent_name": agent_name,
                "swarm": swarm,
                "stage": stage,
                "task": task,
                "timestamp": activity.started_at,
            })
            self._recent_traces.append({
                "timestamp": activity.started_at,
                "workflow_id": workflow_id,
                "agent_name": agent_name,
                "kind": "agent_start",
                "tool": swarm,
                "activity_key": key,
                "stage": stage,
                "task": task,
                "model": model,
                "input": f"{agent_name} starting {stage}",
                "output": "running",
            })
            run = self._workflows.get(workflow_id)
            if run:
                run.current_agent = agent_name
                run.stage = stage
                run.updated_at = activity.started_at
        wf_token = _current_workflow_id.set(workflow_id)
        agent_token = _current_agent_name.set(agent_name)
        activity_token = _current_activity_key.set(key)
        self._notify(
            "agent_started",
            {
                "workflow_id": workflow_id,
                "agent_name": agent_name,
                "stage": stage,
                "task": task,
            },
        )
        try:
            yield
        finally:
            _current_workflow_id.reset(wf_token)
            _current_agent_name.reset(agent_token)
            _current_activity_key.reset(activity_token)
            ended_payload: dict[str, Any] | None = None
            with self._lock:
                started = self._active_agents.pop(key, None)
                if started:
                    self._revision += 1
                    started.ended_at = _iso()
                    started.duration_ms = (
                        _utc_now() - datetime.fromisoformat(started.started_at)
                    ).total_seconds() * 1000
                    started.status = "done"
                    self._recent_events.append({
                        "type": "agent_finished",
                        "workflow_id": workflow_id,
                        "agent_name": agent_name,
                        "swarm": swarm,
                        "stage": stage,
                        "task": task,
                        "timestamp": started.ended_at,
                        "duration_ms": round(started.duration_ms, 2),
                    })
                    self._recent_traces.append({
                        "timestamp": started.ended_at,
                        "workflow_id": workflow_id,
                        "agent_name": agent_name,
                        "kind": "agent_end",
                        "tool": swarm,
                        "activity_key": key,
                        "stage": stage,
                        "task": task,
                        "model": model,
                        "input": f"{agent_name} finished {stage}",
                        "output": f"done in {round(started.duration_ms, 2)} ms",
                    })
                    self._last_finished_by_workflow[workflow_id] = {
                        "agent_name": agent_name,
                        "timestamp": started.ended_at,
                    }
                    run = self._workflows.get(workflow_id)
                    if run:
                        active_agent = self._latest_active_agent_for_workflow_locked(workflow_id)
                        if active_agent:
                            run.current_agent = active_agent.agent_name
                            run.stage = active_agent.stage
                        else:
                            run.current_agent = ""
                        run.updated_at = started.ended_at
                    ended_payload = {
                        "workflow_id": workflow_id,
                        "agent_name": agent_name,
                        "stage": stage,
                        "task": task,
                        "duration_ms": round(started.duration_ms, 2),
                    }
            if ended_payload:
                self._notify("agent_finished", ended_payload)

    def record_agent_trace(
        self,
        *,
        workflow_id: str = "",
        agent_name: str = "",
        kind: str = "tool",
        tool: str = "",
        activity_key: str = "",
        stage: str = "",
        task: str = "",
        model: str = "",
        input: Any = None,
        output: Any = None,
    ) -> None:
        resolved_workflow_id = workflow_id or _current_workflow_id.get()
        resolved_agent_name = agent_name or _current_agent_name.get()
        resolved_activity_key = _resolve_activity_key(
            workflow_id=resolved_workflow_id,
            agent_name=resolved_agent_name,
            activity_key=activity_key,
        )
        event = TraceEvent(
            timestamp=_iso(),
            workflow_id=resolved_workflow_id,
            agent_name=resolved_agent_name,
            kind=kind,
            tool=tool,
            activity_key=resolved_activity_key,
            stage=stage,
            task=task,
            model=model,
            input=_preview(input),
            output=_preview(output),
        )
        payload = asdict(event)
        with self._lock:
            self._revision += 1
            self._recent_traces.append(payload)
            self._recent_events.append({
                "type": "agent_trace",
                **payload,
            })
            run = self._workflows.get(resolved_workflow_id)
            if run:
                run.updated_at = event.timestamp
        self._notify("agent_trace", payload)

    def record_model_call(
        self,
        *,
        workflow_id: str,
        agent_name: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        latency_ms: float,
        activity_key: str = "",
    ) -> None:
        resolved_workflow_id = workflow_id or _current_workflow_id.get()
        resolved_agent_name = agent_name or _current_agent_name.get()
        resolved_activity_key = _resolve_activity_key(
            workflow_id=resolved_workflow_id,
            agent_name=resolved_agent_name,
            activity_key=activity_key,
        )
        event = ModelCallEvent(
            timestamp=_iso(),
            workflow_id=resolved_workflow_id,
            agent_name=resolved_agent_name,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
        )
        payload = {
            "timestamp": event.timestamp,
            "workflow_id": event.workflow_id,
            "agent_name": event.agent_name,
            "model": event.model,
            "input_tokens": event.input_tokens,
            "output_tokens": event.output_tokens,
            "cost_usd": round(event.cost_usd, 6),
            "latency_ms": round(event.latency_ms, 2),
        }
        with self._lock:
            self._revision += 1
            self._model_calls.append(event)
            self._recent_traces.append({
                "timestamp": event.timestamp,
                "workflow_id": event.workflow_id,
                "agent_name": event.agent_name,
                "kind": "model_call",
                "tool": model,
                "activity_key": resolved_activity_key,
                "stage": "llm",
                "task": "complete",
                "model": model,
                "input": f"{input_tokens} input tokens",
                "output": f"{output_tokens} output tokens · ${round(cost_usd, 6)} · {round(latency_ms, 2)} ms",
            })
            self._recent_events.append({
                "type": "model_call",
                **payload,
            })
            run = self._workflows.get(resolved_workflow_id)
            if run:
                run.updated_at = event.timestamp
        self._notify("model_call", payload)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return self._snapshot_locked()


_MONITOR = RuntimeMonitor()


def get_runtime_monitor() -> RuntimeMonitor:
    return _MONITOR
