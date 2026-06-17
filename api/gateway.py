"""L1 · API Gateway — REST entry point for all user requests."""
from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core.orchestrator import OpenClawOrchestrator, WorkflowRequest
from core.model_router import ModelRouter
from core.memory.short_term import SessionMemory
from core.memory.semantic_cache import SemanticCache
from core.runtime import get_runtime_monitor


app = FastAPI(
    title="OpenClaw Enterprise Agent",
    description="Enterprise multi-agent BI → deployment platform",
    version="0.1.0",
)

BASE_DIR = Path(__file__).resolve().parents[1]
DASHBOARD_DIR = BASE_DIR / "web" / "dashboard"
DASHBOARD_INDEX = DASHBOARD_DIR / "index.html"

# Load project-level runtime secrets before constructing shared clients.
load_dotenv(BASE_DIR / ".env")

if DASHBOARD_DIR.exists():
    app.mount("/dashboard-assets", StaticFiles(directory=str(DASHBOARD_DIR)), name="dashboard-assets")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Shared instances
_router = ModelRouter()
_cache = SemanticCache()
_demo_tasks: set[asyncio.Task[str]] = set()


def get_orchestrator() -> OpenClawOrchestrator:
    session = SessionMemory(session_id=str(uuid.uuid4()))
    return OpenClawOrchestrator(router=_router, session=session, cache=_cache)


DEMO_AGENT_SEED = [
    {
        "agent_name": "planner",
        "swarm": "coordination",
        "stage": "01_planning",
        "task": "Break the request into parallel lanes",
        "model": "openrouter/anthropic/claude-sonnet-4",
        "kind": "analysis",
        "tool": "planner_brief",
        "input": "Frame the demo into planning, execution, and review lanes.",
        "output": "Parallel lanes identified: planning, execution, review.",
        "input_tokens": 220,
        "output_tokens": 90,
        "cost_usd": 0.0018,
        "latency_ms": 180.0,
        "delay": 0.18,
    },
    {
        "agent_name": "builder",
        "swarm": "delivery",
        "stage": "02_execution",
        "task": "Simulate the implementation lane",
        "model": "openrouter/openai/gpt-4.1",
        "kind": "tool",
        "tool": "code_patch",
        "input": "Apply the mission control changes and stream progress.",
        "output": "Dashboard state updated with live workflow activity.",
        "input_tokens": 360,
        "output_tokens": 150,
        "cost_usd": 0.0044,
        "latency_ms": 240.0,
        "delay": 0.24,
    },
    {
        "agent_name": "auditor",
        "swarm": "quality",
        "stage": "03_review",
        "task": "Check the dashboard and orchestration flow",
        "model": "openrouter/anthropic/claude-3.5-sonnet",
        "kind": "review",
        "tool": "review_pass",
        "input": "Inspect the generated demo and confirm the command center is populated.",
        "output": "Demo workflow is visible and the mission board has live cards.",
        "input_tokens": 200,
        "output_tokens": 110,
        "cost_usd": 0.0019,
        "latency_ms": 205.0,
        "delay": 0.2,
    },
]


