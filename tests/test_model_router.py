from __future__ import annotations

from unittest.mock import MagicMock

from core import model_router


def test_model_router_loads_policy_from_settings(tmp_path, monkeypatch):
    settings = tmp_path / "settings.yaml"
    settings.write_text(
        """models:
  planning: custom/planning
  balanced: custom/balanced
  fast: custom/fast
  code: custom/code
  long_context: custom/long_context
  cost_optimized: custom/cost
  fallback_chain:
    - custom/balanced
    - custom/code
"""
    )

    monkeypatch.setattr(model_router, "_SETTINGS_PATH", settings)
    monkeypatch.setattr(model_router, "OpenAI", lambda **kwargs: MagicMock())

    router = model_router.ModelRouter()

    assert router.select_model(model_router.RoutingContext(tier=model_router.ModelTier.PLANNING)) == "custom/planning"
    assert router.select_model(model_router.RoutingContext(tier=model_router.ModelTier.BALANCED)) == "custom/balanced"
    assert router.select_model(model_router.RoutingContext(tier=model_router.ModelTier.FAST)) == "custom/fast"
    assert router.select_model(model_router.RoutingContext(tier=model_router.ModelTier.CODE)) == "custom/code"
    assert router.select_model(model_router.RoutingContext(tier=model_router.ModelTier.LONG_CONTEXT)) == "custom/long_context"
    assert router.select_model(model_router.RoutingContext(tier=model_router.ModelTier.COST_OPTIMIZED)) == "custom/cost"

    assert router._fallback_chain[:3] == ["custom/balanced", "custom/code", "custom/cost"]
