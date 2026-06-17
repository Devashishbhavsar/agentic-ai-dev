"""L2 · OpenClaw master orchestrator — decomposes requests, routes swarms, assembles answers."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from core.model_router import ModelRouter, ModelTier, RoutingContext
from core.runtime import get_runtime_monitor
from core.retrieval import get_retrieval_service
from core.langgraph_orchestrator import run_workflow
from core.swarm import SwarmEngine, SwarmResult
from core.memory.short_term import SessionMemory
from core.memory.semantic_cache import SemanticCache


@dataclass
class WorkflowRequest:
    user_input: str
    user_id: str = "anonymous"
    channel: str = "api"            # web | slack | teams | api
    workflow_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    context: dict = field(default_factory=dict)


@dataclass
class WorkflowResponse:
    workflow_id: str
    status: str
    result: Any
    pipeline_used: str = ""
    approval_required: bool = False
    approval_gate: str | None = None
    total_agents_run: int = 0
    estimated_cost_usd: float = 0.0


class OpenClawOrchestrator:
    """
    L2 · Master orchestrator.
    Receives every request, classifies intent, decomposes into sub-goals,
    routes to the right pipeline or swarm, enforces approval gates,
    and assembles the final response.
    """

    INTENT_PROMPT = (
        "You are an enterprise orchestrator. Classify the user request into exactly one category.\n\n"
        "Rules:\n"
        "- Use 'bi_report' + pipeline 'bi' for: KPIs, dashboards, reports, metrics, analytics, revenue, churn, "
        "  data analysis, business intelligence, executive summaries, data visualization.\n"
        "- Use 'sw_delivery' + pipeline 'sw_delivery' for: build/create/develop/generate code or APIs, "
        "  software architecture, REST/GraphQL APIs, microservices, Docker, Kubernetes, CI/CD, deployments, "
        "  authentication systems, JWT, OAuth, databases schemas, backend services, any programming task.\n"
        "- Use 'data_query' + pipeline 'none' for: SQL queries, direct database lookups.\n"
        "- Use 'general' + pipeline 'none' only for greetings or completely unclassifiable requests.\n\n"
        "Return JSON only (no markdown):\n"
        "{\n"
        "  \"intent\": \"bi_report\" | \"sw_delivery\" | \"data_query\" | \"general\",\n"
        "  \"pipeline\": \"bi\" | \"sw_delivery\" | \"none\",\n"
        "  \"requires_approval\": bool,\n"
        "  \"risk_level\": \"low\" | \"medium\" | \"high\",\n"
        "  \"domain\": string,\n"
        "  \"sub_goals\": [list of strings],\n"
        "  \"swarms_needed\": [from: bi, data_eng, ai_eng, sw_eng, devops, qa, release]\n"
        "}"
    )

    def __init__(
        self,
        router: ModelRouter | None = None,
        swarm_engine: SwarmEngine | None = None,
        session: SessionMemory | None = None,
        cache: SemanticCache | None = None,
    ) -> None:
        self._router = router or ModelRouter()
        self._swarm = swarm_engine or SwarmEngine(router=self._router)
        self._session = session or SessionMemory(session_id=str(uuid.uuid4()))
        self._cache = cache or SemanticCache()
        self._retrieval = get_retrieval_service()

    def process(self, request: WorkflowRequest) -> WorkflowResponse:
        """Main entry point — classify intent, plan, execute, return."""
        monitor = get_runtime_monitor()
        monitor.start_workflow(
            workflow_id=request.workflow_id,
            request=request.user_input,
            user_id=request.user_id,
            channel=request.channel,
        )
        self._session.set_agent_state("shared", "workflow_id", request.workflow_id)
        self._session.set_agent_state("shared", "request", request.user_input)
        self._session.set_agent_state("shared", "user_id", request.user_id)
        self._session.set_agent_state("shared", "channel", request.channel)
        self._session.set_agent_state("orchestrator", "workflow_id", request.workflow_id)
        self._session.set_agent_state("orchestrator", "request", request.user_input)

        cached = self._cache.get(request.user_input)
        if cached:
            import json as _json
            try:
                cached_dict = _json.loads(cached)
            except Exception:
                cached_dict = {"response": cached}
            monitor.finish_workflow(
                request.workflow_id,
                status="success",
                summary="Cache hit",
                approval_required=False,
            )
            return WorkflowResponse(
                workflow_id=request.workflow_id,
                status="success",
                result=cached_dict,
                pipeline_used="cache",
            )

        try:
            graph_state = run_workflow(self, request)
            intent = graph_state.get("intent", {"intent": "general", "pipeline": "none", "risk_level": "low", "sub_goals": []})
            pipeline = graph_state.get("pipeline_used", intent.get("pipeline", "none"))
            result = graph_state.get("result", {})
            self._session.set_agent_state("shared", "intent", intent.get("intent", "general"))
            self._session.set_agent_state("shared", "pipeline", pipeline)
            self._session.set_agent_state("shared", "current_stage", f"pipeline:{pipeline}")
            self._session.set_agent_state("shared", "risk_level", intent.get("risk_level", "low"))
            self._session.set_agent_state("shared", "approval_required", bool(intent.get("requires_approval") and intent.get("risk_level") == "high"))
            self._session.set_agent_state("shared", "shared_bullets", intent.get("sub_goals", []))
            monitor.update_workflow(
                request.workflow_id,
                intent=intent.get("intent", "general"),
                pipeline=pipeline,
                stage=f"pipeline:{pipeline}",
                risk_level=intent.get("risk_level", "low"),
                sub_goals=intent.get("sub_goals", []),
                approval_required=bool(intent.get("requires_approval") and intent.get("risk_level") == "high"),
            )
            if intent.get("requires_approval") and intent.get("risk_level") == "high":
                monitor.finish_workflow(
                    request.workflow_id,
                    status="pending_approval",
                    summary="Human review required",
                    approval_required=True,
                )
                return WorkflowResponse(
                    workflow_id=request.workflow_id,
                    status="pending_approval",
                    result={"intent": intent, "sub_goals": intent.get("sub_goals", [])},
                    approval_required=True,
                    approval_gate="human_review",
                )

            import json as _json
            self._retrieval.ingest_workflow_summary(
                workflow_id=request.workflow_id,
                request=request.user_input,
                summary=str(result)[:1000],
                pipeline=pipeline,
                intent=intent.get("intent", "general"),
                stage="completed",
                risk_level=intent.get("risk_level", "low"),
            )
            self._cache.set(request.user_input, _json.dumps(result, default=str))
            monitor.finish_workflow(
                request.workflow_id,
                status="success",
                summary=str(result)[:200],
                approval_required=bool(result.get("approval_required", False)),
            )
            return WorkflowResponse(
                workflow_id=request.workflow_id,
                status="success",
                result=result,
                pipeline_used=pipeline,
                estimated_cost_usd=self._router.total_cost_estimate(),
            )
        except Exception as exc:
            monitor.finish_workflow(
                request.workflow_id,
                status="failure",
                summary=str(exc)[:200],
                approval_required=False,
            )
            raise

    def _classify_intent(self, user_input: str, workflow_id: str = "") -> dict:
        import json, re
        ctx = RoutingContext(tier=ModelTier.PLANNING, agent_name="orchestrator", workflow_id=workflow_id)
        raw = self._router.complete(
            messages=[{"role": "user", "content": user_input}],
            system=self.INTENT_PROMPT,
            ctx=ctx,
        )
        raw = raw.strip()
        # strip markdown fences
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        try:
            return json.loads(raw.strip())
        except json.JSONDecodeError:
            # best-effort: extract first {...} block
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                return json.loads(m.group(0))
            return {"intent": "general", "pipeline": "none", "risk_level": "low", "sub_goals": []}

    def _run_bi_pipeline(self, request: WorkflowRequest, intent: dict) -> dict:
        from pipelines.bi_pipeline import BIPipeline
        pipeline = BIPipeline(router=self._router, session=self._session)
        return pipeline.run(request.user_input, intent)

    def _run_sw_delivery_pipeline(self, request: WorkflowRequest, intent: dict) -> dict:
        from pipelines.sw_delivery_pipeline import SWDeliveryPipeline
        pipeline = SWDeliveryPipeline(router=self._router, session=self._session)
        return pipeline.run(request.user_input, intent)

    def _run_general(self, request: WorkflowRequest, intent: dict) -> dict:
        self._session.set_agent_state("orchestrator", "current_stage", "general")
        ctx = RoutingContext(tier=ModelTier.BALANCED, agent_name="orchestrator", workflow_id=request.workflow_id)
        response = self._router.complete(
            messages=[{"role": "user", "content": request.user_input}],
            system="You are a helpful enterprise AI assistant.",
            ctx=ctx,
        )
        return {"response": response, "intent": intent}
