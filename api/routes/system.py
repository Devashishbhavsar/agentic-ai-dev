"""System health, resources, and service management endpoints."""
from __future__ import annotations
import logging
import os
import subprocess
import time
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

_log = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/system", tags=["system"])

SERVICES = ["enterprise-agent", "openclaw-gateway"]


def _systemctl_show(unit: str) -> dict:
    """Run systemctl show and return key=value pairs."""
    try:
        out = subprocess.check_output(
            ["systemctl", "--user", "show", unit,
             "--property=ActiveState,MainPID,ExecMainStartTimestamp,NRestarts"],
            text=True, timeout=5,
        )
        return dict(line.split("=", 1) for line in out.strip().splitlines() if "=" in line)
    except Exception:
        return {}


@router.get("/status")
def system_status():
    """Return systemd status for both services."""
    services = []
    for name in SERVICES:
        props = _systemctl_show(name)
        active = props.get("ActiveState", "unknown") == "active"
        pid = props.get("MainPID", "0")
        start_ts = props.get("ExecMainStartTimestamp", "")
        uptime_seconds = 0
        if start_ts and start_ts not in ("n/a", ""):
            try:
                import datetime
                # Format: "Mon 2026-06-15 11:48:15 IST"
                dt = datetime.datetime.strptime(
                    start_ts.strip(), "%a %Y-%m-%d %H:%M:%S %Z")
                uptime_seconds = int(
                    (datetime.datetime.now() - dt).total_seconds())
            except Exception:
                _log.warning("Failed to parse uptime for %s: %r", name, start_ts)
        services.append({
            "name": name,
            "active": active,
            "pid": pid if pid != "0" else None,
            "uptime_seconds": uptime_seconds,
            "restarts": int(props.get("NRestarts", 0)),
        })
    return {"services": services}


class RestartPayload(BaseModel):
    service: str


@router.post("/restart")
def restart_service(payload: RestartPayload):
    """Restart a named systemd user service."""
    if payload.service not in SERVICES:
        raise HTTPException(status_code=400,
                            detail=f"Unknown service: {payload.service!r}")
    try:
        subprocess.run(
            ["systemctl", "--user", "restart", payload.service],
            check=True, timeout=30,
        )
        return {"ok": True, "service": payload.service}
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/resources")
def system_resources():
    """Return CPU %, memory, and disk usage."""
    import psutil
    cpu = psutil.cpu_percent(interval=0.1)
    mem = psutil.virtual_memory()

    disk_entries = []
    project_root = Path(__file__).parents[2]
    for label, rel_path in [
        ("vector store", "data/rag"),
        ("cache", "data/cache"),
        ("agents config", "data/agents"),
    ]:
        p = project_root / rel_path
        if p.exists():
            try:
                size_bytes = sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
                disk_entries.append({"label": label, "path": str(p),
                                     "size_mb": round(size_bytes / 1_048_576, 2)})
            except Exception:
                disk_entries.append({"label": label, "path": str(p), "size_mb": 0})

    return {
        "cpu_percent": cpu,
        "memory_used_mb": round(mem.used / 1_048_576),
        "memory_total_mb": round(mem.total / 1_048_576),
        "memory_percent": mem.percent,
        "disk": disk_entries,
    }


@router.get("/discord")
def discord_stats():
    """Parse journald logs for Discord gateway stats."""
    reconnects_today = 0
    last_message_ts = None
    connected = False

    try:
        out = subprocess.check_output(
            ["journalctl", "--user", "-u", "openclaw-gateway",
             "--since", "today", "--no-pager", "-o", "cat"],
            text=True, timeout=10,
        )
        lines = out.splitlines()
        reconnects_today = sum(1 for line in lines if "gateway websocket closed" in line)
        connected = any("discord" in line.lower() and "closed" not in line.lower()
                        for line in lines[-20:])
        for line in reversed(lines):
            if "[discord]" in line.lower() and "closed" not in line:
                last_message_ts = line[:19] if len(line) > 19 else None
                break
    except Exception:
        _log.warning("Failed to read discord stats from journald", exc_info=True)

    return {
        "connected": connected,
        "reconnects_today": reconnects_today,
        "last_activity": last_message_ts,
    }


@router.get("/openrouter-check")
def openrouter_check():
    """Test OpenRouter API key validity."""
    import httpx
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        return {"valid": False, "reason": "no key configured"}
    try:
        r = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": "anthropic/claude-haiku-4-5",
                  "messages": [{"role": "user", "content": "hi"}],
                  "max_tokens": 1},
            timeout=10,
        )
        if r.status_code == 200:
            return {"valid": True}
        return {"valid": False,
                "reason": r.json().get("error", {}).get("message", str(r.status_code))}
    except Exception as e:
        return {"valid": False, "reason": str(e)}