async def run_demo_workflow(
    monitor=None,
    *,
    workflow_id: str | None = None,
    sleep_fn=asyncio.sleep,
) -> str:
    runtime = monitor or get_runtime_monitor()
    workflow_id = workflow_id or f"demo-{uuid.uuid4().hex[:10]}"
    runtime.start_workflow(
        workflow_id=workflow_id,
        request="Launch the OpenClaw mission control demo",
        user_id="system",
        channel="dashboard",
    )
    runtime.update_workflow(
        workflow_id,
        pipeline="mission_control_demo",
        stage="pipeline:demo:planning",
        status="running",
        intent="dashboard_demo",
        risk_level="low",
        approval_required=False,
        current_agent="planner",
        sub_goals=[
            "Show parallel agents",
            "Seed live dashboard activity",
            "Keep the context compact",
        ],
    )
    await sleep_fn(0.12)

    async def run_lane(spec: dict) -> None:
        runtime.update_workflow(
            workflow_id,
            stage=f"pipeline:demo:{spec['stage']}",
            current_agent=spec['agent_name'],
        )
        with runtime.track_agent(
            workflow_id=workflow_id,
            agent_name=spec['agent_name'],
            swarm=spec['swarm'],
            stage=spec['stage'],
            task=spec['task'],
            model=spec['model'],
        ):
            runtime.record_agent_trace(
                workflow_id=workflow_id,
                agent_name=spec['agent_name'],
                kind=spec['kind'],
                tool=spec['tool'],
                stage=spec['stage'],
                task=spec['task'],
                model=spec['model'],
                input=spec['input'],
                output="working",
            )
            await sleep_fn(spec['delay'])
            runtime.record_agent_trace(
                workflow_id=workflow_id,
                agent_name=spec['agent_name'],
                kind="tool_result",
                tool=spec['tool'],
                stage=spec['stage'],
                task=spec['task'],
                model=spec['model'],
                input=spec['input'],
                output=spec['output'],
            )
            runtime.record_model_call(
                workflow_id=workflow_id,
                agent_name=spec['agent_name'],
                model=spec['model'],
                input_tokens=spec['input_tokens'],
                output_tokens=spec['output_tokens'],
                cost_usd=spec['cost_usd'],
                latency_ms=spec['latency_ms'],
            )

    await asyncio.gather(*(run_lane(spec) for spec in DEMO_AGENT_SEED))
    runtime.update_workflow(
        workflow_id,
        stage="pipeline:demo:wrapup",
        current_agent="coordinator",
    )
    with runtime.track_agent(
        workflow_id=workflow_id,
        agent_name="coordinator",
        swarm="coordination",
        stage="04_wrapup",
        task="synthesize the demo state",
        model="openrouter/anthropic/claude-sonnet-4",
    ):
        runtime.record_agent_trace(
            workflow_id=workflow_id,
            agent_name="coordinator",
            kind="summary",
            tool="dashboard_snapshot",
            stage="04_wrapup",
            task="synthesize the demo state",
            model="openrouter/anthropic/claude-sonnet-4",
            input="Collect the completed lane results.",
            output="Mission board is populated and the live stream is active.",
        )
        runtime.record_model_call(
            workflow_id=workflow_id,
            agent_name="coordinator",
            model="openrouter/anthropic/claude-sonnet-4",
            input_tokens=180,
            output_tokens=96,
            cost_usd=0.0012,
            latency_ms=165.0,
        )
        await sleep_fn(0.08)
    runtime.finish_workflow(
        workflow_id,
        status="success",
        summary="Demo workflow completed with parallel planning, execution, and review lanes.",
        approval_required=False,
    )
    return workflow_id


async def _launch_demo_background() -> dict[str, str]:
    workflow_id = f"demo-{uuid.uuid4().hex[:10]}"
    task = asyncio.create_task(run_demo_workflow(workflow_id=workflow_id))
    _demo_tasks.add(task)
    task.add_done_callback(_demo_tasks.discard)
    return {"workflow_id": workflow_id, "status": "started"}




class RequestBody(BaseModel):
    message: str
    user_id: str = "anonymous"
    channel: str = "api"
    context: dict = {}


class WorkflowResponse(BaseModel):
    workflow_id: str
    status: str
    result: dict
    pipeline_used: str = ""
    approval_required: bool = False
    estimated_cost_usd: float = 0.0


