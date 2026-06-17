"""Tests for /v1/system/* endpoints."""
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
    for field in ("name", "active", "pid", "uptime_seconds", "restarts"):
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
    assert "last_activity" in data  # can be None


def test_openrouter_check_returns_valid_key():
    r = client.get("/v1/system/openrouter-check")
    assert r.status_code == 200
    data = r.json()
    assert "valid" in data
    assert isinstance(data["valid"], bool)


def test_restart_rejects_unknown_service():
    r = client.post("/v1/system/restart", json={"service": "not-a-real-service"})
    assert r.status_code == 400
