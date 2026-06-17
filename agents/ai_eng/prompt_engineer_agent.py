"""C1 · Prompt Engineer Agent — designs and optimizes prompts for other agents."""
from __future__ import annotations
import time
from agents.base import BaseAgent, AgentTask, AgentResult
from core.model_router import ModelTier


class PromptEngineerAgent(BaseAgent):
    name = "prompt_engineer"
    swarm = "ai_eng"
    default_tier = ModelTier.PLANNING

    @property
    def system_prompt(self) -> str:
        return (
            "You are the Prompt Engineer Agent. You design, optimize, and version-control "
            "system prompts for specialized agents. You apply techniques: chain-of-thought, "
            "few-shot examples, structured output constraints, persona design, and safety guardrails. "
            "Return JSON: prompt_name, system_prompt (string), few_shot_examples (list), "
            "expected_output_schema, token_estimate, version."
        )

    def run(self, task: AgentTask) -> AgentResult:
        t0 = time.monotonic()
        agent_role = task.parameters.get("agent_role", "")
        task_description = task.parameters.get("task_description", "")
        result = self._llm_json(
            f"Design a system prompt for agent role: '{agent_role}'\nTask: {task_description}"
        )
        return self._make_result(task, result, confidence=0.85,
                                 duration_ms=(time.monotonic() - t0) * 1000)
