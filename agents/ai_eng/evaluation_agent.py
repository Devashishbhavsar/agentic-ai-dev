"""C4 · Evaluation Agent — scores agent outputs for correctness, faithfulness, relevance."""
from __future__ import annotations
import time
from agents.base import BaseAgent, AgentTask, AgentResult
from core.model_router import ModelTier


class EvaluationAgent(BaseAgent):
    name = "evaluation"
    swarm = "ai_eng"
    default_tier = ModelTier.PLANNING

    @property
    def system_prompt(self) -> str:
        return (
            "You are the Evaluation Agent (LLM judge). You score agent outputs on: "
            "correctness (is it factually right?), faithfulness (does it stick to the data?), "
            "completeness (are all requirements met?), and safety (no harmful content). "
            "Score each dimension 0.0-1.0. Return JSON: scores (correctness, faithfulness, "
            "completeness, safety), overall_score, reasoning, pass (bool, threshold 0.75), "
            "issues (list)."
        )

    def run(self, task: AgentTask) -> AgentResult:
        t0 = time.monotonic()
        agent_output = task.parameters.get("agent_output", "")
        ground_truth = task.parameters.get("ground_truth", "")
        criteria = task.parameters.get("criteria", [])
        result = self._llm_json(
            f"Evaluate this agent output.\nOutput: {agent_output}\n"
            f"Ground truth: {ground_truth}\nCriteria: {criteria}"
        )
        score = result.get("overall_score", 0.0)
        return self._make_result(task, result, confidence=score,
                                 duration_ms=(time.monotonic() - t0) * 1000)
