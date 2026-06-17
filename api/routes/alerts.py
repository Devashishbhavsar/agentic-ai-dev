"""Alert rules CRUD — persisted to data/alerts/rules.json."""
from __future__ import annotations
import json
import logging
import os
import uuid
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

_log = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/alerts", tags=["alerts"])

_DEFAULT_RULES_FILE = Path(__file__).parents[2] / "data" / "alerts" / "rules.json"

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


def _rules_file() -> Path:
    """Return path to the rules file, re-reading env var each call."""
    return Path(os.environ.get("ALERTS_FILE", str(_DEFAULT_RULES_FILE)))


def _load_rules() -> list[dict]:
    p = _rules_file()
    if p.exists():
        return json.loads(p.read_text())
    # First load: seed defaults with IDs
    rules = [{"id": str(uuid.uuid4()), **r} for r in DEFAULT_RULES]
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rules, indent=2))
    return rules


def _save_rules(rules: list[dict]) -> None:
    p = _rules_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rules, indent=2))


class RulePayload(BaseModel):
    label: str
    metric: str
    operator: str   # "gt" | "lt" | "eq"
    threshold: float
    channel: str    # "discord" | "banner" | "both"
    enabled: bool = True


@router.get("/rules")
def list_rules():
    """Return all alert rules (seeds defaults on first call)."""
    return {"rules": _load_rules()}


@router.post("/rules")
def create_rule(payload: RulePayload):
    """Append a new alert rule and return it with its generated ID."""
    rules = _load_rules()
    rule = {"id": str(uuid.uuid4()), **payload.model_dump()}
    rules.append(rule)
    _save_rules(rules)
    return rule


@router.delete("/rules/{rule_id}")
def delete_rule(rule_id: str):
    """Delete a rule by ID. Returns 404 if not found."""
    rules = _load_rules()
    remaining = [r for r in rules if r["id"] != rule_id]
    if len(remaining) == len(rules):
        raise HTTPException(status_code=404, detail="Rule not found")
    _save_rules(remaining)
    return {"ok": True, "deleted": rule_id}
