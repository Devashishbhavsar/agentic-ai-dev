from __future__ import annotations

from agents.base import AgentTask, BaseAgent
from core.memory.short_term import SessionMemory


def test_base_agent_injects_retrieved_context(monkeypatch, tmp_path):
    monkeypatch.setenv("RAG_STORE_PATH", str(tmp_path / "rag.sqlite"))

    class DummyRouter:
        def __init__(self):
            self.calls = []

        def complete(self, messages, system, ctx=None, max_tokens=512, **kwargs):
            self.calls.append({"messages": messages, "system": system, "ctx": ctx})
            return "{}"

    class DummyAgent(BaseAgent):
        name = "dummy"
        swarm = "test"

        @property
        def system_prompt(self) -> str:
            return "Dummy system prompt"

        def run(self, task: AgentTask):
            return self._make_result(task, {"ok": True})

    session = SessionMemory(session_id="wf-3")
    session.set_agent_state("shared", "workflow_id", "wf-3")
    session.set_agent_state("shared", "pipeline", "sw_delivery")
    session.set_agent_state("shared", "current_stage", "design")
    session.set_agent_state("shared", "shared_bullets", ["keep prompts short"])
    session.add("user", "We need a production-grade RAG layer.")

    router = DummyRouter()
    agent = DummyAgent(router=router, session=session)
    agent._llm("Plan the RAG architecture", task_label="design")

    call = router.calls[0]
    assert "Retrieved context:" in call["system"]
    assert "compact" in call["system"].lower() or "short" in call["system"].lower()
