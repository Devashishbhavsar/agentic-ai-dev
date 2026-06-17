"""Analytics endpoint — time-series and aggregated chart data."""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter

_log = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/analytics", tags=["analytics"])

_DAYS = 7


def _date_label(iso_str: str) -> str:
    """Extract YYYY-MM-DD from an ISO timestamp string."""
    return iso_str[:10] if iso_str else ""


def _last_n_days(n: int) -> list[str]:
    today = datetime.now(tz=timezone.utc).date()
    return [(today - timedelta(days=n - 1 - i)).isoformat() for i in range(n)]


@router.get("")
def analytics():
    """
    Return aggregated chart data for the Analytics tab:
    - daily_cost       : list of {date, cost_usd} for last 7 days
    - daily_latency    : list of {date, avg_latency_ms}
    - daily_throughput : list of {date, count} — completed workflows
    - model_breakdown  : list of {model, calls, cost_usd, avg_latency_ms}
    - top_agents       : list of {agent, runs, cost_usd} top 10 by runs
    - swarm_activity   : list of {swarm, runs, cost_usd}
    """
    try:
        from core.runtime import get_runtime_monitor
        rm = get_runtime_monitor()
        with rm._lock:
            model_calls = list(rm._model_calls)
            recent_runs = list(rm._recent_runs)
    except Exception:
        _log.warning("Failed to read runtime data", exc_info=True)
        model_calls = []
        recent_runs = []

    days = _last_n_days(_DAYS)

    # ── Daily cost from model calls ──────────────────────────────
    daily_cost_map: dict[str, float] = defaultdict(float)
    daily_lat_count: dict[str, list[float]] = defaultdict(list)
    for call in model_calls:
        d = _date_label(call.timestamp)
        if d:
            daily_cost_map[d] += call.cost_usd
            daily_lat_count[d].append(call.latency_ms)

    daily_cost = [
        {"date": d, "cost_usd": round(daily_cost_map.get(d, 0), 6)}
        for d in days
    ]
    daily_latency = [
        {
            "date": d,
            "avg_latency_ms": round(
                sum(daily_lat_count[d]) / len(daily_lat_count[d]), 1
            ) if daily_lat_count.get(d) else 0,
        }
        for d in days
    ]

    # ── Daily throughput — finished workflows ────────────────────
    daily_done_map: dict[str, int] = defaultdict(int)
    for run in recent_runs:
        if run.get("status") in ("success", "failed"):
            ts = run.get("finished_at") or run.get("started_at") or ""
            d = _date_label(ts)
            if d:
                daily_done_map[d] += 1

    daily_throughput = [
        {"date": d, "count": daily_done_map.get(d, 0)}
        for d in days
    ]

    # ── Model breakdown ──────────────────────────────────────────
    model_agg: dict[str, dict] = defaultdict(lambda: {"calls": 0, "cost_usd": 0.0, "lat_sum": 0.0})
    for call in model_calls:
        key = call.model.replace("openrouter/", "").replace("anthropic/", "").replace("openai/", "")
        model_agg[key]["calls"] += 1
        model_agg[key]["cost_usd"] += call.cost_usd
        model_agg[key]["lat_sum"] += call.latency_ms

    model_breakdown = sorted([
        {
            "model": m,
            "calls": v["calls"],
            "cost_usd": round(v["cost_usd"], 6),
            "avg_latency_ms": round(v["lat_sum"] / max(1, v["calls"]), 1),
        }
        for m, v in model_agg.items()
    ], key=lambda x: -x["calls"])

    # ── Top agents by run count ──────────────────────────────────
    agent_agg: dict[str, dict] = defaultdict(lambda: {"runs": 0, "cost_usd": 0.0})
    for call in model_calls:
        name = call.agent_name or "unknown"
        agent_agg[name]["runs"] += 1
        agent_agg[name]["cost_usd"] += call.cost_usd

    top_agents = sorted([
        {"agent": a, "runs": v["runs"], "cost_usd": round(v["cost_usd"], 6)}
        for a, v in agent_agg.items()
    ], key=lambda x: -x["runs"])[:10]

    # ── Swarm activity ───────────────────────────────────────────
    swarm_colours = {
        "bi": "#6366f1", "qa": "#f59e0b", "devops": "#10b981",
        "sw_eng": "#ec4899", "ai_eng": "#8b5cf6",
        "data_eng": "#06b6d4", "release": "#f97316",
    }

    # Map agent names to swarms via agents/ directory scan
    def _agent_swarm(agent_name: str) -> str:
        from pathlib import Path
        agents_root = Path(__file__).parents[2] / "agents"
        for swarm_dir in agents_root.iterdir():
            if swarm_dir.is_dir() and (swarm_dir / f"{agent_name}.py").exists():
                return swarm_dir.name
        return "unknown"

    swarm_agg: dict[str, dict] = defaultdict(lambda: {"runs": 0, "cost_usd": 0.0})
    for call in model_calls:
        swarm = _agent_swarm(call.agent_name or "")
        swarm_agg[swarm]["runs"] += 1
        swarm_agg[swarm]["cost_usd"] += call.cost_usd

    swarm_activity = [
        {
            "swarm": s,
            "runs": v["runs"],
            "cost_usd": round(v["cost_usd"], 6),
            "colour": swarm_colours.get(s, "#94a3b8"),
        }
        for s, v in swarm_agg.items()
        if s != "unknown"
    ]

    return {
        "daily_cost": daily_cost,
        "daily_latency": daily_latency,
        "daily_throughput": daily_throughput,
        "model_breakdown": model_breakdown,
        "top_agents": top_agents,
        "swarm_activity": swarm_activity,
    }
