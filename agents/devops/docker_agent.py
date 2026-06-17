"""E2 · Docker Agent — generates optimized Dockerfiles and compose configs."""
from __future__ import annotations
import time
from agents.base import BaseAgent, AgentTask, AgentResult
from core.model_router import ModelTier


class DockerAgent(BaseAgent):
    name = "docker"
    swarm = "devops"
    default_tier = ModelTier.CODE

    @property
    def system_prompt(self) -> str:
        return (
            "You are the Docker Agent. You write multi-stage Dockerfiles optimized for "
            "minimal image size, build caching, security (non-root user, read-only fs), "
            "and docker-compose configs for local development. "
            "Return JSON: dockerfile (string), compose_yaml (string), "
            "image_size_estimate_mb, build_time_estimate_seconds, security_notes."
        )

    def run(self, task: AgentTask) -> AgentResult:
        t0 = time.monotonic()
        app_spec = task.parameters.get("app_spec", {})
        result = self._llm_json(f"Generate Dockerfile and compose for: {app_spec}")
        return self._make_result(task, result, confidence=0.88,
                                 duration_ms=(time.monotonic() - t0) * 1000)
