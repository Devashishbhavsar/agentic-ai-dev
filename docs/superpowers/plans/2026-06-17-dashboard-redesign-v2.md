# Dashboard Redesign v2 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the OpenClaw dashboard as a professional Enterprise Light SaaS UI with 7 tabs, full agent visibility, org chart, parallel workflow detail, system monitoring, and alert rules.

**Architecture:** React (no JSX, same esbuild pipeline) split into focused component files under `web/dashboard/components/`. New backend REST endpoints added to `api/gateway.py`. WebSocket data source unchanged. Agent configs saved as JSON overrides in `data/agents/`.

**Tech Stack:** React 18, esbuild, CSS custom properties, d3-force (network graph), psutil (system resources), FastAPI, SQLite (alert rules).

**Spec:** `docs/superpowers/specs/2026-06-17-dashboard-redesign-v2.md`

---

## Phase 0 — Backend API Endpoints

### Task 0: Agent roster endpoint + config override system

**Files:**
- Create: `api/routes/agents.py`
- Create: `data/agents/.gitkeep`
- Modify: `api/gateway.py` (register router)
- Create: `tests/test_agents_api.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_agents_api.py
import json, os
from pathlib import Path
from fastapi.testclient import TestClient
from api.gateway import app

client = TestClient(app)

def test_list_agents_returns_all_swarms():
    r = client.get("/v1/agents")
    assert r.status_code == 200
    data = r.json()
    assert "swarms" in data
    swarm_names = [s["name"] for s in data["swarms"]]
    for expected in ["bi", "qa", "devops", "sw_eng", "ai_eng", "data_eng", "release"]:
        assert expected in swarm_names

def test_list_agents_includes_agent_names():
    r = client.get("/v1/agents")
    data = r.json()
    bi = next(s for s in data["swarms"] if s["name"] == "bi")
    assert "requirements_agent" in bi["agents"]

def test_get_agent_returns_config(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_CONFIG_DIR", str(tmp_path))
    r = client.get("/v1/agents/requirements_agent")
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "requirements_agent"
    assert "swarm" in data
    assert "stats" in data

def test_post_agent_config_saves_override(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_CONFIG_DIR", str(tmp_path))
    payload = {"model_tier": "fast", "max_tokens": 256}
    r = client.post("/v1/agents/requirements_agent/config", json=payload)
    assert r.status_code == 200
    saved = json.loads((tmp_path / "requirements_agent.json").read_text())
    assert saved["model_tier"] == "fast"
    assert saved["max_tokens"] == 256
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
.venv/bin/python -m pytest tests/test_agents_api.py -v 2>&1 | head -30
```
Expected: 4 failures (routes not yet registered).

- [ ] **Step 3: Create the agents router**

```python
# api/routes/agents.py
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

# Swarm → colour mapping (matches CSS design tokens)
SWARM_COLOURS = {
    "bi": "#6366f1", "qa": "#f59e0b", "devops": "#10b981",
    "sw_eng": "#ec4899", "ai_eng": "#8b5cf6",
    "data_eng": "#06b6d4", "release": "#f97316",
}

SWARM_NAMES = list(SWARM_COLOURS.keys())


def _discover_agents() -> dict[str, list[str]]:
    """Walk agents/ directory and return {swarm: [agent_name, ...]}."""
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
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    path = CONFIG_DIR / f"{name}.json"
    if path.exists():
        return json.loads(path.read_text())
    return {}


class AgentConfigPayload(BaseModel):
    model_tier: str | None = None
    max_tokens: int | None = None
    system_prompt: str | None = None


@router.get("")
def list_agents():
    """Return all swarms with their agent names and colours."""
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
    """Return agent metadata, config override, and runtime stats."""
    swarm = _agent_swarm(name)
    if swarm is None:
        raise HTTPException(status_code=404, detail=f"Agent {name!r} not found")
    override = _load_override(name)
    # Pull stats from runtime monitor if available
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
            stats["last_active"] = max(c for c in calls,
                                       key=lambda c: c.latency_ms)
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
    """Save config overrides to data/agents/{name}.json."""
    if _agent_swarm(name) is None:
        raise HTTPException(status_code=404, detail=f"Agent {name!r} not found")
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    path = CONFIG_DIR / f"{name}.json"
    current = _load_override(name)
    if payload.model_tier is not None:
        current["model_tier"] = payload.model_tier
    if payload.max_tokens is not None:
        current["max_tokens"] = payload.max_tokens
    if payload.system_prompt is not None:
        current["system_prompt"] = payload.system_prompt
    path.write_text(json.dumps(current, indent=2))
    return {"ok": True, "saved": current}
```

- [ ] **Step 4: Register the router in gateway.py**

In `api/gateway.py`, after the existing imports add:
```python
from api.routes.agents import router as agents_router
```
After `app = FastAPI(...)` and middleware setup, add:
```python
app.include_router(agents_router)
```

- [ ] **Step 5: Create the data/agents directory**

```bash
mkdir -p data/agents && touch data/agents/.gitkeep
```

- [ ] **Step 6: Run tests**

```bash
.venv/bin/python -m pytest tests/test_agents_api.py -v
```
Expected: 4 passed.

- [ ] **Step 7: Commit**

```bash
git add api/routes/agents.py api/gateway.py data/agents/.gitkeep tests/test_agents_api.py
git commit -m "feat: add /v1/agents roster and config override endpoints"
```

---

### Task 1: System status + resources endpoints

**Files:**
- Create: `api/routes/system.py`
- Modify: `api/gateway.py` (register router)
- Create: `tests/test_system_api.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_system_api.py
from fastapi.testclient import TestClient
from api.gateway import app

client = TestClient(app)

def test_system_status_returns_services():
    r = client.get("/v1/system/status")
    assert r.status_code == 200
    data = r.json()
    assert "services" in data
    names = [s["name"] for s in data["services"]]
    assert "enterprise-agent" in names
    assert "openclaw-gateway" in names

def test_system_status_has_required_fields():
    r = client.get("/v1/system/status")
    svc = r.json()["services"][0]
    for field in ("name", "active", "pid", "uptime_seconds"):
        assert field in svc, f"missing field: {field}"

def test_system_resources_returns_cpu_and_memory():
    r = client.get("/v1/system/resources")
    assert r.status_code == 200
    data = r.json()
    assert "cpu_percent" in data
    assert "memory_used_mb" in data
    assert "memory_total_mb" in data
    assert "disk" in data

def test_system_discord_returns_stats():
    r = client.get("/v1/system/discord")
    assert r.status_code == 200
    data = r.json()
    assert "connected" in data
    assert "reconnects_today" in data
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
.venv/bin/python -m pytest tests/test_system_api.py -v 2>&1 | head -20
```
Expected: 4 failures.

- [ ] **Step 3: Install psutil if not present**

```bash
.venv/bin/pip install psutil 2>&1 | tail -3
```

- [ ] **Step 4: Create the system router**

```python
# api/routes/system.py
"""System health, resources, and service management endpoints."""
from __future__ import annotations
import re
import subprocess
import time
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

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
        if start_ts and start_ts != "n/a":
            try:
                import datetime
                # Format: "Mon 2026-06-15 11:48:15 IST"
                dt = datetime.datetime.strptime(
                    start_ts.strip(), "%a %Y-%m-%d %H:%M:%S %Z")
                uptime_seconds = int(
                    (datetime.datetime.now() - dt).total_seconds())
            except Exception:
                pass
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
    proc = None
    try:
        import os
        proc = psutil.Process(os.getpid())
    except Exception:
        pass

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
        reconnects_today = sum(1 for l in lines if "gateway websocket closed" in l)
        connected = any("gateway websocket" not in l and "discord" in l.lower()
                        for l in lines[-20:])
        # Find last non-close discord event as a proxy for last activity
        for line in reversed(lines):
            if "[discord]" in line and "closed" not in line:
                last_message_ts = line[:19] if len(line) > 19 else None
                break
    except Exception:
        pass

    return {
        "connected": connected,
        "reconnects_today": reconnects_today,
        "last_activity": last_message_ts,
    }


@router.get("/openrouter-check")
def openrouter_check():
    """Test OpenRouter API key validity with a minimal request."""
    import os, httpx
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
        return {"valid": False, "reason": r.json().get("error", {}).get("message", str(r.status_code))}
    except Exception as e:
        return {"valid": False, "reason": str(e)}
```

- [ ] **Step 5: Register router in gateway.py**

```python
# add to api/gateway.py imports:
from api.routes.system import router as system_router
# add after agents_router include:
app.include_router(system_router)
```

- [ ] **Step 6: Run tests**

```bash
.venv/bin/python -m pytest tests/test_system_api.py -v
```
Expected: 4 passed.

- [ ] **Step 7: Commit**

```bash
git add api/routes/system.py api/gateway.py tests/test_system_api.py
git commit -m "feat: add /v1/system status, resources, discord, and openrouter-check endpoints"
```

---

### Task 2: Alert rules endpoints

**Files:**
- Create: `api/routes/alerts.py`
- Modify: `api/gateway.py`
- Create: `tests/test_alerts_api.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_alerts_api.py
from fastapi.testclient import TestClient
from api.gateway import app

client = TestClient(app)

def test_list_rules_returns_defaults():
    r = client.get("/v1/alerts/rules")
    assert r.status_code == 200
    rules = r.json()["rules"]
    assert isinstance(rules, list)
    assert len(rules) >= 5  # 5 default rules

def test_create_rule():
    payload = {
        "label": "Test alert",
        "metric": "total_cost_usd",
        "operator": "gt",
        "threshold": 2.0,
        "channel": "banner",
        "enabled": True,
    }
    r = client.post("/v1/alerts/rules", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["label"] == "Test alert"
    assert "id" in data

def test_delete_rule(tmp_path, monkeypatch):
    monkeypatch.setenv("ALERTS_FILE", str(tmp_path / "rules.json"))
    payload = {"label": "to delete", "metric": "total_cost_usd",
               "operator": "gt", "threshold": 99.0,
               "channel": "banner", "enabled": False}
    create_r = client.post("/v1/alerts/rules", json=payload)
    rule_id = create_r.json()["id"]
    del_r = client.delete(f"/v1/alerts/rules/{rule_id}")
    assert del_r.status_code == 200
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
.venv/bin/python -m pytest tests/test_alerts_api.py -v 2>&1 | head -20
```

- [ ] **Step 3: Create the alerts router**

```python
# api/routes/alerts.py
"""Alert rules CRUD — persisted to data/alerts/rules.json."""
from __future__ import annotations
import json
import os
import uuid
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/v1/alerts", tags=["alerts"])

DEFAULT_RULES_FILE = Path(__file__).parents[2] / "data" / "alerts" / "rules.json"

DEFAULT_RULES = [
    {"label": "Daily cost > $1.00", "metric": "total_cost_usd",
     "operator": "gt", "threshold": 1.0, "channel": "both", "enabled": False},
    {"label": "Avg latency > 10s", "metric": "avg_latency_ms",
     "operator": "gt", "threshold": 10000, "channel": "banner", "enabled": False},
    {"label": "Agent failures > 3/hour", "metric": "agent_failure_count",
     "operator": "gt", "threshold": 3, "channel": "both", "enabled": False},
    {"label": "OpenRouter spend > $2.00", "metric": "total_cost_usd",
     "operator": "gt", "threshold": 2.0, "channel": "discord", "enabled": False},
    {"label": "Service stopped", "metric": "service_down",
     "operator": "eq", "threshold": 1, "channel": "both", "enabled": False},
]


def _rules_path() -> Path:
    p = Path(os.environ.get("ALERTS_FILE", str(DEFAULT_RULES_FILE)))
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load_rules() -> list[dict]:
    p = _rules_path()
    if p.exists():
        return json.loads(p.read_text())
    # First load: seed defaults with IDs
    rules = [{"id": str(uuid.uuid4()), **r} for r in DEFAULT_RULES]
    p.write_text(json.dumps(rules, indent=2))
    return rules


def _save_rules(rules: list[dict]) -> None:
    _rules_path().write_text(json.dumps(rules, indent=2))


class RulePayload(BaseModel):
    label: str
    metric: str
    operator: str   # "gt" | "lt" | "eq"
    threshold: float
    channel: str    # "discord" | "banner" | "both"
    enabled: bool = True


@router.get("/rules")
def list_rules():
    return {"rules": _load_rules()}


@router.post("/rules")
def create_rule(payload: RulePayload):
    rules = _load_rules()
    rule = {"id": str(uuid.uuid4()), **payload.model_dump()}
    rules.append(rule)
    _save_rules(rules)
    return rule


@router.delete("/rules/{rule_id}")
def delete_rule(rule_id: str):
    rules = _load_rules()
    remaining = [r for r in rules if r["id"] != rule_id]
    if len(remaining) == len(rules):
        raise HTTPException(status_code=404, detail="Rule not found")
    _save_rules(remaining)
    return {"ok": True, "deleted": rule_id}
```

- [ ] **Step 4: Register in gateway.py**

