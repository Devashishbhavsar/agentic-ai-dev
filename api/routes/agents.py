"""Agent roster and config override endpoints."""
from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/v1/agents", tags=["agents"])

AGENTS_DIR = Path(__file__).parents[2] / "agents"
CONFIG_DIR = Path(os.environ.get("AGENT_CONFIG_DIR",
                  str(Path(__file__).parents[2] / "data" / "agents")))

SWARM_COLOURS = {
    "bi": "#6366f1", "qa": "#f59e0b", "devops": "#10b981",
    "sw_eng": "#ec4899", "ai_eng": "#8b5cf6",
    "data_eng": "#06b6d4", "release": "#f97316",
}

SWARM_NAMES = list(SWARM_COLOURS.keys())


def _discover_agents() -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for swarm in SWARM_NAMES:
        swarm_dir = AGENTS_DIR / swarm
        if not swarm_dir.is_dir():
            continue
        agents = [
            p.stem for p in swarm_dir.glob("*.py")
            if p.stem not in ("__init__", "base")
        ]
        result[swarm] = sorted(agents)
    return result


def _agent_swarm(name: str) -> str | None:
    for swarm, agents in _discover_agents().items():
        if name in agents:
            return swarm
    return None


def _load_override(name: str) -> dict[str, Any]:
    cfg_dir = Path(os.environ.get("AGENT_CONFIG_DIR",
                   str(Path(__file__).parents[2] / "data" / "agents")))
    cfg_dir.mkdir(parents=True, exist_ok=True)
    path = cfg_dir / f"{name}.json"
    if path.exists():
        return json.loads(path.read_text())
    return {}


class AgentConfigPayload(BaseModel):
    model_tier: str | None = None
    max_tokens: int | None = None
    system_prompt: str | None = None


@router.get("")
def list_agents():
    roster = _discover_agents()
    swarms = []
    for swarm in SWARM_NAMES:
        agents = roster.get(swarm, [])
        swarms.append({
            "name": swarm,
            "colour": SWARM_COLOURS[swarm],
            "agents": agents,
            "count": len(agents),
        })
    total = sum(s["count"] for s in swarms)
    return {"swarms": swarms, "total": total}


@router.get("/{name}")
def get_agent(name: str):
    swarm = _agent_swarm(name)
    if swarm is None:
        raise HTTPException(status_code=404, detail=f"Agent {name!r} not found")
    override = _load_override(name)
    stats: dict[str, Any] = {"total_runs": 0, "avg_latency_ms": 0,
                              "total_cost_usd": 0.0, "last_active": None}
    try:
        from core.runtime import get_runtime_monitor
        rm = get_runtime_monitor()
        calls = [c for c in rm.model_calls if c.agent == name]
        if calls:
            stats["total_runs"] = len(calls)
            stats["avg_latency_ms"] = round(
                sum(c.latency_ms for c in calls) / len(calls), 1)
            stats["total_cost_usd"] = round(sum(c.cost_usd for c in calls), 6)
    except Exception:
        pass
    return {
        "name": name,
        "swarm": swarm,
        "colour": SWARM_COLOURS[swarm],
        "override": override,
        "stats": stats,
    }


@router.post("/{name}/config")
def update_agent_config(name: str, payload: AgentConfigPayload):
    if _agent_swarm(name) is None:
        raise HTTPException(status_code=404, detail=f"Agent {name!r} not found")
    cfg_dir = Path(os.environ.get("AGENT_CONFIG_DIR",
                   str(Path(__file__).parents[2] / "data" / "agents")))
    cfg_dir.mkdir(parents=True, exist_ok=True)
    path = cfg_dir / f"{name}.json"
    current = _load_override(name)
    if payload.model_tier is not None:
        current["model_tier"] = payload.model_tier
    if payload.max_tokens is not None:
        current["max_tokens"] = payload.max_tokens
    if payload.system_prompt is not None:
        current["system_prompt"] = payload.system_prompt
    path.write_text(json.dumps(current, indent=2))
    return {"ok": True, "saved": current}
