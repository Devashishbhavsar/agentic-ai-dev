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