```python
from api.routes.alerts import router as alerts_router
app.include_router(alerts_router)
```

- [ ] **Step 5: Run tests**

```bash
.venv/bin/python -m pytest tests/test_alerts_api.py -v
```
Expected: 3 passed.

- [ ] **Step 6: Run full suite to check no regressions**

```bash
.venv/bin/python -m pytest tests/ -q 2>&1 | tail -5
```
Expected: all tests passing.

- [ ] **Step 7: Commit**

```bash
git add api/routes/alerts.py api/gateway.py tests/test_alerts_api.py
git commit -m "feat: add /v1/alerts CRUD endpoint with 5 default rules"
```

---

## Phase 1 — Design System + Layout Skeleton

### Task 3: New CSS design system (Enterprise Light)

**Files:**
- Overwrite: `web/dashboard/styles.css`

- [ ] **Step 1: Replace styles.css with the new design system**

Write the complete new `web/dashboard/styles.css`. Replace the entire file — the new file is light-theme only.

Key sections in order:
1. CSS custom properties (design tokens)
2. Reset + base styles
3. Status bar (`.status-bar`, `.status-pill`)
4. Tab nav (`.tab-nav`, `.tab-nav__item`, `.tab-nav__item.is-active`)
5. KPI cards (`.kpi-card`, `.kpi-card__value`, `.kpi-card__label`, `.kpi-card__sub`)
6. Swarm cards (`.swarm-card`, `.swarm-card--bi/qa/devops/sw_eng/ai_eng/data_eng/release`)
7. Agent tags (`.agent-tag`, `.agent-tag.is-active`)
8. Slide-over panel (`.slideover`, `.slideover.is-open`, `.slideover__backdrop`)
9. Kanban board (`.board`, `.board__col`, `.board__card`)
10. Gantt timeline (`.gantt`, `.gantt__lane`, `.gantt__bar`, `.gantt__bar--running`)
11. Agent chat feed (`.chat-feed`, `.chat-feed__msg`, `.chat-feed__avatar`)
12. Data table (`.data-table`, `th`, `td`)
13. Mini chart (`.mini-chart`, `svg`)
14. Status bar pills (`.pill--ok`, `.pill--warn`, `.pill--error`)
15. System cards (`.sys-card`, `.resource-bar`)
16. Alert rule rows (`.alert-rule`, `.alert-rule__toggle`)
17. Animations (`@keyframes pulse-green`, `@keyframes shimmer`, `@keyframes typing`)

```css
/* web/dashboard/styles.css — Enterprise Light v2 */

:root {
  --bg:         #f8fafc;
  --surface:    #ffffff;
  --border:     #e2e8f0;
  --text:       #0f172a;
  --text-2:     #475569;
  --text-3:     #94a3b8;
  --accent:     #6366f1;
  --accent-bg:  #eef2ff;
  --accent-2:   #c7d2fe;
  --green:      #16a34a;
  --green-bg:   #dcfce7;
  --amber:      #f59e0b;
  --amber-bg:   #fef9c3;
  --red:        #ef4444;
  --red-bg:     #fee2e2;

  /* swarm colours */
  --bi:         #6366f1;
  --qa:         #f59e0b;
  --devops:     #10b981;
  --sw_eng:     #ec4899;
  --ai_eng:     #8b5cf6;
  --data_eng:   #06b6d4;
  --release:    #f97316;

  --r:          6px;
  --r-lg:       10px;
  --shadow:     0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04);
  --font:       Inter, system-ui, sans-serif;
  --font-mono:  'IBM Plex Mono', ui-monospace, monospace;
}

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html { font-size: 14px; }
body { background: var(--bg); color: var(--text); font-family: var(--font);
       line-height: 1.5; }
button { font: inherit; background: none; border: none; cursor: pointer; }
input, select, textarea { font: inherit; }
a { color: var(--accent); text-decoration: none; }

/* ── Status bar ─────────────────────────────────────────────── */
.status-bar {
  height: 36px; background: #f1f5f9; border-bottom: 1px solid var(--border);
  display: flex; align-items: center; padding: 0 20px; gap: 16px;
  font-size: 12px; position: sticky; top: 0; z-index: 100;
}
.status-bar__brand { font-weight: 600; color: var(--text-2); margin-right: auto; }
.status-bar__update { color: var(--amber); font-weight: 600; font-size: 11px; }
.pill {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 2px 8px; border-radius: 20px; font-size: 11px; font-weight: 500;
}
.pill--ok     { background: var(--green-bg); color: var(--green); }
.pill--warn   { background: var(--amber-bg); color: #92400e; }
.pill--error  { background: var(--red-bg); color: var(--red); }
.pill--neutral{ background: #f1f5f9; color: var(--text-2); }

/* ── Tab navigation ─────────────────────────────────────────── */
.tab-nav {
  display: flex; align-items: center; gap: 0; padding: 0 20px;
  background: var(--surface); border-bottom: 1px solid var(--border);
  position: sticky; top: 36px; z-index: 99;
}
.tab-nav__item {
  padding: 12px 16px; font-size: 13px; font-weight: 500;
  color: var(--text-3); border-bottom: 2px solid transparent;
  cursor: pointer; transition: color .15s, border-color .15s;
}
.tab-nav__item:hover { color: var(--text-2); }
.tab-nav__item.is-active { color: var(--accent); border-bottom-color: var(--accent); }

/* ── Page content ───────────────────────────────────────────── */
.page { padding: 24px 24px 48px; max-width: 1400px; margin: 0 auto; }

/* ── KPI cards ──────────────────────────────────────────────── */
.kpi-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px;
            margin-bottom: 20px; }
@media (max-width: 1100px) { .kpi-grid { grid-template-columns: repeat(3, 1fr); } }
@media (max-width: 700px)  { .kpi-grid { grid-template-columns: 1fr 1fr; } }
.kpi-card {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--r-lg); padding: 16px; box-shadow: var(--shadow);
}
.kpi-card__label { font-size: 11px; font-weight: 600; text-transform: uppercase;
                   letter-spacing: .06em; color: var(--text-3); margin-bottom: 4px; }
.kpi-card__value { font-size: 28px; font-weight: 700; color: var(--text);
                   line-height: 1.1; }
.kpi-card__sub   { font-size: 11px; color: var(--text-3); margin-top: 4px; }

/* ── Swarm cards ────────────────────────────────────────────── */
.swarm-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
@media (max-width: 900px) { .swarm-grid { grid-template-columns: 1fr 1fr; } }
@media (max-width: 600px) { .swarm-grid { grid-template-columns: 1fr; } }
.swarm-card {
  background: var(--surface); border: 1px solid var(--border);
  border-top: 3px solid var(--border); border-radius: var(--r-lg);
  padding: 16px; box-shadow: var(--shadow); cursor: pointer;
  transition: border-color .15s, box-shadow .15s;
}
.swarm-card:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
.swarm-card--bi       { border-top-color: var(--bi); }
.swarm-card--qa       { border-top-color: var(--qa); }
.swarm-card--devops   { border-top-color: var(--devops); }
.swarm-card--sw_eng   { border-top-color: var(--sw_eng); }
.swarm-card--ai_eng   { border-top-color: var(--ai_eng); }
.swarm-card--data_eng { border-top-color: var(--data_eng); }
.swarm-card--release  { border-top-color: var(--release); }
.swarm-card__header   { display: flex; justify-content: space-between;
                        align-items: center; margin-bottom: 10px; }
.swarm-card__name     { font-weight: 700; font-size: 15px; text-transform: uppercase;
                        letter-spacing: .04em; }
.swarm-card__count    { font-size: 11px; color: var(--text-3);
                        font-family: var(--font-mono); }
.agent-tags           { display: flex; flex-wrap: wrap; gap: 5px; }
.agent-tag {
  font-size: 11px; padding: 3px 8px; border-radius: 20px; cursor: pointer;
  background: #f1f5f9; color: var(--text-2); border: 1px solid var(--border);
  transition: background .1s, color .1s;
}
.agent-tag:hover      { background: var(--accent-bg); color: var(--accent); }
.agent-tag.is-active  { background: var(--green-bg); color: var(--green);
                        border-color: #86efac; }
.agent-tag.is-active::before { content: '● '; font-size: 8px; }
.active-badge { display: inline-flex; align-items: center; gap: 4px; font-size: 11px;
                padding: 2px 7px; border-radius: 20px;
                background: var(--green-bg); color: var(--green);
                animation: pulse-green 2s infinite; }

/* ── Slide-over panel ───────────────────────────────────────── */
.slideover-backdrop {
  position: fixed; inset: 0; background: rgba(0,0,0,0.2);
  z-index: 200; opacity: 0; pointer-events: none; transition: opacity .2s;
}
.slideover-backdrop.is-open { opacity: 1; pointer-events: auto; }
.slideover {
  position: fixed; top: 0; right: -400px; width: 400px; height: 100vh;
  background: var(--surface); border-left: 1px solid var(--border);
  box-shadow: -4px 0 20px rgba(0,0,0,0.1); z-index: 201;
  overflow-y: auto; padding: 24px; transition: right .25s ease;
}
.slideover.is-open { right: 0; }
.slideover__header { display: flex; justify-content: space-between;
                     align-items: flex-start; margin-bottom: 20px; }
.slideover__title  { font-size: 16px; font-weight: 700; }
.slideover__close  { font-size: 20px; color: var(--text-3); line-height: 1; }
.slideover__section { margin-bottom: 20px; padding-bottom: 20px;
                      border-bottom: 1px solid var(--border); }
.slideover__section:last-child { border-bottom: none; }
.slideover__section-label { font-size: 11px; font-weight: 600; text-transform: uppercase;
                             letter-spacing: .06em; color: var(--text-3); margin-bottom: 8px; }
.field { margin-bottom: 12px; }
.field label { display: block; font-size: 12px; color: var(--text-2); margin-bottom: 4px; }
.field input, .field select, .field textarea {
  width: 100%; padding: 7px 10px; border: 1px solid var(--border);
  border-radius: var(--r); font-size: 13px; background: var(--bg);
}
.field textarea { resize: vertical; }
.btn-primary { background: var(--accent); color: #fff; padding: 8px 16px;
               border-radius: var(--r); font-size: 13px; font-weight: 500; }
.btn-primary:hover { background: #4f46e5; }
.btn-ghost { padding: 8px 16px; border-radius: var(--r); font-size: 13px;
             color: var(--text-2); border: 1px solid var(--border); }
.btn-ghost:hover { background: var(--bg); }
.btn-danger { color: var(--red); border: 1px solid #fecaca; padding: 6px 12px;
              border-radius: var(--r); font-size: 12px; }

/* ── Kanban board ───────────────────────────────────────────── */
.board { overflow-x: auto; padding-bottom: 12px; }
.board__grid { display: grid; grid-template-columns: repeat(5, minmax(180px, 1fr));
               gap: 12px; min-width: 900px; }
.board__col { background: #f8fafc; border: 1px solid var(--border);
              border-radius: var(--r-lg); padding: 10px;
              max-height: 460px; overflow-y: auto;
              scrollbar-width: thin; scrollbar-color: var(--border) transparent; }
.board__col-head { display: flex; justify-content: space-between; align-items: center;
                   padding-bottom: 8px; border-bottom: 1px solid var(--border);
                   margin-bottom: 8px; }
.board__col-label { font-size: 11px; font-weight: 700; text-transform: uppercase;
                    letter-spacing: .1em; color: var(--text-3); }
.board__col-count { font-size: 11px; font-family: var(--font-mono); color: var(--text-3); }
.board__card {
  width: 100%; text-align: left; background: var(--surface);
  border: 1px solid var(--border); border-radius: var(--r);
  padding: 10px; margin-bottom: 6px; cursor: pointer;
  transition: box-shadow .15s, border-color .15s;
}
.board__card:hover  { box-shadow: var(--shadow); }
.board__card.is-selected { border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent-2); }
.board__card-name  { font-size: 12px; font-weight: 600; color: var(--text);
                     margin-bottom: 4px; }
.board__card-meta  { font-size: 11px; color: var(--text-3); }
.board__empty      { text-align: center; padding: 24px 8px; font-size: 12px;
                     color: var(--text-3); }

/* ── Gantt timeline ─────────────────────────────────────────── */
.gantt { background: var(--surface); border: 1px solid var(--border);
         border-radius: var(--r-lg); padding: 16px; }
.gantt__header { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.gantt__title  { font-size: 13px; font-weight: 600; }
.gantt__axis   { display: grid; margin-left: 100px; margin-bottom: 4px; }
.gantt__axis-label { font-size: 10px; color: var(--text-3);
                     font-family: var(--font-mono); }
.gantt__lane   { display: flex; align-items: center; gap: 8px; margin-bottom: 5px; }
.gantt__lane-name { width: 92px; font-size: 11px; color: var(--text-2);
                    text-align: right; white-space: nowrap; overflow: hidden;
                    text-overflow: ellipsis; flex-shrink: 0; }
.gantt__track  { flex: 1; height: 18px; background: #f1f5f9;
                 border-radius: 3px; position: relative; }
.gantt__bar    { position: absolute; height: 100%; border-radius: 3px;
                 transition: opacity .2s; }
.gantt__bar--done    { opacity: 0.9; }
.gantt__bar--running { animation: shimmer 1.2s infinite; }
.gantt__bar--waiting { background: #e2e8f0 !important; opacity: 0.5; }
.gantt__empty  { text-align: center; padding: 32px; font-size: 13px;
                 color: var(--text-3); }

/* ── Agent chat feed ────────────────────────────────────────── */
.chat-feed { background: var(--surface); border: 1px solid var(--border);
             border-radius: var(--r-lg); padding: 16px;
             overflow-y: auto; display: flex; flex-direction: column; gap: 10px; }
.chat-feed__msg    { display: flex; gap: 8px; align-items: flex-start; }
.chat-feed__avatar { width: 28px; height: 28px; border-radius: 50%;
                     display: flex; align-items: center; justify-content: center;
                     font-size: 9px; font-weight: 700; color: #fff;
                     flex-shrink: 0; text-transform: uppercase; }
.chat-feed__body   { flex: 1; }
.chat-feed__header { display: flex; gap: 6px; align-items: baseline; margin-bottom: 2px; }
.chat-feed__name   { font-size: 12px; font-weight: 600; }
.chat-feed__time   { font-size: 10px; color: var(--text-3);
                     font-family: var(--font-mono); }
.chat-feed__text   { font-size: 12px; color: var(--text-2); line-height: 1.4; }
.chat-feed__typing { display: inline-flex; gap: 3px; align-items: center; }
.chat-feed__typing span { width: 5px; height: 5px; border-radius: 50%;
                          background: var(--text-3); animation: typing 1s infinite; }
.chat-feed__typing span:nth-child(2) { animation-delay: .15s; }
.chat-feed__typing span:nth-child(3) { animation-delay: .30s; }
.chat-feed__empty  { text-align: center; padding: 32px; font-size: 13px;
                     color: var(--text-3); }

/* ── Data table ─────────────────────────────────────────────── */
.data-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.data-table th { padding: 8px 12px; text-align: left; font-size: 11px; font-weight: 600;
                 text-transform: uppercase; letter-spacing: .05em; color: var(--text-3);
                 border-bottom: 1px solid var(--border); background: #f8fafc; }
.data-table td { padding: 10px 12px; border-bottom: 1px solid #f1f5f9;
                 vertical-align: middle; }
.data-table tr:hover td { background: #f8fafc; }
.data-table tr.is-selected td { background: var(--accent-bg); }

/* ── Mini chart ─────────────────────────────────────────────── */
.mini-chart { background: var(--surface); border: 1px solid var(--border);
              border-radius: var(--r-lg); padding: 16px; }
.mini-chart__title { font-size: 12px; font-weight: 600; color: var(--text-2);
                     margin-bottom: 8px; }
.mini-chart__svg   { display: block; width: 100%; }

/* ── System cards ───────────────────────────────────────────── */
.sys-section   { margin-bottom: 24px; }
.sys-section h3 { font-size: 14px; font-weight: 600; margin-bottom: 12px;
                  padding-bottom: 8px; border-bottom: 1px solid var(--border); }
.sys-card { background: var(--surface); border: 1px solid var(--border);
            border-radius: var(--r-lg); padding: 16px; }
.sys-grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.resource-bar  { height: 6px; background: #f1f5f9; border-radius: 3px;
                 overflow: hidden; margin-top: 6px; margin-bottom: 2px; }
.resource-bar__fill { height: 100%; border-radius: 3px;
                      background: var(--accent); transition: width .5s; }
.resource-bar__fill--warn { background: var(--amber); }
.resource-bar__fill--danger { background: var(--red); }

/* ── Alert rules ────────────────────────────────────────────── */
.alert-rule { display: flex; align-items: center; gap: 12px; padding: 12px 0;
              border-bottom: 1px solid #f1f5f9; }
.alert-rule__toggle { flex-shrink: 0; }
.alert-rule__label { flex: 1; font-size: 13px; }
.alert-rule__channel { font-size: 11px; color: var(--text-3); white-space: nowrap; }
.toggle { position: relative; width: 36px; height: 20px; }
.toggle input { opacity: 0; width: 0; height: 0; }
.toggle__slider { position: absolute; inset: 0; border-radius: 20px;
                  background: #cbd5e1; cursor: pointer; transition: background .2s; }
.toggle__slider::before { content: ''; position: absolute; width: 14px; height: 14px;
                          top: 3px; left: 3px; background: #fff; border-radius: 50%;
                          transition: transform .2s; }
.toggle input:checked + .toggle__slider { background: var(--accent); }
.toggle input:checked + .toggle__slider::before { transform: translateX(16px); }

/* ── Org chart ──────────────────────────────────────────────── */
.org-chart    { background: var(--surface); border: 1px solid var(--border);
                border-radius: var(--r-lg); padding: 16px; overflow: hidden; }
.org-chart__toolbar { display: flex; justify-content: flex-end; gap: 8px;
                      margin-bottom: 12px; }
.org-chart__view-btn { padding: 5px 12px; border-radius: var(--r); font-size: 12px;
                       font-weight: 500; color: var(--text-2);
                       border: 1px solid var(--border); }
.org-chart__view-btn.is-active { background: var(--accent); color: #fff;
                                  border-color: var(--accent); }
.org-chart__svg { display: block; width: 100%; height: 500px; }
.org-node circle { cursor: pointer; transition: opacity .15s; }
.org-node circle:hover { opacity: 0.8; }
.org-node text  { font-size: 10px; font-family: var(--font); pointer-events: none; }
.org-link       { fill: none; stroke: var(--border); stroke-width: 1.5; }
.org-link--active { stroke: var(--accent); stroke-width: 2; }

/* ── Live event feed ────────────────────────────────────────── */
.event-feed { background: var(--surface); border: 1px solid var(--border);
              border-radius: var(--r-lg); padding: 16px; }
.event-feed__header { display: flex; justify-content: space-between; align-items: center;
                      margin-bottom: 10px; }
.event-feed__title  { font-size: 13px; font-weight: 600; }
.event-feed__autoscroll { font-size: 11px; color: var(--text-3); cursor: pointer; }
.event-item { display: flex; align-items: baseline; gap: 8px; padding: 5px 0;
              border-bottom: 1px solid #f8fafc; font-size: 12px; }
.event-item__type { font-family: var(--font-mono); font-size: 11px; font-weight: 600;
                    padding: 1px 6px; border-radius: 4px; white-space: nowrap; }
.event-item__agent { color: var(--text-2); white-space: nowrap; }
.event-item__time  { margin-left: auto; font-size: 10px; color: var(--text-3);
                     font-family: var(--font-mono); white-space: nowrap; }

/* Event type colours */
.type--workflow_finished { background: var(--green-bg); color: var(--green); }
.type--workflow_started  { background: var(--accent-bg); color: var(--accent); }
.type--agent_finished    { background: #f0fdf4; color: #15803d; }
.type--agent_started     { background: #eff6ff; color: #1d4ed8; }
.type--model_call        { background: #fef9c3; color: #92400e; }
.type--agent_trace       { background: #f5f3ff; color: #6d28d9; }

/* ── Badges ─────────────────────────────────────────────────── */
.badge { display: inline-flex; align-items: center; padding: 2px 7px;
         border-radius: 20px; font-size: 11px; font-weight: 500; }
.badge--success  { background: var(--green-bg); color: var(--green); }
.badge--running  { background: var(--accent-bg); color: var(--accent); }
.badge--failed   { background: var(--red-bg); color: var(--red); }
.badge--pending  { background: #f1f5f9; color: var(--text-2); }
.badge--bi       { background: #eef2ff; color: #4338ca; }
.badge--qa       { background: var(--amber-bg); color: #92400e; }
.badge--devops   { background: #d1fae5; color: #065f46; }
.badge--cache    { background: #f1f5f9; color: var(--text-2); }

/* ── Search input ───────────────────────────────────────────── */
.search-bar { display: flex; align-items: center; gap: 8px; }
.search-input { padding: 7px 12px; border: 1px solid var(--border);
                border-radius: var(--r); font-size: 13px; background: var(--surface);
                color: var(--text); width: 260px; }
.search-input:focus { outline: none; border-color: var(--accent);
                      box-shadow: 0 0 0 2px var(--accent-2); }

/* ── Empty states ───────────────────────────────────────────── */
.empty-state { text-align: center; padding: 48px 24px; }
.empty-state__icon  { font-size: 36px; margin-bottom: 12px; }
.empty-state__title { font-size: 15px; font-weight: 600; margin-bottom: 6px; }
.empty-state__body  { font-size: 13px; color: var(--text-3); }

/* ── Animations ─────────────────────────────────────────────── */
@keyframes pulse-green {
  0%, 100% { box-shadow: 0 0 0 0 rgba(22,163,74,.4); }
  50%       { box-shadow: 0 0 0 4px rgba(22,163,74,.1); }
}
@keyframes shimmer {
  0%   { opacity: 1; }
  50%  { opacity: 0.6; }
  100% { opacity: 1; }
}
@keyframes typing {
  0%, 60%, 100% { transform: translateY(0); opacity: .5; }
  30%           { transform: translateY(-4px); opacity: 1; }
}

/* ── Utilities ──────────────────────────────────────────────── */
.flex        { display: flex; }
.flex-center { display: flex; align-items: center; }
.gap-8       { gap: 8px; }
.gap-12      { gap: 12px; }
.gap-16      { gap: 16px; }
.mt-12       { margin-top: 12px; }
.mt-20       { margin-top: 20px; }
.mb-12       { margin-bottom: 12px; }
.mb-20       { margin-bottom: 20px; }
.text-mono   { font-family: var(--font-mono); }
.text-sm     { font-size: 12px; }
.text-xs     { font-size: 11px; }
.text-muted  { color: var(--text-3); }
.truncate    { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.section-title { font-size: 16px; font-weight: 700; margin-bottom: 16px; }
.two-col     { display: grid; grid-template-columns: 1.5fr 1fr; gap: 16px; }
.detail-row  { display: grid; grid-template-columns: 1fr 1fr; gap: 16px;
               margin-top: 16px; }
```

