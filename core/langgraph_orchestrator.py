"""LangGraph workflow wrapper for orchestration."""
from __future__ import annotations

from typing import Any, TypedDict

try:
    from langgraph.graph import END, START, StateGraph
except Exception as exc:  # pragma: no cover - dependency guard
    StateGraph = None  # type: ignore[assignment]
    START = END = None  # type: ignore[assignment]
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


class WorkflowState(TypedDict, total=False):
    request: Any
    intent: dict[str, Any]
    result: Any
    pipeline_used: str


def build_workflow_graph(orchestrator: Any):
    if StateGraph is None:
        raise RuntimeError(f"LangGraph is unavailable: {_IMPORT_ERROR}")

    graph = StateGraph(WorkflowState)

    def classify(state: WorkflowState) -> WorkflowState:
        request = state["request"]
        intent = orchestrator._classify_intent(request.user_input, request.workflow_id)
        pipeline_used = intent.get("pipeline", "none")
        return {"intent": intent, "pipeline_used": pipeline_used}

    def route(state: WorkflowState) -> WorkflowState:
        request = state["request"]
        intent = state["intent"]
        pipeline_used = state.get("pipeline_used", intent.get("pipeline", "none"))
        if pipeline_used == "bi":
            result = orchestrator._run_bi_pipeline(request, intent)
        elif pipeline_used == "sw_delivery":
            result = orchestrator._run_sw_delivery_pipeline(request, intent)
        else:
            result = orchestrator._run_general(request, intent)
        return {"result": result, "pipeline_used": pipeline_used}

    graph.add_node("classify", classify)
    graph.add_node("route", route)
    graph.add_edge(START, "classify")
    graph.add_edge("classify", "route")
    graph.add_edge("route", END)
    return graph.compile()


def run_workflow(orchestrator: Any, request: Any) -> WorkflowState:
    graph = build_workflow_graph(orchestrator)
    return graph.invoke({"request": request})
