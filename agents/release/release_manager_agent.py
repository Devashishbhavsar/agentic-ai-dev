"""G1 · Release Manager Agent — coordinates releases, changelogs, and approval gates."""
from __future__ import annotations
import time
from agents.base import BaseAgent, AgentTask, AgentResult
from core.model_router import ModelTier


class ReleaseManagerAgent(BaseAgent):
    name = "release_manager"
    skill_tasks = ["deployment"]
    swarm = "release"
    default_tier = ModelTier.PLANNING

    @property
    def system_prompt(self) -> str:
        return (
            "You are the Release Manager Agent. You coordinate software releases: "
            "generate changelogs from git history, define release notes, "
            "check go/no-go criteria (all tests pass, security cleared, QA signed off), "
            "and request human approval for production deployments. "
            "Return JSON: release_version, changelog (string), go_no_go (bool), "
            "blocking_issues (list), approval_required (bool), release_notes."
        )

    def run(self, task: AgentTask) -> AgentResult:
        t0 = time.monotonic()
        git_log = task.parameters.get("git_log", "")
        qa_results = task.parameters.get("qa_results", {})
        result = self._llm_json(
            f"Prepare release.\nGit log: {git_log}\nQA: {qa_results}"
        )
        return self._make_result(task, result, confidence=0.9,
                                 duration_ms=(time.monotonic() - t0) * 1000)