- [ ] **Step 2: Build and verify no syntax errors**

```bash
cd /home/dev1029/openclaw-enterprise-agent && npm run build:dashboard 2>&1 | tail -5
```
Expected: `⚡ Done in ~50ms`

- [ ] **Step 3: Commit**

```bash
git add web/dashboard/styles.css
git commit -m "feat: new Enterprise Light CSS design system"
```

---

### Task 4: App shell — status bar + tab navigation

**Files:**
- Create: `web/dashboard/components/StatusBar.js`
- Create: `web/dashboard/components/TabNav.js`
- Modify: `web/dashboard/app.js` (replace with new shell)
- Modify: `web/dashboard/build.mjs` (add component entry points)

- [ ] **Step 1: Create StatusBar component**

```javascript
// web/dashboard/components/StatusBar.js
const { createElement: h, useState, useEffect } = React;

export function StatusBar({ onUpdate }) {
  const [status, setStatus] = useState({
    gateway: null, discord: null, agent: null, openrouter: null, update: null,
  });

  useEffect(() => {
    async function fetchStatus() {
      try {
        const [sys, health] = await Promise.all([
          fetch("/v1/system/status").then(r => r.json()),
          fetch("/v1/health").then(r => r.json()),
        ]);
        const agent = sys.services?.find(s => s.name === "enterprise-agent");
        const gw    = sys.services?.find(s => s.name === "openclaw-gateway");
        setStatus(prev => ({
          ...prev,
          agent:   agent?.active ? "ok" : "error",
          gateway: gw?.active    ? "ok" : "error",
        }));
      } catch { /* services may not be ready */ }

      try {
        const disc = await fetch("/v1/system/discord").then(r => r.json());
        setStatus(prev => ({
          ...prev,
          discord: disc.connected ? "ok" : "warn",
        }));
      } catch { }
    }
    fetchStatus();
    const t = setInterval(fetchStatus, 30000);
    return () => clearInterval(t);
  }, []);

  const pill = (label, state) => {
    const cls = state === "ok" ? "pill--ok" : state === "warn" ? "pill--warn" : "pill--neutral";
    const dot = state === "ok" ? "● " : state === "error" ? "✗ " : "⚠ ";
    return h("span", { className: `pill ${cls}`, title: label }, dot + label);
  };

  return h("div", { className: "status-bar" },
    h("span", { className: "status-bar__brand" }, "OpenClaw / Control Plane"),
    pill("Gateway", status.gateway),
    pill("Discord", status.discord),
    pill("Agent Service", status.agent),
    status.update && h("span", { className: "status-bar__update" },
      `⬆ ${status.update} available`),
  );
}
```

- [ ] **Step 2: Create TabNav component**

