from __future__ import annotations

from types import SimpleNamespace

import pipelines.bi_pipeline as bi_pipeline_module
from core.memory.short_term import SessionMemory


def test_bi_pipeline_writes_summary_to_retrieval_store(monkeypatch):
    recorded = []

    class FakeRetrievalService:
        def ingest_workflow_summary(self, **kwargs):
            recorded.append(kwargs)

    monkeypatch.setattr(
        bi_pipeline_module,
        "get_retrieval_service",
        lambda: FakeRetrievalService(),
        raising=False,
    )

    class DummyRouter:
        def complete(self, messages, system, ctx=None, max_tokens=512, **kwargs):
            return "{}"

    class DummyResult:
        def __init__(self, results):
            self.results = results

    pipeline = bi_pipeline_module.BIPipeline(router=DummyRouter(), session=SessionMemory(session_id="wf-9"))

    def fake_run_agent(agent, task, stage):
        if stage == "01_requirements":
            return DummyResult({"audience": "executives"})
        if stage == "02_analysis":
            return DummyResult({"analysis_plan": {"focus": "revenue"}})
        if stage == "03_data_discovery":
            return DummyResult({"sources": [{"name": "warehouse"}]})
        if stage == "04_kpi_modeling":
            return DummyResult({"kpis": [{"name": "Revenue", "formula": "SUM(revenue)"}]})
        if stage == "04_etl_plan":
            return DummyResult({"plan": "etl"})
        if stage == "04_data_mapping":
            return DummyResult({"mapping": "done"})
        if stage == "07_stakeholder":
            return DummyResult({"alignment": "done"})
        if stage == "05_data_quality":
            return DummyResult({"checks": []})
        return DummyResult({"ok": True})

    pipeline._run_agent = fake_run_agent
    pipeline._generate_dashboard = lambda kpis, mapping: {"title": "Dashboard"}
    pipeline._generate_exec_summary = lambda result: "Executive summary for BI"
    pipeline._verifier = SimpleNamespace(run=lambda task: SimpleNamespace(results={"status": "ok"}))
    pipeline._duckdb = SimpleNamespace(run_kpi_sql=lambda name, formula: {"name": name, "formula": formula})

    response = pipeline.run("Prepare a revenue dashboard", {"domain": "finance", "risk_level": "low", "sub_goals": ["track revenue"]})

    assert response["status"] == "success"
    assert recorded
    assert recorded[0]["workflow_id"] == pipeline._wf_id
    assert recorded[0]["summary"] == "Executive summary for BI"
