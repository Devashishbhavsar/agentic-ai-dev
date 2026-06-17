"""L5 · Model routing layer — selects optimal LLM per call based on cost/latency/capability."""
from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from enum import Enum
from typing import Any

import yaml
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

# OpenRouter model IDs (via OpenAI-compatible API).
# Keep these aligned with config/settings.yaml.
class ModelTier(str, Enum):
    PLANNING = "planning"          # complex reasoning, task decomposition
    BALANCED = "balanced"          # most agent tasks
    FAST = "fast"                  # cheap, high-volume
    CODE = "code"                  # code gen / review
    LONG_CONTEXT = "long_context"  # >100k token contexts
    COST_OPTIMIZED = "cost_optimized"


_MODEL_PRICING = {
    "anthropic/claude-opus-4":     (0.000015, 0.000075),
    "anthropic/claude-sonnet-4-5": (0.000003, 0.000015),
    "anthropic/claude-haiku-4-5":  (0.0000008, 0.000004),
    "openai/gpt-4.1":              (0.00001, 0.00003),
    "google/gemini-2.5-pro":       (0.0000025, 0.00001),
    "deepseek/deepseek-chat":      (0.00000027, 0.0000011),
}

DEFAULT_MODEL_MAP: dict[ModelTier, str] = {
    ModelTier.PLANNING:        "anthropic/claude-opus-4",
    ModelTier.BALANCED:        "anthropic/claude-sonnet-4-5",
    ModelTier.FAST:            "anthropic/claude-haiku-4-5",
    ModelTier.CODE:            "openai/gpt-4.1",
    ModelTier.LONG_CONTEXT:    "google/gemini-2.5-pro",
    ModelTier.COST_OPTIMIZED:  "deepseek/deepseek-chat",
}

DEFAULT_FALLBACK_CHAIN = [
    "anthropic/claude-sonnet-4-5",
    "openai/gpt-4.1",
    "deepseek/deepseek-chat",
]

_SETTINGS_PATH = Path(__file__).resolve().parents[1] / "config" / "settings.yaml"


def _load_model_policy() -> tuple[dict[ModelTier, str], list[str]]:
    model_map = dict(DEFAULT_MODEL_MAP)
    fallback_chain = list(DEFAULT_FALLBACK_CHAIN)

    tier_to_config_key = {
        ModelTier.PLANNING: "planning",
        ModelTier.BALANCED: "balanced",
        ModelTier.FAST: "fast",
        ModelTier.CODE: "code",
        ModelTier.LONG_CONTEXT: "long_context",
        ModelTier.COST_OPTIMIZED: "cost_optimized",
    }

    try:
        raw = yaml.safe_load(_SETTINGS_PATH.read_text()) or {}
        models = raw.get("models", {})
        if isinstance(models, dict):
            for tier, config_key in tier_to_config_key.items():
                value = models.get(config_key)
                if isinstance(value, str) and value.strip():
                    model_map[tier] = value.strip()

            raw_fallback = models.get("fallback_chain")
            if isinstance(raw_fallback, list):
                cleaned = [m.strip() for m in raw_fallback if isinstance(m, str) and m.strip()]
                if cleaned:
                    fallback_chain = cleaned
    except Exception:
        pass

    fallback_chain = list(
        dict.fromkeys(
            [
                model_map[ModelTier.BALANCED],
                *fallback_chain,
                model_map[ModelTier.CODE],
                model_map[ModelTier.COST_OPTIMIZED],
            ]
        )
    )
    return model_map, fallback_chain


@dataclass
class RoutingContext:
    """Hints the router uses to pick a model."""
    tier: ModelTier = ModelTier.BALANCED
    estimated_tokens: int = 4000
    requires_tools: bool = False
    requires_json: bool = False
    task_label: str = ""
    workflow_id: str = ""
    agent_name: str = ""


@dataclass
class ModelCall:
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    agent: str = ""


class ModelRouter:
    """Routes agent LLM calls to the optimal model via OpenRouter."""

    # Limit concurrent API calls to avoid rate limits from OpenRouter
    _api_semaphore = threading.Semaphore(2)

    def __init__(self) -> None:
        self._model_map, self._fallback_chain = _load_model_policy()
        self._client = OpenAI(
            api_key=os.environ.get("OPENROUTER_API_KEY", ""),
            base_url="https://openrouter.ai/api/v1",
            default_headers={
                "HTTP-Referer": "http://localhost:8000",
                "X-Title": "openclaw-enterprise-agent",
            },
        )
        self._call_log: list[ModelCall] = []
        self._log_lock = threading.Lock()

    def select_model(self, ctx: RoutingContext) -> str:
        return self._model_map.get(ctx.tier, self._model_map[ModelTier.BALANCED])

    @retry(stop=stop_after_attempt(4), wait=wait_exponential(min=2, max=30))
    def complete(
        self,
        messages: list[dict],
        system: str,
        ctx: RoutingContext | None = None,
        max_tokens: int = 512,
        **kwargs: Any,
    ) -> str:
        import time
        ctx = ctx or RoutingContext()
        candidates = [self.select_model(ctx), *self._fallback_chain]
        candidates = list(dict.fromkeys(candidates))

        t0 = time.monotonic()
        full_messages = [{"role": "system", "content": system}] + messages
        last_error: Exception | None = None

        for model in candidates:
            try:
                with self._api_semaphore:
                    response = self._client.chat.completions.create(
                        model=model,
                        max_tokens=max_tokens,
                        messages=full_messages,
                    )
                latency = (time.monotonic() - t0) * 1000

                usage = response.usage
                input_tokens = usage.prompt_tokens if usage else 0
                output_tokens = usage.completion_tokens if usage else 0
                inp_cost, out_cost = _MODEL_PRICING.get(model, (0.000003, 0.000015))
                cost_usd = (input_tokens * inp_cost) + (output_tokens * out_cost)
                with self._log_lock:
                    self._call_log.append(ModelCall(
                        model=model,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        cost_usd=cost_usd,
                        latency_ms=latency,
                        agent=ctx.agent_name,
                    ))
                try:
                    from core.runtime import get_runtime_monitor
                    get_runtime_monitor().record_model_call(
                        workflow_id=ctx.workflow_id,
                        agent_name=ctx.agent_name,
                        model=model,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        cost_usd=cost_usd,
                        latency_ms=latency,
                    )
                except Exception:
                    pass

                return response.choices[0].message.content or ""
            except Exception as exc:
                last_error = exc

        if last_error is not None:
            raise last_error
        raise RuntimeError("No OpenRouter model candidates were available")

    def total_cost_estimate(self) -> float:
        """Rough cost estimate."""
        return sum(call.cost_usd for call in self._call_log)

    def call_summary(self) -> dict:
        return {
            "total_calls": len(self._call_log),
            "total_input_tokens": sum(c.input_tokens for c in self._call_log),
            "total_output_tokens": sum(c.output_tokens for c in self._call_log),
            "estimated_cost_usd": self.total_cost_estimate(),
            "calls_by_model": {
                m: sum(1 for c in self._call_log if c.model == m)
                for m in set(c.model for c in self._call_log)
            },
        }
