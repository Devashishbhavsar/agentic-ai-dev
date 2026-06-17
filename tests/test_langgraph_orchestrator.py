from __future__ import annotations

from core.langgraph_orchestrator import run_workflow
from core.orchestrator import WorkflowRequest


def test_langgraph_workflow_routes_to_sw_delivery():
    calls = []

    class DummyOrchestrator:
        def _classify_intent(self, user_input: str, workflow_id: str = "") -> dict:
            calls.append(("classify", user_input, workflow_id))
            return {"intent": "sw_delivery", "pipeline": "sw_delivery", "sub_goals": ["ship"], "risk_level": "low"}

        def _run_sw_delivery_pipeline(self, request, intent):
            calls.append(("sw_delivery", request.user_input, intent["intent"]))
            return {"status": "ok", "mode": "sw_delivery"}

        def _run_bi_pipeline(self, request, intent):
            raise AssertionError("BI path should not be used")

        def _run_general(self, request, intent):
            raise AssertionError("general path should not be used")

    request = WorkflowRequest(user_input="build me an api", workflow_id="wf-graph")
    state = run_workflow(DummyOrchestrator(), request)

    assert state["pipeline_used"] == "sw_delivery"
    assert state["result"]["mode"] == "sw_delivery"
    assert calls[0] == ("classify", "build me an api", "wf-graph")
    assert calls[1] == ("sw_delivery", "build me an api", "sw_delivery")
