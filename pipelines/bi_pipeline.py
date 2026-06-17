"""L9 · BI Pipeline — 10 steps from business request to executive report, with parallel swarm execution."""
from __future__ import annotations

import concurrent.futures
import uuid
from dataclasses import dataclass, field

from agents.base import AgentTask
from agents.bi.requirements_agent import RequirementsAgent
from agents.bi.business_analyst_agent import BusinessAnalystAgent
from agents.bi.kpi_discovery_agent import KPIDiscoveryAgent
from agents.bi.data_mapping_agent import DataMappingAgent
from agents.bi.stakeholder_agent import StakeholderAgent
from agents.data_eng.source_discovery_agent import SourceDiscoveryAgent
from agents.data_eng.etl_agent import ETLAgent
from agents.data_eng.data_quality_agent import DataQualityAgent
from agents.qa.verification_agent import VerificationAgent
from core.model_router import ModelRouter, ModelTier, RoutingContext
from core.runtime import get_runtime_monitor
from core.retrieval import get_retrieval_service
from core.memory.short_term import SessionMemory
from data.connectors.duckdb_connector import DuckDBConnector


@dataclass
class BIPipelineResult:
    workflow_id: str
    step_results: dict = field(default_factory=dict)
    kpis: list = field(default_factory=list)
    dashboard_config: dict = field(default_factory=dict)
    exec_summary: str = ""
    approval_required: bool = False
    status: str = "success"