```javascript
// web/dashboard/components/TabNav.js
const { createElement: h } = React;

const TABS = [
  { id: "overview",   label: "Overview" },
  { id: "agents",     label: "Agents" },
  { id: "orgchart",   label: "Org Chart" },
  { id: "workflows",  label: "Workflows" },
  { id: "history",    label: "History" },
  { id: "system",     label: "System" },
  { id: "settings",   label: "Settings" },
];

export function TabNav({ activeTab, onTabChange }) {
  return h("nav", { className: "tab-nav" },
    TABS.map(t =>
      h("button", {
        key: t.id,
        className: `tab-nav__item${activeTab === t.id ? " is-active" : ""}`,
        onClick: () => onTabChange(t.id),
      }, t.label)
    )
  );
}
```

- [ ] **Step 3: Rewrite app.js as the app shell**

Replace `web/dashboard/app.js` entirely:

```javascript
// web/dashboard/app.js — Enterprise Light v2 shell
import React, { useState, useCallback } from "react";
import { createRoot } from "react-dom/client";
import { StatusBar } from "./components/StatusBar.js";
import { TabNav }    from "./components/TabNav.js";

// Tab pages — loaded inline for now, replaced in later tasks
function Placeholder({ name }) {
  return React.createElement("div", { className: "page" },
    React.createElement("div", { className: "empty-state" },
      React.createElement("div", { className: "empty-state__icon" }, "🔧"),
      React.createElement("div", { className: "empty-state__title" }, `${name} tab`),
      React.createElement("div", { className: "empty-state__body" }, "Coming soon"),
    )
  );
}

function App() {
  const [activeTab, setActiveTab] = useState("overview");

  const page = () => React.createElement(Placeholder, { name: activeTab });

  return React.createElement(React.Fragment, null,
    React.createElement(StatusBar, {}),
    React.createElement(TabNav, { activeTab, onTabChange: setActiveTab }),
    page(),
  );
}

createRoot(document.getElementById("root")).render(
  React.createElement(App)
);
```

- [ ] **Step 4: Update build.mjs to handle component imports**

Open `web/dashboard/build.mjs`. Verify the `entryPoints` includes `app.js` and `format` is `esm` or `iife`. If using `bundle: true` (default esbuild), no changes needed — it will follow the imports automatically. Confirm:

```bash
head -20 web/dashboard/build.mjs
```

If it uses `bundle: true`, no change needed. If it lists files explicitly, add the component directory.

- [ ] **Step 5: Build and open in browser**

```bash
npm run build:dashboard 2>&1 | tail -5
curl -s http://localhost:8000/dashboard | grep -c "OpenClaw"
```
Expected: build succeeds, page returns HTML.

- [ ] **Step 6: Verify in browser**

Open `http://localhost:8000/dashboard`. Should see:
- Status bar across top with pills
- 7 tab buttons
- "Coming soon" placeholder for each tab

- [ ] **Step 7: Commit**

```bash
git add web/dashboard/app.js web/dashboard/components/
git commit -m "feat: app shell with status bar + 7-tab navigation"
```

---

## Phase 2 — Overview Tab

### Task 5: Overview tab — KPIs + Workflows + Live Feed

**Files:**
- Create: `web/dashboard/components/Overview.js`
- Create: `web/dashboard/hooks/useDashboard.js`
- Modify: `web/dashboard/app.js` (import + wire Overview)

- [ ] **Step 1: Extract WebSocket hook**

```javascript
// web/dashboard/hooks/useDashboard.js
import { useState, useEffect, useRef } from "react";

export function useDashboard() {
  const [data, setData]         = useState(null);
  const [streamState, setStreamState] = useState("connecting");
  const [updatedAt, setUpdatedAt]     = useState(null);
  const wsRef = useRef(null);

  useEffect(() => {
    function connect() {
      const proto = location.protocol === "https:" ? "wss:" : "ws:";
      const ws = new WebSocket(`${proto}//${location.host}/v1/dashboard/stream`);
      wsRef.current = ws;

      ws.onopen  = () => setStreamState("live");
      ws.onclose = () => {
        setStreamState("reconnecting");
        setTimeout(connect, 3000);
      };
      ws.onerror = () => setStreamState("reconnecting");
      ws.onmessage = (e) => {
        try {
          const d = JSON.parse(e.data);
          setData(d);
          setUpdatedAt(new Date());
        } catch { /* ignore malformed */ }
      };
    }
    connect();
    return () => { wsRef.current?.close(); };
  }, []);

  return { data, streamState, updatedAt };
}
```

- [ ] **Step 2: Create Overview component**

```javascript
// web/dashboard/components/Overview.js
import React, { useMemo, useState, useRef, useEffect } from "react";

const h = React.createElement;

function KpiCard({ label, value, sub, spark }) {
  return h("div", { className: "kpi-card" },
    h("div", { className: "kpi-card__label" }, label),
    h("div", { className: "kpi-card__value" }, value),
    sub  && h("div", { className: "kpi-card__sub" }, sub),
    spark && h(Sparkline, { values: spark }),
  );
}

