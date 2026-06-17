import os
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


def test_delete_nonexistent_rule_returns_404(tmp_path, monkeypatch):
    monkeypatch.setenv("ALERTS_FILE", str(tmp_path / "rules.json"))
    r = client.delete("/v1/alerts/rules/nonexistent-id")
    assert r.status_code == 404