class BIPipeline:
    """
    10-step BI pipeline with parallel swarm execution:

    Phase 1 (sequential): Requirements parsing
    Phase 2 (parallel):   Business analysis  ║  Data source discovery
    Phase 3 (parallel):   KPI modeling       ║  ETL planning
    Phase 4 (parallel):   Data mapping       ║  Stakeholder alignment
    Phase 5 (parallel):   Data quality       ║  Dashboard gen  ║  Exec summary
    Phase 6 (sequential): Approval gate → Release
    """

    def __init__(self, router: ModelRouter, session: SessionMemory | None = None) -> None:
        self._router = router
        self._session = session
        self._wf_id = str(uuid.uuid4())
        self._retrieval = get_retrieval_service()

        self._requirements = RequirementsAgent(router, session)
        self._analyst = BusinessAnalystAgent(router, session)
        self._kpi = KPIDiscoveryAgent(router, session)
        self._data_mapping = DataMappingAgent(router, session)
        self._stakeholder = StakeholderAgent(router, session)
        self._src_discovery = SourceDiscoveryAgent(router, session)
        self._etl = ETLAgent(router, session)
        self._quality = DataQualityAgent(router, session)
        self._verifier = VerificationAgent(router, session)
        self._duckdb = DuckDBConnector()

    def _task(self, operation: str, params: dict) -> AgentTask:
        return AgentTask(
            task_id=str(uuid.uuid4()),
            workflow_id=self._wf_id,
            operation=operation,
            parameters=params,
        )

    def _run_agent(self, agent, task: AgentTask, stage: str):
        monitor = get_runtime_monitor()
        with monitor.track_agent(
            workflow_id=self._wf_id,
            agent_name=agent.name,
            swarm=agent.swarm,
            stage=stage,
            task=task.operation,
        ):
            return agent.run(task)

    def run(self, user_request: str, intent: dict) -> dict:
        result = BIPipelineResult(workflow_id=self._wf_id)
        monitor = get_runtime_monitor()
        if self._session:
            self._session.set_agent_state("shared", "workflow_id", self._wf_id)
            self._session.set_agent_state("shared", "pipeline", "bi")
            self._session.set_agent_state("shared", "current_stage", "01_requirements")
            self._session.set_agent_state("shared", "shared_bullets", ["keep prompts compact", "reuse executive summary across agents"])
        monitor.update_workflow(self._wf_id, pipeline="bi", stage="01_requirements", status="running")

        # ── Phase 1: Requirements (sequential — everything depends on this) ──
        req_result = self._run_agent(self._requirements, self._task("parse", {"request": user_request}), "01_requirements")
        result.step_results["01_requirements"] = req_result.results

        # ── Phase 2: Business analysis + Source discovery (parallel) ──
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            analyst_future = pool.submit(
                self._run_agent,
                self._analyst,
                self._task("analyze", {"requirements": req_result.results}),
                "02_analysis",
            )
            src_future = pool.submit(
                self._run_agent,
                self._src_discovery,
                self._task("discover", {
                    "query": user_request,
                    "available_sources": ["postgres", "snowflake", "bigquery", "csv"],
                }),
                "03_data_discovery",
            )
            analyst_result = analyst_future.result()
            src_result = src_future.result()

        result.step_results["02_analysis"] = analyst_result.results
        result.step_results["03_data_discovery"] = src_result.results

        # ── Phase 3: KPI modeling + ETL planning (parallel) ──
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            kpi_future = pool.submit(
                self._run_agent,
                self._kpi,
                self._task("discover_kpis", {
                    "domain": intent.get("domain", "business"),
                    "analysis_plan": analyst_result.results.get("analysis_plan", {}),
                }),
                "04_kpi_modeling",
            )
            etl_future = pool.submit(
                self._run_agent,
                self._etl,
                self._task("plan", {
                    "sources": src_result.results.get("sources", []),
                    "target": "analytical_layer",
                }),
                "04_etl_plan",
            )
            kpi_result = kpi_future.result()
            etl_result = etl_future.result()

        result.step_results["04_kpi_modeling"] = kpi_result.results
        result.kpis = kpi_result.results.get("kpis", [])
        result.step_results["04_etl_plan"] = etl_result.results

        # ── Skill: verification-before-completion — check KPIs before proceeding ──
        kpi_verify = self._verifier.run(self._task("verify", {
            "pipeline_type": "bi",
            "phase_name": "kpi_modeling",
            "phase_output": {"kpis": result.kpis},
        }))
        result.step_results["04_kpi_verification"] = kpi_verify.results

        # ── Skill: duckdb-query — execute KPI formulas on any loaded CSV/data ──
        kpi_actuals = []
        for kpi in result.kpis[:3]:  # run top 3 KPIs through DuckDB
            formula = kpi.get("formula", "")
            if formula and ("SELECT" in formula.upper() or "SUM(" in formula.upper()):
                kpi_actuals.append(self._duckdb.run_kpi_sql(kpi["name"], formula))
        if kpi_actuals:
            result.step_results["04_kpi_actuals"] = kpi_actuals

        # ── Phase 4: Data mapping + Stakeholder alignment (parallel) ──
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            mapping_future = pool.submit(
                self._run_agent,
                self._data_mapping,
                self._task("map", {
                    "kpis": result.kpis,
                    "schema_catalog": src_result.results.get("sources", []),
                }),
                "04_data_mapping",
            )
            stakeholder_future = pool.submit(
                self._run_agent,
                self._stakeholder,
                self._task("align", {
                    "audience": req_result.results.get("audience", "executives"),
                    "kpis": result.kpis,
                }),
                "07_stakeholder",
            )
            mapping_result = mapping_future.result()
            stakeholder_result = stakeholder_future.result()

        result.step_results["04_data_mapping"] = mapping_result.results
        result.step_results["07_stakeholder"] = stakeholder_result.results

        # ── Phase 5: Quality check + Dashboard + Exec summary (parallel) ──
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            quality_future = pool.submit(
                self._run_agent,
                self._quality,
                self._task("validate", {
                    "data_profile": mapping_result.results,
                    "rules": ["no_nulls_in_primary_keys", "valid_date_ranges", "referential_integrity"],
                }),
                "05_data_quality",
            )
            dashboard_future = pool.submit(self._generate_dashboard, result.kpis, mapping_result.results)
            summary_future = pool.submit(self._generate_exec_summary, result)

            quality_result = quality_future.result()
            dashboard = dashboard_future.result()
            summary = summary_future.result()

        result.step_results["05_data_quality"] = quality_result.results
        result.step_results["06_dashboard"] = dashboard
        result.dashboard_config = dashboard
        result.exec_summary = summary
        result.step_results["08_exec_summary"] = summary

        # ── Phase 6: Approval gate → Release (sequential) ──
        risk = intent.get("risk_level", "low")
        result.approval_required = risk in ("high", "medium")
        result.step_results["09_approval_gate"] = {
            "required": result.approval_required,
            "risk_level": risk,
        }
        result.step_results["10_release"] = {"status": "ready_for_release"}
        result.status = "success"
        if self._session:
            self._session.set_agent_state("shared", "current_stage", "10_release")
        self._retrieval.ingest_workflow_summary(
            workflow_id=self._wf_id,
            request=user_request,
            summary=result.exec_summary,
            pipeline="bi",
            intent=intent.get("intent", "bi_report"),
            stage="10_release",
            risk_level=risk,
        )
        monitor.finish_workflow(
            self._wf_id,
            status=result.status,
            summary=result.exec_summary[:180],
            approval_required=result.approval_required,
        )

        return {
            "workflow_id": result.workflow_id,
            "status": result.status,
            "kpis": result.kpis,
            "dashboard_config": result.dashboard_config,
            "exec_summary": result.exec_summary,
            "approval_required": result.approval_required,
            "steps": result.step_results,
        }

    def _generate_dashboard(self, kpis: list, mapping: dict) -> dict:
        import json
        ctx = RoutingContext(tier=ModelTier.BALANCED, agent_name="dashboard_gen", workflow_id=self._wf_id)
        raw = self._router.complete(
            messages=[{"role": "user", "content":
                f"Generate dashboard config JSON for KPIs: {kpis}\nMapping: {mapping}\n"
                "Return JSON: {title, charts: [{type, kpi, x_axis, y_axis, color}]}"}],
            system="You are a dashboard generation agent. Return valid JSON only.",
            ctx=ctx,
        )
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        try:
            return json.loads(raw.strip())
        except Exception:
            return {"title": "Dashboard", "charts": [], "raw": raw}

    def _generate_exec_summary(self, result: BIPipelineResult) -> str:
        ctx = RoutingContext(tier=ModelTier.PLANNING, agent_name="exec_summary", workflow_id=self._wf_id)
        return self._router.complete(
            messages=[{"role": "user", "content":
                f"Write a 3-paragraph executive summary for this BI analysis.\n"
                f"KPIs: {result.kpis}\nQuality: {result.step_results.get('05_data_quality', {})}"}],
            system="You are an executive communication specialist. Be concise and insight-driven.",
            ctx=ctx,
        )