function Sparkline({ values }) {
  if (!values?.length) return null;
  const w = 80, h2 = 24, pad = 2;
  const max = Math.max(...values, 1);
  const xs = values.map((_, i) => pad + (i / (values.length - 1 || 1)) * (w - pad * 2));
  const ys = values.map(v => h2 - pad - (v / max) * (h2 - pad * 2));
  const d = xs.map((x, i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)} ${ys[i].toFixed(1)}`).join(" ");
  return h("svg", { viewBox: `0 0 ${w} ${h2}`, style: { width: "100%", height: 24, marginTop: 8 } },
    h("path", { d, fill: "none", stroke: "var(--accent)", strokeWidth: 1.5 }),
  );
}

function WorkflowItem({ wf, onClick }) {
  const elapsed = wf.duration_ms
    ? `${(wf.duration_ms / 1000).toFixed(1)}s`
    : wf.started_at
      ? `${Math.floor((Date.now() - new Date(wf.started_at).getTime()) / 1000)}s`
      : "—";
  return h("div", { className: "board__card", onClick, style: { cursor: "pointer" } },
    h("div", { className: "flex-center gap-8 mb-12" },
      h("span", { className: `badge badge--${wf.pipeline || "pending"}` }, wf.pipeline || "general"),
      h("span", { className: `badge badge--${wf.status || "running"}` }, wf.status || "running"),
    ),
    h("div", { className: "board__card-name truncate" }, wf.request || "—"),
    h("div", { className: "board__card-meta text-mono" },
      `${elapsed} · ${wf.current_agent || "—"}`),
  );
}

const EVENT_COLOURS = {
  workflow_finished: "type--workflow_finished",
  workflow_started:  "type--workflow_started",
  agent_finished:    "type--agent_finished",
  agent_started:     "type--agent_started",
  model_call:        "type--model_call",
  agent_trace:       "type--agent_trace",
};

function EventFeed({ events }) {
  const [paused, setPaused] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!paused && ref.current) ref.current.scrollTop = 0;
  }, [events, paused]);

  return h("div", { className: "event-feed" },
    h("div", { className: "event-feed__header" },
      h("span", { className: "event-feed__title" }, "Live Events"),
      h("span", {
        className: "event-feed__autoscroll",
        onClick: () => setPaused(p => !p),
      }, paused ? "▶ Resume" : "⏸ Pause"),
    ),
    h("div", { ref, style: { maxHeight: 340, overflowY: "auto" } },
      events.slice(0, 50).map((ev, i) =>
        h("div", { key: i, className: "event-item" },
          h("span", {
            className: `event-item__type ${EVENT_COLOURS[ev.event_type] || ""}`,
          }, ev.event_type || "event"),
          h("span", { className: "event-item__agent truncate" },
            ev.agent_name || ev.workflow_id?.slice(-8) || "—"),
          h("span", { className: "event-item__time" },
            ev.timestamp
              ? new Date(ev.timestamp).toLocaleTimeString()
              : "—"),
        )
      ),
      events.length === 0 && h("div", { className: "chat-feed__empty" },
        "Waiting for events…"),
    ),
  );
}

export function Overview({ data }) {
  if (!data) {
    return h("div", { className: "page" },
      h("div", { className: "empty-state" },
        h("div", { className: "empty-state__icon" }, "⟳"),
        h("div", { className: "empty-state__title" }, "Connecting…"),
      )
    );
  }

  const s = data.summary || {};
  const runs = data.recent_runs || [];
  const events = data.recent_events || [];
  const active = runs.filter(r => r.status === "running");
  const cacheRate = s.cache_hits
    ? Math.round((s.cache_hits / (s.cache_hits + (s.cache_misses || 0))) * 100)
    : 0;

  // 7-day cost from latency trend (placeholder — real data from history tab later)
  const trendCost = (data.latency_trend || []).slice(-7);

  return h("div", { className: "page" },

    // KPI grid
    h("div", { className: "kpi-grid" },
      h(KpiCard, {
        label: "Active Workflows",
        value: s.active_workflows ?? 0,
        sub: `${s.active_agents ?? 0} agents busy`,
      }),
      h(KpiCard, {
        label: "Agents Busy",
        value: s.active_agents ?? 0,
        sub: "across all swarms",
      }),
      h(KpiCard, {
        label: "Cost Today",
        value: `$${(s.total_model_cost_usd || 0).toFixed(4)}`,
        sub: `${Math.round(s.avg_latency_ms || 0)} ms avg latency`,
      }),
      h(KpiCard, {
        label: "Model Calls",
        value: s.total_model_calls ?? 0,
        sub: `Cache hit ${cacheRate}%`,
        spark: trendCost,
      }),
      h(KpiCard, {
        label: "Cache Hit Rate",
        value: `${cacheRate}%`,
        sub: `${s.cache_hits ?? 0} hits · ${s.cache_misses ?? 0} misses`,
      }),
    ),

    // Two-column layout
    h("div", { className: "two-col" },

      // Left: active workflows + cost chart
      h("div", null,
        h("h2", { className: "section-title" }, "Active Workflows"),
        active.length === 0
          ? h("div", { className: "empty-state", style: { padding: "24px" } },
              h("div", { className: "empty-state__body" },
                "No active workflows — send a message via Discord or launch a demo"),
            )
          : active.map((wf, i) =>
              h(WorkflowItem, { key: wf.workflow_id || i, wf })
            ),
        runs.length > 0 && h("div", { style: { marginTop: 16 } },
          h("h3", { style: { fontSize: 13, fontWeight: 600, marginBottom: 8 } },
            "Recent Runs"),
          runs.slice(0, 5).map((r, i) =>
            h(WorkflowItem, { key: r.workflow_id || i, wf: r }),
          ),
        ),
      ),

      // Right: live event feed
      h(EventFeed, { events }),
    ),
  );
}
```

- [ ] **Step 3: Wire into app.js**

```javascript
// web/dashboard/app.js — add import and render Overview
import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import { StatusBar }  from "./components/StatusBar.js";
import { TabNav }     from "./components/TabNav.js";
import { Overview }   from "./components/Overview.js";
import { useDashboard } from "./hooks/useDashboard.js";

function Placeholder({ name }) {
  return React.createElement("div", { className: "page" },
    React.createElement("div", { className: "empty-state" },
      React.createElement("div", { className: "empty-state__icon" }, "🔧"),
      React.createElement("div", { className: "empty-state__title" }, `${name}`),
      React.createElement("div", { className: "empty-state__body" }, "Coming soon"),
    )
  );
}

function App() {
  const [activeTab, setActiveTab] = useState("overview");
  const { data, streamState } = useDashboard();

  const renderTab = () => {
    if (activeTab === "overview") return React.createElement(Overview, { data, streamState });
    return React.createElement(Placeholder, { name: activeTab });
  };

  return React.createElement(React.Fragment, null,
    React.createElement(StatusBar, {}),
    React.createElement(TabNav, { activeTab, onTabChange: setActiveTab }),
    renderTab(),
  );
}

createRoot(document.getElementById("root")).render(React.createElement(App));
```

- [ ] **Step 4: Build and verify**

```bash
npm run build:dashboard 2>&1 | tail -5
```
Open `http://localhost:8000/dashboard`. Overview tab should show 5 KPI cards, workflow list, and live event feed.

- [ ] **Step 5: Commit**

```bash
git add web/dashboard/components/Overview.js web/dashboard/hooks/useDashboard.js web/dashboard/app.js
git commit -m "feat: Overview tab with KPIs, workflow list, and live event feed"
```

---

## Phase 3 — Agents Tab

### Task 6: Agents tab — swarm cards + agent detail slide-over

**Files:**
- Create: `web/dashboard/components/Agents.js`
- Modify: `web/dashboard/app.js`

- [ ] **Step 1: Create Agents component**

```javascript
// web/dashboard/components/Agents.js
import React, { useState, useEffect } from "react";
const h = React.createElement;

const SWARM_COLOURS = {
  bi: "#6366f1", qa: "#f59e0b", devops: "#10b981",
  sw_eng: "#ec4899", ai_eng: "#8b5cf6", data_eng: "#06b6d4", release: "#f97316",
};

function AgentDetailPanel({ agent, onClose }) {
  const [config, setConfig] = useState({
    model_tier: agent?.override?.model_tier || "balanced",
    max_tokens: agent?.override?.max_tokens || 512,
    system_prompt: agent?.override?.system_prompt || "",
  });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  if (!agent) return null;

  const save = async () => {
    setSaving(true);
    try {
      await fetch(`/v1/agents/${agent.name}/config`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(config),
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } finally {
      setSaving(false);
    }
  };

  const s = agent.stats || {};

  return h(React.Fragment, null,
    h("div", {
      className: `slideover-backdrop is-open`,
      onClick: onClose,
    }),
    h("div", { className: "slideover is-open" },
      h("div", { className: "slideover__header" },
        h("div", null,
          h("div", { className: "slideover__title" }, agent.name),
          h("span", {
            className: "badge",
            style: { background: `${SWARM_COLOURS[agent.swarm]}22`,
                     color: SWARM_COLOURS[agent.swarm] },
          }, agent.swarm),
        ),
        h("button", { className: "slideover__close", onClick: onClose }, "×"),
      ),

      // Stats
      h("div", { className: "slideover__section" },
        h("div", { className: "slideover__section-label" }, "Stats"),
        h("div", { style: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 } },
          [
            ["Runs", s.total_runs ?? 0],
            ["Avg latency", `${s.avg_latency_ms ?? 0} ms`],
            ["Total cost", `$${(s.total_cost_usd || 0).toFixed(4)}`],
            ["Last active", s.last_active || "—"],
          ].map(([label, val]) =>
            h("div", { key: label },
              h("div", { className: "text-xs text-muted" }, label),
              h("div", { style: { fontWeight: 600, fontFamily: "var(--font-mono)", fontSize: 13 } }, String(val)),
            )
          )
        ),
      ),

      // Config overrides
      h("div", { className: "slideover__section" },
        h("div", { className: "slideover__section-label" }, "Config Overrides"),
        h("div", { className: "field" },
          h("label", null, "Model Tier"),
          h("select", {
            value: config.model_tier,
            onChange: e => setConfig(c => ({ ...c, model_tier: e.target.value })),
          },
            ["planning", "balanced", "fast", "long-context"].map(t =>
              h("option", { key: t, value: t }, t)
            )
          ),
        ),
        h("div", { className: "field" },
          h("label", null, "Max Tokens"),
          h("input", {
            type: "number", value: config.max_tokens,
            onChange: e => setConfig(c => ({ ...c, max_tokens: +e.target.value })),
          }),
        ),
        h("div", { className: "field" },
          h("label", null, "System Prompt Override"),
          h("textarea", {
            rows: 4, value: config.system_prompt,
            placeholder: "Leave blank to use default from code",
            onChange: e => setConfig(c => ({ ...c, system_prompt: e.target.value })),
          }),
        ),
        h("button", {
          className: "btn-primary",
          onClick: save,
          disabled: saving,
        }, saving ? "Saving…" : saved ? "✓ Saved" : "Save Changes"),
      ),
    ),
  );
}

function SwarmCard({ swarm, activeAgents, onAgentClick }) {
  const colour = SWARM_COLOURS[swarm.name] || "#6366f1";
  const activeSet = new Set(activeAgents.map(a => a.name || a.agent_name));
  const activeCount = swarm.agents.filter(n => activeSet.has(n)).length;

  return h("div", {
    className: `swarm-card swarm-card--${swarm.name}`,
    style: { borderTopColor: colour },
  },
    h("div", { className: "swarm-card__header" },
      h("div", null,
        h("span", { className: "swarm-card__name" }, swarm.name.replace("_", " ")),
        activeCount > 0 && h("span", {
          className: "active-badge",
          style: { marginLeft: 8 },
        }, `● ${activeCount} active`),
      ),
      h("span", { className: "swarm-card__count" }, `${swarm.count} agents`),
    ),
    h("div", { className: "agent-tags" },
      swarm.agents.map(name =>
        h("button", {
          key: name,
          className: `agent-tag${activeSet.has(name) ? " is-active" : ""}`,
          onClick: () => onAgentClick(name, swarm.name),
        }, name.replace("_agent", "").replace(/_/g, " "))
      )
    ),
  );
}

export function Agents({ activeAgents = [] }) {
  const [roster, setRoster]   = useState(null);
  const [query, setQuery]     = useState("");
  const [selected, setSelected] = useState(null); // { name, swarm }
  const [agentDetail, setAgentDetail] = useState(null);

  useEffect(() => {
    fetch("/v1/agents").then(r => r.json()).then(setRoster);
  }, []);

  const openAgent = async (name, swarm) => {
    try {
      const d = await fetch(`/v1/agents/${name}`).then(r => r.json());
      setAgentDetail(d);
    } catch {
      setAgentDetail({ name, swarm, stats: {}, override: {} });
    }
  };

  if (!roster) return h("div", { className: "page" },
    h("div", { className: "empty-state" }, h("div", { className: "empty-state__body" }, "Loading agents…"))
  );

  const filtered = query
    ? roster.swarms.map(s => ({
        ...s,
        agents: s.agents.filter(n => n.includes(query.toLowerCase())),
      })).filter(s => s.agents.length > 0)
    : roster.swarms;

  return h("div", { className: "page" },
    h("div", { className: "flex-center gap-12 mb-20" },
      h("h1", { className: "section-title", style: { margin: 0 } },
        `${roster.total} agents across ${roster.swarms.length} swarms`),
      h("input", {
        className: "search-input",
        placeholder: "Search agents…",
        value: query,
        onChange: e => setQuery(e.target.value),
        style: { marginLeft: "auto" },
      }),
    ),
    h("div", { className: "swarm-grid" },
      filtered.map(swarm =>
        h(SwarmCard, {
          key: swarm.name,
          swarm,
          activeAgents,
          onAgentClick: openAgent,
        })
      )
    ),
    agentDetail && h(AgentDetailPanel, {
      agent: agentDetail,
      onClose: () => setAgentDetail(null),
    }),
  );
}
```

- [ ] **Step 2: Add Agents tab to app.js**

```javascript
// add import to app.js:
import { Agents } from "./components/Agents.js";

// update renderTab() in App:
if (activeTab === "agents") {
  return React.createElement(Agents, {
    activeAgents: data?.active_agents || [],
  });
}
```

- [ ] **Step 3: Build and verify**

```bash
npm run build:dashboard 2>&1 | tail -5
```
Open `http://localhost:8000/dashboard`, click Agents tab.
- Should see 7 swarm cards with colour-coded top borders
- Each agent listed as a tag
- Clicking a tag → slide-over panel opens with stats + config form

- [ ] **Step 4: Commit**

```bash
git add web/dashboard/components/Agents.js web/dashboard/app.js
git commit -m "feat: Agents tab with 7 swarm cards and agent detail slide-over"
```

---

## Phase 4 — Org Chart Tab

### Task 7: Org Chart — SVG tree + d3-force network

**Files:**
- Create: `web/dashboard/components/OrgChart.js`
- Modify: `web/dashboard/app.js`
- Modify: `package.json` (add d3-force)

- [ ] **Step 1: Install d3-force**

```bash
cd /home/dev1029/openclaw-enterprise-agent && npm install d3-force 2>&1 | tail -3
```

- [ ] **Step 2: Create OrgChart component**

```javascript
// web/dashboard/components/OrgChart.js
import React, { useState, useEffect, useRef, useCallback } from "react";
const h = React.createElement;

const SWARM_COLOURS = {
  bi: "#6366f1", qa: "#f59e0b", devops: "#10b981",
  sw_eng: "#ec4899", ai_eng: "#8b5cf6", data_eng: "#06b6d4", release: "#f97316",
};

// ── Hierarchy Tree (SVG, no library) ────────────────────────────
function HierarchyTree({ roster, activeAgents, connections, onNodeClick }) {
  const activeSet = new Set(activeAgents.map(a => a.name || a.agent_name));
  const W = 900, H = 480;
  const rootX = W / 2, rootY = 40;
  const swarmY = 130;
  const agentY = 260;

  const swarmCount = roster.swarms.length;
  const swarmSpacing = W / (swarmCount + 1);

  // Draw swarm nodes
  const swarmNodes = roster.swarms.map((s, i) => ({
    ...s, x: swarmSpacing * (i + 1), y: swarmY,
  }));

  // All agent nodes per swarm
  const agentNodes = swarmNodes.flatMap(swarm => {
    const count = swarm.agents.length;
    const totalW = (count - 1) * 90;
    const startX = swarm.x - totalW / 2;
    return swarm.agents.map((name, j) => ({
      name, swarm: swarm.name, colour: SWARM_COLOURS[swarm.name],
      x: startX + j * 90, y: agentY + Math.floor(j / 8) * 70,
      active: activeSet.has(name),
    }));
  });

  return h("svg", {
    viewBox: `0 0 ${W} ${H + 80}`,
    style: { width: "100%", height: "auto" },
  },
    // Root → swarm lines
    swarmNodes.map(s =>
      h("line", {
        key: `root-${s.name}`,
        x1: rootX, y1: rootY + 16, x2: s.x, y2: swarmY - 16,
        stroke: "#e2e8f0", strokeWidth: 1.5,
      })
    ),
    // Swarm → agent lines (only first few to avoid clutter)
    swarmNodes.flatMap(sn =>
      agentNodes
        .filter(a => a.swarm === sn.name)
        .slice(0, 6)
        .map(a =>
          h("line", {
            key: `sw-ag-${a.name}`,
            x1: sn.x, y1: swarmY + 16, x2: a.x, y2: a.y - 10,
            stroke: "#e2e8f0", strokeWidth: 1,
          })
        )
    ),
    // Root node
    h("g", {
      className: "org-node", transform: `translate(${rootX},${rootY})`,
      style: { cursor: "pointer" },
    },
      h("circle", { r: 20, fill: "#6366f1" }),
      h("text", { textAnchor: "middle", dy: 32, fontSize: 10, fill: "#475569" },
        "Orchestrator"),
    ),
    // Swarm nodes
    swarmNodes.map(s =>
      h("g", {
        key: s.name, className: "org-node",
        transform: `translate(${s.x},${s.y})`,
        style: { cursor: "pointer" },
        onClick: () => onNodeClick({ type: "swarm", name: s.name }),
      },
        h("circle", { r: 16, fill: SWARM_COLOURS[s.name], opacity: 0.85 }),
        h("text", { textAnchor: "middle", dy: 28, fontSize: 10, fill: "#475569" },
          s.name.replace("_", " ")),
      )
    ),
    // Agent nodes
    agentNodes.map(a =>
      h("g", {
        key: a.name, className: "org-node",
        transform: `translate(${a.x},${a.y})`,
        style: { cursor: "pointer" },
        onClick: () => onNodeClick({ type: "agent", name: a.name, swarm: a.swarm }),
      },
        h("circle", {
          r: 9, fill: a.active ? "#dcfce7" : "#f1f5f9",
          stroke: a.colour, strokeWidth: a.active ? 2.5 : 1.5,
        }),
        a.active && h("circle", { r: 13, fill: "none", stroke: "#16a34a",
                                   strokeWidth: 1, opacity: 0.4 }),
        h("text", { textAnchor: "middle", dy: 20, fontSize: 8, fill: "#94a3b8" },
          a.name.replace("_agent", "")),
      )
    ),
  );
}

// ── Network / Force Graph ────────────────────────────────────────
function NetworkGraph({ roster, activeAgents, connections, onNodeClick }) {
  const svgRef = useRef(null);
  const [nodes, setNodes] = useState([]);
  const [links, setLinks] = useState([]);
  const simRef = useRef(null);

  useEffect(() => {
    // Build node + link lists
    const allNodes = [
      { id: "orchestrator", label: "Orchestrator", type: "root",
        colour: "#6366f1", r: 22 },
      ...roster.swarms.map(s => ({
        id: `swarm_${s.name}`, label: s.name, type: "swarm",
        colour: SWARM_COLOURS[s.name], swarm: s.name, r: 16,
      })),
      ...roster.swarms.flatMap(s =>
        s.agents.map(name => ({
          id: name, label: name.replace("_agent",""), type: "agent",
          colour: SWARM_COLOURS[s.name], swarm: s.name, r: 8,
        }))
      ),
    ];
    const allLinks = [
      ...roster.swarms.map(s => ({
        source: "orchestrator", target: `swarm_${s.name}`, type: "hierarchy",
      })),
      ...roster.swarms.flatMap(s =>
        s.agents.map(name => ({
          source: `swarm_${s.name}`, target: name, type: "hierarchy",
        }))
      ),
      ...connections.map(c => ({
        source: c.from_agent, target: c.to_agent, type: "handoff",
      })),
    ];

    // Initialise positions
    const W = 800, H = 480;
    allNodes.forEach(n => {
      if (!n.x) { n.x = W/2 + (Math.random()-.5)*300;
                  n.y = H/2 + (Math.random()-.5)*200; }
    });

    setNodes(allNodes.map(n => ({...n})));
    setLinks(allLinks);

    // Simple force simulation using d3-force
    import("d3-force").then(({ forceSimulation, forceLink, forceManyBody, forceCenter, forceCollide }) => {
      const sim = forceSimulation(allNodes)
        .force("link", forceLink(allLinks).id(d => d.id).distance(60).strength(0.3))
        .force("charge", forceManyBody().strength(-120))
        .force("center", forceCenter(W/2, H/2))
        .force("collide", forceCollide(d => d.r + 6))
        .on("tick", () => {
          setNodes([...allNodes]);
        })
        .on("end", () => {
          setLinks([...allLinks]);
        });
      simRef.current = sim;
    });

    return () => simRef.current?.stop();
  }, [roster, connections]);

  return h("svg", {
    ref: svgRef,
    viewBox: "0 0 800 480",
    style: { width: "100%", height: 480, overflow: "visible" },
  },
    // Links
    links.map((l, i) => {
      const src = nodes.find(n => n.id === (l.source?.id || l.source));
      const tgt = nodes.find(n => n.id === (l.target?.id || l.target));
      if (!src || !tgt) return null;
      return h("line", {
        key: i,
        x1: src.x, y1: src.y, x2: tgt.x, y2: tgt.y,
        stroke: l.type === "handoff" ? "#6366f1" : "#e2e8f0",
        strokeWidth: l.type === "handoff" ? 2 : 1,
        strokeDasharray: l.type === "handoff" ? "4,2" : "none",
        opacity: l.type === "handoff" ? 0.8 : 0.6,
      });
    }),
    // Nodes
    nodes.map(n =>
      h("g", {
        key: n.id, className: "org-node",
        transform: `translate(${n.x||0},${n.y||0})`,
        style: { cursor: "pointer" },
        onClick: () => onNodeClick(n),
      },
        h("circle", { r: n.r, fill: n.colour, opacity: 0.85 }),
        h("text", { textAnchor: "middle", dy: n.r + 12,
                    fontSize: n.type === "root" ? 10 : 8, fill: "#475569" },
          n.label),
      )
    ),
  );
}

export function OrgChart({ data, activeAgents = [] }) {
  const [view, setView] = useState("tree");
  const [agentDetail, setAgentDetail] = useState(null);
  const [roster, setRoster] = useState(null);

  useEffect(() => {
    fetch("/v1/agents").then(r => r.json()).then(setRoster);
  }, []);

  const connections = data?.workflow_connections || [];

  const handleNodeClick = async (node) => {
    if (node.type === "agent" || (node.id && !node.id.startsWith("swarm_") && node.id !== "orchestrator")) {
      const name = node.name || node.id;
      try {
        const d = await fetch(`/v1/agents/${name}`).then(r => r.json());
        setAgentDetail(d);
      } catch {
        setAgentDetail({ name, swarm: node.swarm, stats: {}, override: {} });
      }
    }
  };

  if (!roster) return h("div", { className: "page" },
    h("div", { className: "empty-state" },
      h("div", { className: "empty-state__body" }, "Loading org chart…"))
  );

  // Lazily import AgentDetailPanel to avoid circular dep
  const AgentDetailPanel = React.lazy(() =>
    import("./Agents.js").then(m => ({ default: (props) => {
      // Inline minimal panel to avoid circular dependency
      if (!props.agent) return null;
      const s = props.agent.stats || {};
      return h(React.Fragment, null,
        h("div", { className: "slideover-backdrop is-open", onClick: props.onClose }),
        h("div", { className: "slideover is-open" },
          h("div", { className: "slideover__header" },
            h("div", { className: "slideover__title" }, props.agent.name),
            h("button", { className: "slideover__close", onClick: props.onClose }, "×"),
          ),
          h("div", { className: "slideover__section" },
            h("div", { className: "slideover__section-label" }, "Stats"),
            h("div", { className: "text-sm text-muted" },
              `Runs: ${s.total_runs ?? 0} · Cost: $${(s.total_cost_usd||0).toFixed(4)}`),
          ),
        ),
      );
    }}))
  );

  return h("div", { className: "page" },
    h("div", { className: "org-chart" },
      h("div", { className: "org-chart__toolbar" },
        h("button", {
          className: `org-chart__view-btn${view === "tree" ? " is-active" : ""}`,
          onClick: () => setView("tree"),
        }, "🌳 Hierarchy"),
        h("button", {
          className: `org-chart__view-btn${view === "network" ? " is-active" : ""}`,
          onClick: () => setView("network"),
        }, "🕸 Network"),
      ),
      view === "tree"
        ? h(HierarchyTree, { roster, activeAgents, connections, onNodeClick: handleNodeClick })
        : h(NetworkGraph, { roster, activeAgents, connections, onNodeClick: handleNodeClick }),
    ),
    agentDetail && h(React.Suspense, { fallback: null },
      h(AgentDetailPanel, { agent: agentDetail, onClose: () => setAgentDetail(null) })
    ),
  );
}
```

- [ ] **Step 3: Wire into app.js**

```javascript
import { OrgChart } from "./components/OrgChart.js";
// in renderTab():
if (activeTab === "orgchart") return React.createElement(OrgChart, {
  data, activeAgents: data?.active_agents || [],
});
```

- [ ] **Step 4: Build and verify**

```bash
npm run build:dashboard 2>&1 | tail -5
```
Open Org Chart tab. Tree view shows orchestrator → swarms → agents. Toggle to Network view shows force-directed bubbles.

- [ ] **Step 5: Commit**

```bash
git add web/dashboard/components/OrgChart.js web/dashboard/app.js package.json
git commit -m "feat: Org Chart tab with SVG hierarchy tree and d3-force network graph"
```

---

## Phase 5 — Workflows Tab

### Task 8: Workflows tab — Kanban + Gantt timeline + Agent chat feed

**Files:**
- Create: `web/dashboard/components/Workflows.js`
- Modify: `web/dashboard/app.js`

- [ ] **Step 1: Create Workflows component**

```javascript
// web/dashboard/components/Workflows.js
import React, { useState, useMemo } from "react";
const h = React.createElement;

const SWARM_COLOURS = {
  bi: "#6366f1", qa: "#f59e0b", devops: "#10b981",
  sw_eng: "#ec4899", ai_eng: "#8b5cf6", data_eng: "#06b6d4", release: "#f97316",
};

const COLUMNS = ["inbox","assigned","in_progress","review","done"];
const COL_LABELS = { inbox:"Inbox", assigned:"Assigned", in_progress:"In Progress",
                     review:"Review", done:"Done" };

function categorise(run) {
  if (run.status === "success" || run.status === "failed") return "done";
  if (run.stage === "review")       return "review";
  if (run.stage === "in_progress" || run.status === "running") return "in_progress";
  if (run.current_agent)            return "assigned";
  return "inbox";
}

function BoardCard({ run, isSelected, onClick }) {
  const col = categorise(run);
  const dur = run.duration_ms ? `${(run.duration_ms/1000).toFixed(1)}s` : "—";
  return h("button", {
    className: `board__card${isSelected ? " is-selected" : ""}`,
    onClick,
  },
    h("div", { className: "flex-center gap-8", style: { marginBottom: 4 } },
      h("span", { className: `badge badge--${run.pipeline || "cache"}` },
        run.pipeline || "general"),
      h("span", { className: `badge badge--${run.status || "running"}` },
        run.status || "running"),
    ),
    h("div", { className: "board__card-name truncate" }, run.request || "—"),
    h("div", { className: "board__card-meta text-mono" },
      `${dur} · ${run.current_agent || run.stage || "—"}`),
  );
}

function GanttTimeline({ run, events }) {
  if (!run) return h("div", { className: "gantt" },
    h("div", { className: "gantt__empty" }, "Select a workflow card to inspect its timeline"));

  // Build agent lanes from events
  const wfEvents = events.filter(e => e.workflow_id === run.workflow_id);
  const agentNames = [...new Set(wfEvents.map(e => e.agent_name).filter(Boolean))];
  if (!agentNames.length && run.current_agent) agentNames.push(run.current_agent);

  const startMs = run.started_at ? new Date(run.started_at).getTime() : Date.now();
  const endMs = run.finished_at
    ? new Date(run.finished_at).getTime()
    : startMs + (run.duration_ms || 5000);
  const totalMs = Math.max(endMs - startMs, 1000);

  const lanes = agentNames.map(name => {
    const starts = wfEvents.filter(e => e.agent_name === name && e.event_type === "agent_started");
    const ends   = wfEvents.filter(e => e.agent_name === name && e.event_type === "agent_finished");
    const laneStart = starts[0]?.timestamp
      ? (new Date(starts[0].timestamp).getTime() - startMs) / totalMs
      : 0;
    const laneEnd   = ends[0]?.timestamp
      ? (new Date(ends[0].timestamp).getTime() - startMs) / totalMs
      : run.status === "running" ? 1 : laneStart + 0.2;
    const running = ends.length === 0 && run.status === "running";
    const swarm = Object.keys(SWARM_COLOURS).find(s => name.includes(s)) || "bi";
    return { name, start: laneStart, end: laneEnd, running,
             colour: SWARM_COLOURS[swarm] };
  });

  return h("div", { className: "gantt" },
    h("div", { className: "gantt__header" },
      h("span", { className: "gantt__title", style: { fontSize: 13, fontWeight: 600 } },
        "Timeline"),
      h("span", { className: "text-xs text-muted" },
        `${(totalMs/1000).toFixed(1)}s total`),
    ),
    lanes.map(lane =>
      h("div", { key: lane.name, className: "gantt__lane" },
        h("div", { className: "gantt__lane-name" }, lane.name.replace("_agent","")),
        h("div", { className: "gantt__track" },
          h("div", {
            className: `gantt__bar ${lane.running ? "gantt__bar--running" : "gantt__bar--done"}`,
            style: {
              left: `${lane.start * 100}%`,
              width: `${Math.max((lane.end - lane.start) * 100, 4)}%`,
              background: lane.colour,
            },
          }),
        ),
      )
    ),
    lanes.length === 0 && h("div", { className: "gantt__empty", style: { padding: 16 } },
      "No agent timing data available for this workflow"),
  );
}

function AgentChatFeed({ run, events, traces }) {
  if (!run) return h("div", { className: "chat-feed" },
    h("div", { className: "chat-feed__empty" }, "Select a workflow to see the agent feed"));

  const SWARM_COLOURS_LOCAL = SWARM_COLOURS;
  const wfEvents = events.filter(e => e.workflow_id === run.workflow_id);
  const wfTraces = (traces || []).filter(t => t.workflow_id === run.workflow_id);

  const msgs = [
    ...wfEvents.map(e => ({
      ts: e.timestamp, type: "event",
      agent: e.agent_name || "system",
      text: `${e.event_type}${e.agent_name ? ` · ${e.agent_name}` : ""}`,
    })),
    ...wfTraces.map(t => ({
      ts: t.timestamp, type: "trace",
      agent: t.agent_name || "system",
      text: t.output || t.summary || JSON.stringify(t).slice(0, 120),
    })),
  ].sort((a, b) => new Date(a.ts) - new Date(b.ts));

  const swarmOf = name =>
    Object.keys(SWARM_COLOURS_LOCAL).find(s => (name||"").includes(s)) || "bi";

  const isTyping = run.status === "running" && run.current_agent;

  return h("div", { className: "chat-feed", style: { height: "100%", maxHeight: 320 } },
    msgs.slice(-30).map((m, i) =>
      h("div", { key: i, className: "chat-feed__msg" },
        h("div", {
          className: "chat-feed__avatar",
          style: { background: SWARM_COLOURS_LOCAL[swarmOf(m.agent)] || "#6366f1" },
        }, (m.agent||"?").slice(0,2).toUpperCase()),
        h("div", { className: "chat-feed__body" },
          h("div", { className: "chat-feed__header" },
            h("span", { className: "chat-feed__name" }, m.agent),
            h("span", { className: "chat-feed__time" },
              m.ts ? new Date(m.ts).toLocaleTimeString() : ""),
          ),
          h("div", { className: "chat-feed__text" }, m.text),
        ),
      )
    ),
    isTyping && h("div", { className: "chat-feed__msg" },
      h("div", {
        className: "chat-feed__avatar",
        style: { background: SWARM_COLOURS_LOCAL[swarmOf(run.current_agent)] || "#6366f1" },
      }, (run.current_agent||"?").slice(0,2).toUpperCase()),
      h("div", { className: "chat-feed__body" },
        h("div", { className: "chat-feed__header" },
          h("span", { className: "chat-feed__name" }, run.current_agent),
        ),
        h("div", { className: "chat-feed__typing" },
          h("span"), h("span"), h("span"),
          h("span", { style: { marginLeft: 4, fontSize: 11, color: "var(--text-3)" } }, "working…")
        ),
      ),
    ),
    msgs.length === 0 && h("div", { className: "chat-feed__empty" },
      "No events recorded for this workflow yet"),
  );
}

export function Workflows({ data }) {
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState(null);

  const runs = data?.recent_runs || [];
  const events = data?.recent_events || [];
  const traces = data?.recent_traces || [];

  const filtered = query
    ? runs.filter(r =>
        r.request?.toLowerCase().includes(query) ||
        r.pipeline?.includes(query) ||
        r.current_agent?.includes(query))
    : runs;

  const grouped = useMemo(() => {
    const g = Object.fromEntries(COLUMNS.map(c => [c, []]));
    filtered.forEach(r => g[categorise(r)].push(r));
    return g;
  }, [filtered]);

  const selected = runs.find(r => r.workflow_id === selectedId);

  return h("div", { className: "page" },
    // Filter bar
    h("div", { className: "flex-center gap-12 mb-20" },
      h("h1", { className: "section-title", style: { margin: 0 } }, "Workflows"),
      h("input", {
        className: "search-input",
        placeholder: "Filter by agent, pipeline, stage…",
        value: query,
        onChange: e => setQuery(e.target.value),
        style: { marginLeft: "auto" },
      }),
    ),

    // Kanban board
    h("div", { className: "board" },
      h("div", { className: "board__grid" },
        COLUMNS.map(col =>
          h("div", { key: col, className: "board__col" },
            h("div", { className: "board__col-head" },
              h("span", { className: "board__col-label" }, COL_LABELS[col]),
              h("span", { className: "board__col-count" }, grouped[col].length),
            ),
            grouped[col].length === 0
              ? h("div", { className: "board__empty" }, "Empty")
              : grouped[col].map(r =>
                  h(BoardCard, {
                    key: r.workflow_id,
                    run: r,
                    isSelected: r.workflow_id === selectedId,
                    onClick: () => setSelectedId(
                      r.workflow_id === selectedId ? null : r.workflow_id),
                  })
                ),
          )
        )
      )
    ),

    // Workflow detail (Gantt + Chat Feed)
    h("div", { className: "detail-row", style: { marginTop: 24 } },
      h(GanttTimeline, { run: selected, events }),
      h(AgentChatFeed, { run: selected, events, traces }),
    ),
  );
}
```

- [ ] **Step 2: Wire into app.js**

```javascript
import { Workflows } from "./components/Workflows.js";
// in renderTab():
if (activeTab === "workflows") return React.createElement(Workflows, { data });
```

- [ ] **Step 3: Build and verify**

```bash
npm run build:dashboard 2>&1 | tail -5
```
Open Workflows tab. Click a Done card. Gantt timeline and Agent Chat Feed should appear below.

- [ ] **Step 4: Commit**

```bash
git add web/dashboard/components/Workflows.js web/dashboard/app.js
git commit -m "feat: Workflows tab with Kanban board, Gantt timeline, and agent chat feed"
```

---

## Phase 6 — History + System + Settings Tabs

### Task 9: History tab with analytics

**Files:**
- Create: `web/dashboard/components/History.js`
- Modify: `web/dashboard/app.js`

- [ ] **Step 1: Create History component**

```javascript
// web/dashboard/components/History.js
import React, { useState } from "react";
const h = React.createElement;

function BarChart({ values, labels, colour = "#6366f1" }) {
  const max = Math.max(...values, 0.01);
  const W = 300, H = 80, barW = W / values.length - 4;
  return h("svg", { viewBox: `0 0 ${W} ${H + 20}`, className: "mini-chart__svg" },
    values.map((v, i) => {
      const barH = (v / max) * H;
      return h("g", { key: i },
        h("rect", {
          x: i * (barW + 4) + 2, y: H - barH,
          width: barW, height: barH,
          fill: colour, opacity: 0.8, rx: 2,
        }),
        labels && h("text", {
          x: i * (barW + 4) + barW / 2 + 2, y: H + 14,
          textAnchor: "middle", fontSize: 8, fill: "#94a3b8",
        }, labels[i]),
      );
    }),
  );
}

export function History({ data }) {
  const [expandedId, setExpandedId] = useState(null);
  const [filter, setFilter] = useState("all");

  const runs = (data?.recent_runs || []).filter(r =>
    filter === "all" || r.status === filter);

  const modelUsage = data?.model_usage || {};
  const modelRows = Object.entries(modelUsage).map(([model, stats]) => ({
    model: model.replace("openrouter/", ""),
    calls: stats.call_count || 0,
    avgLatency: stats.avg_latency_ms ? `${Math.round(stats.avg_latency_ms)} ms` : "—",
    avgCost: stats.avg_cost_usd ? `$${stats.avg_cost_usd.toFixed(4)}` : "—",
  }));

  // 7-day cost placeholder (real data from runtime trend)
  const trend = data?.cost_trend || Array(7).fill(0);
  const days = Array.from({ length: 7 }, (_, i) => {
    const d = new Date(); d.setDate(d.getDate() - 6 + i);
    return d.toLocaleDateString("en", { weekday: "short" });
  });

  return h("div", { className: "page" },
    // Filter bar
    h("div", { className: "flex-center gap-8 mb-20" },
      h("h1", { className: "section-title", style: { margin: 0 } }, "Run History"),
      ["all","success","running","failed"].map(f =>
        h("button", {
          key: f,
          className: `badge badge--${f === "all" ? "pending" : f}`,
          style: { cursor: "pointer", marginLeft: f === "all" ? "auto" : 0,
                   opacity: filter === f ? 1 : 0.5 },
          onClick: () => setFilter(f),
        }, f)
      ),
    ),

    // Runs table
    h("div", { style: { background: "var(--surface)", border: "1px solid var(--border)",
                         borderRadius: "var(--r-lg)", marginBottom: 24, overflow: "hidden" } },
      h("table", { className: "data-table" },
        h("thead", null,
          h("tr", null,
            ["Request","Pipeline","Status","Duration","Model Calls","Cost","Time"].map(col =>
              h("th", { key: col }, col)
            )
          )
        ),
        h("tbody", null,
          runs.map(r =>
            h(React.Fragment, { key: r.workflow_id },
              h("tr", {
                style: { cursor: "pointer" },
                className: expandedId === r.workflow_id ? "is-selected" : "",
                onClick: () => setExpandedId(
                  r.workflow_id === expandedId ? null : r.workflow_id),
              },
                h("td", { className: "truncate", style: { maxWidth: 200 } }, r.request || "—"),
                h("td", null, h("span", { className: `badge badge--${r.pipeline||"cache"}` },
                  r.pipeline || "general")),
                h("td", null, h("span", { className: `badge badge--${r.status||"running"}` },
                  r.status || "running")),
                h("td", { className: "text-mono" },
                  r.duration_ms ? `${(r.duration_ms/1000).toFixed(1)}s` : "—"),
                h("td", { className: "text-mono" }, r.model_calls || "—"),
                h("td", { className: "text-mono" },
                  r.cost_usd ? `$${r.cost_usd.toFixed(4)}` : "—"),
                h("td", { className: "text-mono text-muted" },
                  r.started_at
                    ? new Date(r.started_at).toLocaleTimeString()
                    : "—"),
              ),
              expandedId === r.workflow_id && h("tr", null,
                h("td", { colSpan: 7, style: { padding: "12px 16px",
                                               background: "#f8fafc" } },
                  h("div", { className: "text-sm text-muted" },
                    `Workflow ID: ${r.workflow_id} · Stage: ${r.stage || "—"} · Agent: ${r.current_agent || "—"}`),
                ),
              ),
            )
          ),
          runs.length === 0 && h("tr", null,
            h("td", { colSpan: 7, style: { textAlign: "center", padding: 24,
                                           color: "var(--text-3)" } },
              "No runs match this filter"),
          ),
        ),
      ),
    ),

    // Analytics row
    h("div", { style: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 } },

      // Model performance
      h("div", { className: "mini-chart" },
        h("div", { className: "mini-chart__title" }, "Model Performance"),
        h("table", { className: "data-table" },
          h("thead", null, h("tr", null,
            ["Model","Calls","Avg Latency","Avg Cost"].map(c => h("th",{key:c},c)))),
          h("tbody", null,
            modelRows.map(r =>
              h("tr", { key: r.model },
                h("td", { className: "text-mono text-sm" }, r.model),
                h("td", { className: "text-mono" }, r.calls),
                h("td", { className: "text-mono" }, r.avgLatency),
                h("td", { className: "text-mono" }, r.avgCost),
              )
            ),
            modelRows.length === 0 && h("tr", null,
              h("td", { colSpan: 4, style: { textAlign:"center", color:"var(--text-3)", padding:12 }},
                "No model data yet")),
          ),
        ),
      ),

      // 7-day cost chart
      h("div", { className: "mini-chart" },
        h("div", { className: "mini-chart__title" }, "7-day Cost (USD)"),
        h(BarChart, { values: trend, labels: days, colour: "#6366f1" }),
      ),
    ),
  );
}
```

- [ ] **Step 2: Wire into app.js**

```javascript
import { History } from "./components/History.js";
// in renderTab():
if (activeTab === "history") return React.createElement(History, { data });
```

- [ ] **Step 3: Commit after verifying build**

```bash
npm run build:dashboard 2>&1 | tail -3 && \
git add web/dashboard/components/History.js web/dashboard/app.js && \
git commit -m "feat: History tab with runs table, model perf table, and cost bar chart"
```

---

### Task 10: System tab

**Files:**
- Create: `web/dashboard/components/System.js`
- Modify: `web/dashboard/app.js`

- [ ] **Step 1: Create System component**

```javascript
// web/dashboard/components/System.js
import React, { useState, useEffect } from "react";
const h = React.createElement;

function ResourceBar({ percent, warn = 70, danger = 90 }) {
  const cls = percent >= danger ? "danger" : percent >= warn ? "warn" : "";
  return h("div", { className: "resource-bar" },
    h("div", {
      className: `resource-bar__fill${cls ? ` resource-bar__fill--${cls}` : ""}`,
      style: { width: `${Math.min(percent, 100)}%` },
    }),
  );
}

export function System() {
  const [status, setStatus]  = useState(null);
  const [res, setRes]        = useState(null);
  const [discord, setDiscord] = useState(null);
  const [orStatus, setOrStatus] = useState(null);
  const [restarting, setRestarting] = useState({});

  async function load() {
    try {
      const [s, r, d] = await Promise.all([
        fetch("/v1/system/status").then(x => x.json()),
        fetch("/v1/system/resources").then(x => x.json()),
        fetch("/v1/system/discord").then(x => x.json()),
      ]);
      setStatus(s); setRes(r); setDiscord(d);
    } catch(e) { console.error(e); }
  }

  useEffect(() => { load(); const t = setInterval(load, 5000); return () => clearInterval(t); }, []);

  const restart = async (name) => {
    setRestarting(r => ({...r, [name]: true}));
    try {
      await fetch("/v1/system/restart", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ service: name }),
      });
      setTimeout(load, 3000);
    } finally {
      setTimeout(() => setRestarting(r => ({...r, [name]: false})), 3000);
    }
  };

  const testOpenRouter = async () => {
    setOrStatus("testing…");
    try {
      const r = await fetch("/v1/system/openrouter-check").then(x => x.json());
      setOrStatus(r.valid ? "✓ Valid" : `✗ ${r.reason}`);
    } catch { setOrStatus("✗ Request failed"); }
  };

  const fmtUptime = (s) => {
    if (!s) return "—";
    const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600),
          m = Math.floor((s % 3600) / 60);
    return d > 0 ? `${d}d ${h}h` : h > 0 ? `${h}h ${m}m` : `${m}m`;
  };

  return h("div", { className: "page" },

    // Services
    h("div", { className: "sys-section" },
      h("h3", null, "Services"),
      h("div", { style: { background:"var(--surface)", border:"1px solid var(--border)",
                           borderRadius:"var(--r-lg)", overflow:"hidden" } },
        h("table", { className: "data-table" },
          h("thead", null, h("tr", null,
            ["Service","Status","PID","Uptime","Restarts","Actions"].map(c=>h("th",{key:c},c)))),
          h("tbody", null,
            (status?.services || []).map(svc =>
              h("tr", { key: svc.name },
                h("td", { className: "text-mono" }, svc.name),
                h("td", null, h("span", {
                  className: `pill ${svc.active ? "pill--ok" : "pill--error"}` },
                  svc.active ? "● running" : "✗ stopped")),
                h("td", { className: "text-mono text-muted" }, svc.pid || "—"),
                h("td", { className: "text-mono" }, fmtUptime(svc.uptime_seconds)),
                h("td", { className: "text-mono" }, svc.restarts ?? "—"),
                h("td", null,
                  h("button", {
                    className: "btn-ghost text-sm",
                    disabled: restarting[svc.name],
                    onClick: () => restart(svc.name),
                  }, restarting[svc.name] ? "Restarting…" : "Restart"),
                ),
              )
            )
          ),
        ),
      ),
    ),

    // Resources
    h("div", { className: "sys-section" },
      h("h3", null, "System Resources"),
      h("div", { className: "sys-grid-2" },
        h("div", { className: "sys-card" },
          h("div", { className: "text-xs text-muted", style:{marginBottom:8} }, "CPU"),
          h("div", { style:{fontSize:24,fontWeight:700} }, `${res?.cpu_percent ?? "—"}%`),
          res && h(ResourceBar, { percent: res.cpu_percent }),
          h("div", { className: "text-xs text-muted", style:{marginTop:16,marginBottom:8} }, "Memory"),
          res && h(React.Fragment, null,
            h("div", { style:{fontSize:14} },
              `${res.memory_used_mb} MB / ${res.memory_total_mb} MB`),
            h(ResourceBar, { percent: res.memory_percent }),
          ),
        ),
        h("div", { className: "sys-card" },
          h("div", { className: "text-xs text-muted", style:{marginBottom:8} }, "Disk"),
          (res?.disk || []).map(d =>
            h("div", { key: d.label, style:{marginBottom:8} },
              h("div", { className: "flex-center gap-8" },
                h("span", { className: "text-sm" }, d.label),
                h("span", { className: "text-mono text-sm text-muted", style:{marginLeft:"auto"} },
                  `${d.size_mb} MB`),
              ),
              h("div", { className: "text-xs text-muted" }, d.path),
            )
          ),
        ),
      ),
    ),

    // OpenRouter
    h("div", { className: "sys-section" },
      h("h3", null, "OpenRouter"),
      h("div", { className: "sys-card" },
        h("div", { className: "flex-center gap-12" },
          h("span", { className: "text-sm" }, "API Key: sk-or-v1-…"),
          h("button", { className: "btn-ghost text-sm", onClick: testOpenRouter },
            "Test Connection"),
          orStatus && h("span", {
            className: "text-sm",
            style: { color: orStatus.startsWith("✓") ? "var(--green)" : "var(--red)" },
          }, orStatus),
        ),
      ),
    ),

    // Discord
    h("div", { className: "sys-section" },
      h("h3", null, "Discord"),
      h("div", { className: "sys-card" },
        discord
          ? h("div", { style:{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12} },
              [
                ["Status", discord.connected ? "● Connected" : "✗ Disconnected"],
                ["Reconnects today", discord.reconnects_today ?? "—"],
                ["Last activity", discord.last_activity || "—"],
              ].map(([k,v]) =>
                h("div", { key: k },
                  h("div", { className: "text-xs text-muted" }, k),
                  h("div", { className: "text-sm", style:{marginTop:2} }, v),
                )
              )
            )
          : h("div", { className: "text-sm text-muted" }, "Loading…"),
      ),
    ),
  );
}
```

- [ ] **Step 2: Wire into app.js**

```javascript
import { System } from "./components/System.js";
if (activeTab === "system") return React.createElement(System, {});
```

- [ ] **Step 3: Build, verify, commit**

```bash
npm run build:dashboard 2>&1 | tail -3 && \
git add web/dashboard/components/System.js web/dashboard/app.js && \
git commit -m "feat: System tab with service controls, CPU/mem/disk, Discord and OpenRouter status"
```

---

### Task 11: Settings / Alerts tab

**Files:**
- Create: `web/dashboard/components/Settings.js`
- Modify: `web/dashboard/app.js`

- [ ] **Step 1: Create Settings component**

```javascript
// web/dashboard/components/Settings.js
import React, { useState, useEffect } from "react";
const h = React.createElement;

const METRICS = [
  { value: "total_cost_usd",      label: "Daily Cost (USD)" },
  { value: "avg_latency_ms",      label: "Avg Latency (ms)" },
  { value: "agent_failure_count", label: "Agent Failures (per hour)" },
  { value: "service_down",        label: "Service Down" },
];

const OPERATORS = [
  { value: "gt", label: "greater than" },
  { value: "lt", label: "less than" },
  { value: "eq", label: "equals" },
];

const CHANNELS = [
  { value: "banner",  label: "Banner only" },
  { value: "discord", label: "Discord only" },
  { value: "both",    label: "Banner + Discord" },
];

export function Settings() {
  const [rules, setRules] = useState([]);
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({
    label: "", metric: "total_cost_usd", operator: "gt",
    threshold: "", channel: "banner", enabled: true,
  });

  const load = () =>
    fetch("/v1/alerts/rules").then(r => r.json()).then(d => setRules(d.rules));

  useEffect(() => { load(); }, []);

  const toggle = async (rule) => {
    await fetch("/v1/alerts/rules", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...rule, enabled: !rule.enabled }),
    });
    load();
  };

  const del = async (id) => {
    await fetch(`/v1/alerts/rules/${id}`, { method: "DELETE" });
    load();
  };

  const submit = async (e) => {
    e.preventDefault();
    await fetch("/v1/alerts/rules", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...form, threshold: parseFloat(form.threshold) }),
    });
    setAdding(false);
    setForm({ label:"", metric:"total_cost_usd", operator:"gt",
               threshold:"", channel:"banner", enabled:true });
    load();
  };

  return h("div", { className: "page" },
    h("div", { className: "flex-center gap-12 mb-20" },
      h("h1", { className: "section-title", style: { margin: 0 } }, "Alert Rules"),
      h("button", {
        className: "btn-primary",
        style: { marginLeft: "auto" },
        onClick: () => setAdding(a => !a),
      }, adding ? "Cancel" : "+ Add Rule"),
    ),

    // Add rule form
    adding && h("form", {
      onSubmit: submit,
      style: { background:"var(--surface)", border:"1px solid var(--border)",
               borderRadius:"var(--r-lg)", padding:16, marginBottom:16,
               display:"grid", gridTemplateColumns:"1fr 1fr 1fr 1fr auto", gap:10, alignItems:"end" },
    },
      h("div", { className: "field", style:{margin:0} },
        h("label", null, "Label"),
        h("input", { required:true, value:form.label,
                     onChange: e => setForm(f=>({...f,label:e.target.value})),
                     placeholder:"e.g. Cost spike" }),
      ),
      h("div", { className: "field", style:{margin:0} },
        h("label", null, "Metric"),
        h("select", { value:form.metric,
                      onChange: e => setForm(f=>({...f,metric:e.target.value})) },
          METRICS.map(m => h("option",{key:m.value,value:m.value},m.label))),
      ),
      h("div", { className: "field", style:{margin:0} },
        h("label", null, "Threshold"),
        h("div", { className: "flex-center gap-8" },
          h("select", { value:form.operator, style:{width:100},
                        onChange: e => setForm(f=>({...f,operator:e.target.value})) },
            OPERATORS.map(o => h("option",{key:o.value,value:o.value},o.label))),
          h("input", { required:true, type:"number", step:"any", value:form.threshold,
                       onChange: e => setForm(f=>({...f,threshold:e.target.value})),
                       placeholder:"0" }),
        ),
      ),
      h("div", { className: "field", style:{margin:0} },
        h("label", null, "Notify via"),
        h("select", { value:form.channel,
                      onChange: e => setForm(f=>({...f,channel:e.target.value})) },
          CHANNELS.map(c => h("option",{key:c.value,value:c.value},c.label))),
      ),
      h("button", { type:"submit", className:"btn-primary" }, "Add"),
    ),

    // Rules list
    h("div", { style:{background:"var(--surface)",border:"1px solid var(--border)",
                       borderRadius:"var(--r-lg)",overflow:"hidden"} },
      rules.map(rule =>
        h("div", { key: rule.id, className: "alert-rule" ,
                   style: { padding: "10px 16px" } },
          // Toggle
          h("label", { className: "toggle", title: rule.enabled ? "Enabled" : "Disabled" },
            h("input", { type:"checkbox", checked: rule.enabled,
                         onChange: () => toggle(rule) }),
            h("span", { className: "toggle__slider" }),
          ),
          // Label + condition
          h("div", { className: "alert-rule__label" },
            h("div", { style:{fontWeight:500} }, rule.label),
            h("div", { className: "text-xs text-muted" },
              `${rule.metric} ${rule.operator} ${rule.threshold}`),
          ),
          // Channel badge
          h("span", { className: "badge badge--pending alert-rule__channel" },
            rule.channel),
          // Delete
          h("button", {
            className: "btn-danger",
            onClick: () => del(rule.id),
          }, "Delete"),
        )
      ),
      rules.length === 0 && h("div", {
        style:{textAlign:"center",padding:24,color:"var(--text-3)"}},
        "No alert rules yet — click Add Rule to create one"),
    ),
  );
}
```

- [ ] **Step 2: Wire into app.js**

Final `app.js` with all 7 tabs:

```javascript
// web/dashboard/app.js — complete
import React, { useState } from "react";
import { createRoot }    from "react-dom/client";
import { StatusBar }  from "./components/StatusBar.js";
import { TabNav }     from "./components/TabNav.js";
import { Overview }   from "./components/Overview.js";
import { Agents }     from "./components/Agents.js";
import { OrgChart }   from "./components/OrgChart.js";
import { Workflows }  from "./components/Workflows.js";
import { History }    from "./components/History.js";
import { System }     from "./components/System.js";
import { Settings }   from "./components/Settings.js";
import { useDashboard } from "./hooks/useDashboard.js";

function App() {
  const [activeTab, setActiveTab] = useState("overview");
  const { data, streamState } = useDashboard();
  const agents = data?.active_agents || [];

  const tab = () => {
    switch (activeTab) {
      case "overview":  return React.createElement(Overview,  { data, streamState });
      case "agents":    return React.createElement(Agents,    { activeAgents: agents });
      case "orgchart":  return React.createElement(OrgChart,  { data, activeAgents: agents });
      case "workflows": return React.createElement(Workflows, { data });
      case "history":   return React.createElement(History,   { data });
      case "system":    return React.createElement(System,    {});
      case "settings":  return React.createElement(Settings,  {});
      default:          return null;
    }
  };

  return React.createElement(React.Fragment, null,
    React.createElement(StatusBar, {}),
    React.createElement(TabNav, { activeTab, onTabChange: setActiveTab }),
    tab(),
  );
}

createRoot(document.getElementById("root")).render(React.createElement(App));
```

- [ ] **Step 3: Build and full smoke test**

```bash
npm run build:dashboard 2>&1 | tail -5
node --check web/dashboard/app.bundle.js 2>&1
curl -s http://localhost:8000/v1/health
```
All expected: build succeeds, no syntax errors, health returns `{"status":"ok"}`.

- [ ] **Step 4: Run backend tests**

```bash
.venv/bin/python -m pytest tests/ -q 2>&1 | tail -5
```
Expected: all tests pass.

- [ ] **Step 5: Final commit**

```bash
git add web/dashboard/components/Settings.js web/dashboard/app.js
git commit -m "feat: Settings tab with CRUD alert rules + complete app.js with all 7 tabs"
```

---

## Phase 7 — Restart Service + Smoke Test

### Task 12: Deploy, restart, and verify end-to-end

- [ ] **Step 1: Restart the systemd service**

```bash
systemctl --user restart enterprise-agent
sleep 4
systemctl --user status enterprise-agent --no-pager | grep Active
```
Expected: `Active: active (running)`

- [ ] **Step 2: Verify health**

```bash
curl -s http://localhost:8000/v1/health
curl -s http://localhost:8000/v1/agents | python3 -c "import sys,json; d=json.load(sys.stdin); print('swarms:', len(d['swarms']), '| total:', d['total'])"
curl -s http://localhost:8000/v1/system/status | python3 -c "import sys,json; d=json.load(sys.stdin); [print(s['name'],s['active']) for s in d['services']]"
curl -s http://localhost:8000/v1/alerts/rules | python3 -c "import sys,json; d=json.load(sys.stdin); print('rules:', len(d['rules']))"
```
Expected:
```
{"status":"ok","version":"0.1.0"}
swarms: 7 | total: 36
enterprise-agent True
openclaw-gateway True
rules: 5
```

- [ ] **Step 3: Open the dashboard and verify all 7 tabs**

Open `http://localhost:8000/dashboard` and check each tab:
- **Overview:** 5 KPI cards visible, event feed running
- **Agents:** 7 swarm cards, all agents as tags, click one → slide-over opens
- **Org Chart:** Tree view loads, toggle to Network works
- **Workflows:** Kanban board visible, click a Done card → Gantt + Chat Feed appear
- **History:** Runs table, model performance table, cost bar chart
- **System:** Both services shown as running, CPU/memory bars, Discord status
- **Settings:** 5 default alert rules visible, toggle and Add Rule work

- [ ] **Step 4: Final commit**

```bash
git add .
git commit -m "feat: complete dashboard v2 redesign — 7 tabs, Enterprise Light, all agents visible"
```

---

## Success Criteria Checklist

- [ ] All 36 agents visible on Agents tab with correct swarm colour coding
- [ ] Org Chart renders both Hierarchy Tree and Network views; active agents pulse green
- [ ] Workflow detail shows Gantt timeline + agent chat feed for any selected run
- [ ] System tab shows live CPU/memory, both service statuses, restart buttons work
- [ ] Top status bar always shows Gateway, Discord, Agent Service, OpenRouter state
- [ ] Alert rules can be created, toggled, and deleted
- [ ] All backend tests pass (`pytest tests/ -q`)
- [ ] Page loads in < 2s, WebSocket reconnects automatically on disconnect
