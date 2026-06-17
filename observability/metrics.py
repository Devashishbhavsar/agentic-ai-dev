"""L12 · Prometheus metrics — agent performance, token costs, pipeline latency."""
from __future__ import annotations

from prometheus_client import Counter, Histogram, Gauge, start_http_server


agent_calls_total = Counter(
    "agent_calls_total",
    "Total LLM calls per agent",
    ["agent_name", "swarm", "model"],
)

agent_latency_seconds = Histogram(
    "agent_latency_seconds",
    "Agent task duration in seconds",
    ["agent_name", "swarm"],
    buckets=[0.1, 0.5, 1, 2, 5, 10, 30, 60],
)

agent_confidence = Gauge(
    "agent_confidence_score",
    "Last confidence score per agent",
    ["agent_name"],
)

llm_tokens_total = Counter(
    "llm_tokens_total",
    "Total LLM tokens consumed",
    ["model", "direction"],  # direction: input | output
)

llm_cost_usd_total = Counter(
    "llm_cost_usd_total",
    "Estimated LLM cost in USD",
    ["model"],
)

pipeline_runs_total = Counter(
    "pipeline_runs_total",
    "Total pipeline executions",
    ["pipeline", "status"],
)

pipeline_duration_seconds = Histogram(
    "pipeline_duration_seconds",
    "End-to-end pipeline duration",
    ["pipeline"],
    buckets=[1, 5, 10, 30, 60, 120, 300, 600],
)

approval_gates_total = Counter(
    "approval_gates_total",
    "Human approval gate triggers",
    ["pipeline", "risk_level"],
)


def start_metrics_server(port: int = 9090) -> None:
    start_http_server(port)