@app.post("/v1/chat", response_model=WorkflowResponse)
async def chat(body: RequestBody, orchestrator: OpenClawOrchestrator = Depends(get_orchestrator)):
    """Main entry point — send any natural language request."""
    try:
        request = WorkflowRequest(
            user_input=body.message,
            user_id=body.user_id,
            channel=body.channel,
            context=body.context,
        )
        resp = orchestrator.process(request)
        return WorkflowResponse(
            workflow_id=resp.workflow_id,
            status=resp.status,
            result=resp.result if isinstance(resp.result, dict) else {"response": str(resp.result)},
            pipeline_used=resp.pipeline_used,
            approval_required=resp.approval_required,
            estimated_cost_usd=resp.estimated_cost_usd,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/v1/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


@app.on_event("startup")
async def bootstrap_demo_workflow() -> None:
    if os.environ.get("OPENCLAW_AUTO_DEMO", "1") == "0":
        return
    monitor = get_runtime_monitor()
    snapshot = monitor.snapshot()
    summary = snapshot.get("summary", {})
    if summary.get("active_workflows") or summary.get("recent_runs") or summary.get("recent_events") or summary.get("recent_traces"):
        return
    await run_demo_workflow(monitor)


@app.post("/v1/demo/workflow")
async def demo_workflow():
    result = await _launch_demo_background()
    return JSONResponse(result)




@app.get("/v1/stats")
async def stats():
    return {
        "cache_hit_rate": _cache.hit_rate,
        "cache_hits": _cache.hits,
        "cache_misses": _cache.misses,
        "model_stats": _router.call_summary(),
    }


@app.get("/dashboard")
async def dashboard():
    if DASHBOARD_INDEX.exists():
        return FileResponse(DASHBOARD_INDEX, media_type="text/html")
    raise HTTPException(status_code=404, detail="Dashboard assets are missing")


@app.get("/v1/dashboard")
async def dashboard_data():
    runtime = get_runtime_monitor().snapshot()
    stats = _router.call_summary()
    cache_hit_rate = _cache.hit_rate
    summary = dict(runtime.get("summary", {}))
    summary.update({
        "cache_hit_rate": cache_hit_rate,
        "cache_hits": _cache.hits,
        "cache_misses": _cache.misses,
        "estimated_cost_usd": stats.get("estimated_cost_usd", 0),
        "total_input_tokens": stats.get("total_input_tokens", 0),
        "total_output_tokens": stats.get("total_output_tokens", 0),
    })

    return {
        "generated_at": runtime.get("generated_at"),
        "revision": runtime.get("revision", 0),
        "summary": summary,
        "active_workflows": runtime.get("active_workflows", []),
        "active_agents": runtime.get("active_agents", []),
        "recent_runs": runtime.get("recent_runs", []),
        "recent_events": runtime.get("recent_events", []),
        "recent_traces": runtime.get("recent_traces", []),
        "pipeline_counts": runtime.get("pipeline_counts", {}),
        "status_counts": runtime.get("status_counts", {}),
        "model_usage": runtime.get("model_usage", {}),
        "trend_points": runtime.get("trend_points", []),
        "task_board": runtime.get("task_board", {"columns": [], "total_cards": 0}),
        "workflow_connections": runtime.get("workflow_connections", []),
        "model_stats": stats,
    }


@app.websocket("/v1/dashboard/stream")
async def dashboard_stream(websocket: WebSocket):
    await websocket.accept()
    monitor = get_runtime_monitor()
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=64)

    def push(message: dict) -> None:
        def enqueue() -> None:
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            queue.put_nowait(message)

        loop.call_soon_threadsafe(enqueue)

    listener_id = monitor.register_listener(push)
    push({"type": "snapshot", "snapshot": monitor.snapshot()})

    try:
        while True:
            message = await queue.get()
            await websocket.send_json(message)
    except WebSocketDisconnect:
        pass
    finally:
        monitor.unregister_listener(listener_id)


@app.get("/v1/data/catalog")
async def data_catalog():
    from data.unified_layer import UnifiedDataLayer
    layer = UnifiedDataLayer()
    return layer.catalog()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.gateway:app",
        host=os.environ.get("API_HOST", "0.0.0.0"),
        port=int(os.environ.get("API_PORT", 8000)),
        reload=True,
    )
