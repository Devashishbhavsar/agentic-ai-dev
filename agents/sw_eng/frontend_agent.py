"""D3 · Frontend Agent — generates UI components and pages."""
from __future__ import annotations
import time
from agents.base import BaseAgent, AgentTask, AgentResult
from core.model_router import ModelTier


class FrontendAgent(BaseAgent):
    name = "frontend"
    swarm = "sw_eng"
    default_tier = ModelTier.CODE

    @property
    def system_prompt(self) -> str:
        return (
            "You are the Frontend Agent. You generate React/Next.js UI code: components, "
            "pages, hooks, state management, API client calls, and responsive layouts. "
            "Follow accessibility best practices. "
            "Return JSON: files (list of {path, content}), dependencies, "
            "storybook_stories (if applicable)."
        )

    def run(self, task: AgentTask) -> AgentResult:
        t0 = time.monotonic()
        wireframe = task.parameters.get("wireframe", "")
        api_spec = task.parameters.get("api_spec", {})
        result = self._llm_json(
            f"Generate frontend components.\nWireframe: {wireframe}\nAPI: {api_spec}"
        )
        return self._make_result(task, result, confidence=0.76,
                                 duration_ms=(time.monotonic() - t0) * 1000)
