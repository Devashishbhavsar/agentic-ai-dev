from __future__ import annotations

from core.context_layer import ContextLayerBuilder
from core.memory.short_term import SessionMemory


def test_context_layer_compacts_history_and_keeps_shared_state():
    session = SessionMemory(session_id="wf-1")
    session.add("user", "Build a dashboard with live traces.")
    session.add("assistant", "I will do that.")
    session.add("agent", "Requirements: live websocket, compact context.", agent="orchestrator")
    session.add("assistant", "Use pinned navigation and alerts.")
    session.add("agent", "Trace panel should be collapsible.", agent="ui")

    session.set_agent_state("orchestrator", "intent", "sw_delivery")
    session.set_agent_state("orchestrator", "pipeline", "sw_delivery")
    session.set_agent_state("orchestrator", "current_stage", "wireframe")
    session.set_agent_state("orchestrator", "shared_bullets", ["websocket stream", "compact context"])

    builder = ContextLayerBuilder(max_messages=3, max_bullets=4)
    pack = builder.build(
        workflow_id="wf-1",
        user_request="Build a dashboard with live traces.",
        session=session,
        agent_name="ui",
        task_label="design dashboard",
    )

    assert pack.workflow_id == "wf-1"
    assert pack.compressed_turns == 3
    assert "websocket stream" in pack.shared_summary
    assert "compact context" in pack.shared_summary
    assert len(pack.messages) == 3
    assert pack.messages[0]["content"] != "Build a dashboard with live traces."
    assert pack.agent_brief.startswith("Agent: ui")
    assert "design dashboard" in pack.agent_brief



def test_base_agent_uses_compact_context_pack(monkeypatch):
    from agents.base import AgentTask, BaseAgent
    from core.memory.short_term import SessionMemory

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

    session = SessionMemory(session_id="wf-2")
    session.set_agent_state("shared", "workflow_id", "wf-2")
    session.set_agent_state("shared", "pipeline", "sw_delivery")
    session.set_agent_state("shared", "current_stage", "design")
    session.set_agent_state("shared", "shared_bullets", ["reuse context", "keep prompts short"])
    session.add("user", "Original request with lots of detail")
    session.add("assistant", "Long response that should be compressed")

    router = DummyRouter()
    agent = DummyAgent(router=router, session=session)
    agent._llm("Make the context compact", task_label="design")

    call = router.calls[0]
    assert "Shared context:" in call["system"]
    assert "reuse context" in call["system"]
    assert len(call["messages"]) == 3
    assert call["messages"][0]["content"].startswith("[user]")
    assert call["messages"][0]["content"] != "Original request with lots of detail"
