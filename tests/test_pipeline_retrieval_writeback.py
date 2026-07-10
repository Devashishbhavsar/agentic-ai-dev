from __future__ import annotations

import json
from types import SimpleNamespace

import pipelines.bi_pipeline as bi_pipeline_module
from agents.base import AgentResult
from core.memory.short_term import SessionMemory


def _agent_result(agent, task, results):
    return AgentResult(
        task_id=task.task_id,
        agent_name=getattr(agent, "name", "agent"),
        operation=task.operation,
        status="success",
        results=results,
        confidence_score=0.9,
    )


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


def test_bi_pipeline_reuses_external_workflow_id(monkeypatch):
    class FakeRetrievalService:
        def ingest_workflow_summary(self, **kwargs):
            pass

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

    pipeline = bi_pipeline_module.BIPipeline(
        router=DummyRouter(),
        session=SessionMemory(session_id="wf-10"),
        workflow_id="wf-discord",
    )
    pipeline._run_agent = lambda agent, task, stage: DummyResult({"kpis": []} if stage == "04_kpi_modeling" else {})
    pipeline._generate_dashboard = lambda kpis, mapping: {"title": "Dashboard"}
    pipeline._generate_exec_summary = lambda result: "Executive summary for BI"
    pipeline._verifier = SimpleNamespace(run=lambda task: SimpleNamespace(results={"status": "ok"}))
    pipeline._duckdb = SimpleNamespace(run_kpi_sql=lambda name, formula: {"name": name, "formula": formula})

    response = pipeline.run("Prepare a revenue dashboard", {"domain": "finance", "risk_level": "low"})

    assert response["workflow_id"] == "wf-discord"
    assert pipeline._wf_id == "wf-discord"


def test_sw_delivery_pipeline_reuses_external_workflow_id(monkeypatch, tmp_path):
    import pipelines.sw_delivery_pipeline as sw_pipeline_module

    class FakeRetrievalService:
        def ingest_workflow_summary(self, **kwargs):
            pass

    monkeypatch.setattr(
        sw_pipeline_module,
        "get_retrieval_service",
        lambda: FakeRetrievalService(),
        raising=False,
    )
    monkeypatch.setattr(sw_pipeline_module, "WORKFLOW_OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(sw_pipeline_module, "PROJECT_OUTPUT_DIR", tmp_path / "projects")

    class DummyRouter:
        pass

    class DummyResult:
        def __init__(self, results):
            self.results = results

    pipeline = sw_pipeline_module.SWDeliveryPipeline(
        router=DummyRouter(),
        session=SessionMemory(session_id="wf-11"),
        workflow_id="wf-discord-sw",
    )
    pipeline._claw_code = SimpleNamespace(is_available=lambda: False)

    from tests.test_claw_code_integration import _complete_sw_mocks

    backend_files, frontend_files, compose_yaml = _complete_sw_mocks()

    def fake_run_agent(agent, task, stage):
        if stage == "02_architecture":
            return _agent_result(agent, task, {"service": "api"})
        if stage == "03_code_gen_backend":
            return _agent_result(agent, task, {"files": backend_files})
        if stage == "03_code_gen_frontend":
            return _agent_result(agent, task, {"files": frontend_files})
        if stage == "03_code_gen_k8s":
            return _agent_result(agent, task, {"manifests": ["deployment.yaml"]})
        if stage == "04_security_review":
            return _agent_result(agent, task, {"risk_score": 3})
        if stage == "05_unit_tests":
            return _agent_result(agent, task, {"test_files": [{"path": "tests/test_app.py", "content": "def test_ok(): pass\n"}]})
        if stage == "05_integration_tests":
            return _agent_result(agent, task, {"test_files": [{"path": "tests/integration/test_api.py", "content": "def test_ok(): pass\n"}]})
        if stage.startswith("05_dockerfile"):
            return _agent_result(agent, task, {"dockerfile": "FROM python:3.12\nWORKDIR /app\nCOPY . .\nCMD [\"uvicorn\", \"main:app\"]\n"})
        if stage.startswith("05_docker_compose"):
            return _agent_result(agent, task, {"compose_yaml": compose_yaml})
        if stage.startswith("05_docker_readme"):
            return _agent_result(agent, task, {
                "readme_md": "# Ship the API\n\n## Run\n\ncd project/deploy && docker compose up --build\n",
            })
        if stage == "09_release_plan":
            return _agent_result(agent, task, {"go_no_go": True})
        if stage == "09_deploy":
            return _agent_result(agent, task, {"plan": "deploy"})
        return _agent_result(agent, task, {})

    pipeline._run_agent = fake_run_agent
    pipeline._verifier = SimpleNamespace(run=lambda task: SimpleNamespace(results={"passed": True, "issues": []}))

    response = pipeline.run("Ship the API", {"intent": "sw_delivery", "risk_level": "low", "sub_goals": ["ship api"]})

    assert response["workflow_id"] == "wf-discord-sw"
    assert pipeline._wf_id == "wf-discord-sw"
    assert response["status"] == "success"
    assert response["approval_required"] is False
    assert response["artifact_bundle_url"] == "/v1/workflows/wf-discord-sw/artifacts"
    project_slug = pipeline._project_slug("Ship the API")
    manifest_path = tmp_path / "projects" / project_slug / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text())
    assert manifest["files_count"] >= 4
    assert "meta/request.txt" in manifest["saved_files"]

