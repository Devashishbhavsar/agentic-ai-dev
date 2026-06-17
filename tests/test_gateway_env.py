from __future__ import annotations

import importlib

import dotenv

from core import model_router


def test_gateway_loads_dotenv_before_router_init(monkeypatch):
    captured: dict[str, object] = {}

    def fake_load_dotenv(path, override=False):
        captured["path"] = str(path)
        captured["override"] = override
        monkeypatch.setenv("OPENROUTER_API_KEY", "dotenv-test-key")
        return True

    class DummyRouter:
        def __init__(self):
            captured["api_key_at_init"] = __import__("os").environ.get("OPENROUTER_API_KEY")

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(dotenv, "load_dotenv", fake_load_dotenv)
    monkeypatch.setattr(model_router, "ModelRouter", DummyRouter)

    gateway = importlib.import_module("api.gateway")
    importlib.reload(gateway)

    assert captured["api_key_at_init"] == "dotenv-test-key"
    assert captured["path"].endswith("/.env")
    assert captured["override"] is False

    monkeypatch.undo()
    importlib.reload(gateway)
