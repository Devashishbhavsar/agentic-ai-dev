import json

import pipelines.sw_delivery_pipeline as sw_pipeline_module
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


def _build_pipeline(monkeypatch, tmp_path):
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
        session=SessionMemory(session_id="wf-gates"),
        workflow_id="wf-gates",
    )
    pipeline._claw_code = type("Claw", (), {"is_available": lambda self: False})()
    return pipeline, DummyResult


def test_delivery_gates_fail_when_bundle_is_incomplete(monkeypatch, tmp_path):
    pipeline, DummyResult = _build_pipeline(monkeypatch, tmp_path)

    def fake_run_agent(agent, task, stage):
        if stage == "02_architecture":
            return _agent_result(agent, task, {"architecture": {"style": "monolith"}})
        if stage == "03_code_gen_backend":
            return _agent_result(agent, task, {"files": [{"path": "backend/main.py", "content": "print('ok')\n"}]})
        if stage == "03_code_gen_frontend":
            return _agent_result(agent, task, {"files": [{"path": "frontend/package.json", "content": "{}\n"}]})
        if stage == "03_code_gen_k8s":
            return _agent_result(agent, task, {"manifests": []})
        if stage == "04_security_review":
            return _agent_result(agent, task, {"risk_score": 2})
        if stage == "05_unit_tests":
            return _agent_result(agent, task, {"test_files": []})
        if stage == "05_integration_tests":
            return _agent_result(agent, task, {"test_files": []})
        if stage.startswith("05_dockerfile"):
            return _agent_result(agent, task, {"dockerfile": "FROM python:3.12\n"})
        if stage.startswith("05_docker_compose"):
            return _agent_result(agent, task, {"compose_yaml": "services:\n  api:\n    image: api\n"})
        if stage.startswith("05_docker_readme"):
            return _agent_result(agent, task, {"readme_md": "# stub\n"})
        if stage == "05_docker":
            return _agent_result(agent, task, {"dockerfile": "FROM python:3.12\n", "compose_yaml": "services:\n  api:\n    image: api\n"})
        if stage == "09_release_plan":
            return _agent_result(agent, task, {"go_no_go": False, "blocking_issues": ["tests missing"]})
        if stage == "09_deploy":
            return _agent_result(agent, task, {"plan": "deploy"})
        return _agent_result(agent, task, {})

    pipeline._run_agent = fake_run_agent
    pipeline._verifier = type(
        "Verifier",
        (),
        {"run": lambda self, task: DummyResult({"passed": False, "issues": ["No test cases generated"]})},
    )()

    response = pipeline.run(
        "Build TaskFlow MVP",
        {"intent": "sw_delivery", "risk_level": "low", "sub_goals": ["compose up"]},
    )

    assert response["status"] == "failed"
    assert response["approval_required"] is True
    assert response["delivery_gates"]["passed"] is False
    assert response["delivery_gates"]["issues"]

    # manifest is written into the project dir, not the old bundle dir
    project_slug = pipeline._project_slug("Build TaskFlow MVP")
    manifest = json.loads((tmp_path / "projects" / project_slug / "manifest.json").read_text())
    assert manifest["delivery_gates"]["passed"] is False
    assert manifest["status"] == "failed"
    assert manifest["approval_required"] is True


def test_delivery_gates_pass_for_complete_bundle(monkeypatch, tmp_path):
    pipeline, DummyResult = _build_pipeline(monkeypatch, tmp_path)

    backend_files = [
        {"path": "backend/main.py", "content": "from fastapi import FastAPI\neval('bad')\napp = FastAPI()\n"},
        {"path": "backend/app/api.py", "content": "router = object()\n"},
        {"path": "backend/app/models.py", "content": "class User: pass\n"},
        {"path": "backend/requirements.txt", "content": "fastapi\nuvicorn\nsqlalchemy\n"},
    ]
    frontend_files = [
        {"path": "frontend/package.json", "content": '{"name":"taskflow"}\n'},
        {"path": "frontend/app/page.tsx", "content": "export default function Page(){return null}\n"},
        {"path": "frontend/src/main.tsx", "content": "import App from './App'\n"},
    ]
    compose_yaml = (
        "services:\n"
        "  postgres:\n    image: postgres:16\n"
        "  backend:\n    build: .\n"
        "  frontend:\n    build: ./frontend\n"
    )

    def fake_run_agent(agent, task, stage):
        if stage == "02_architecture":
            return _agent_result(agent, task, {"architecture": {"style": "monolith"}})
        if stage == "03_code_gen_backend":
            return _agent_result(agent, task, {"files": backend_files})
        if stage == "03_code_gen_frontend":
            return _agent_result(agent, task, {"files": frontend_files})
        if stage == "03_code_gen_k8s":
            return _agent_result(agent, task, {"manifests": []})
        if stage == "04_security_review":
            return _agent_result(agent, task, {"risk_score": 2})
        if stage == "05_unit_tests":
            return _agent_result(agent, task, {"test_files": [{"path": "tests/test_main.py", "content": "def test_ok(): pass\n"}]})
        if stage == "05_integration_tests":
            return _agent_result(agent, task, {"test_files": [{"path": "tests/integration/test_health.py", "content": "def test_health(): pass\n"}]})
        if stage.startswith("05_dockerfile"):
            return _agent_result(agent, task, {"dockerfile": "FROM python:3.12\nWORKDIR /app\n"})
        if stage.startswith("05_docker_compose"):
            return _agent_result(agent, task, {"compose_yaml": compose_yaml})
        if stage.startswith("05_docker_readme"):
            return _agent_result(agent, task, {"readme_md": "# TaskFlow\n\nRun docker compose up.\n"})
        if stage == "09_release_plan":
            return _agent_result(agent, task, {"go_no_go": True, "blocking_issues": []})
        if stage == "09_deploy":
            return _agent_result(agent, task, {"plan": "deploy"})
        return _agent_result(agent, task, {})

    pipeline._run_agent = fake_run_agent
    pipeline._verifier = type(
        "Verifier",
        (),
        {"run": lambda self, task: DummyResult({"passed": True, "issues": []})},
    )()

    response = pipeline.run(
        "Build TaskFlow MVP",
        {"intent": "sw_delivery", "risk_level": "low", "sub_goals": ["compose up"]},
    )

    assert response["status"] == "success"
    assert response["delivery_gates"]["passed"] is True

    project_slug = pipeline._project_slug("Build TaskFlow MVP")
    manifest = json.loads((tmp_path / "projects" / project_slug / "manifest.json").read_text())
    assert manifest["status"] == "success"
    assert manifest["delivery_gates"]["passed"] is True


def test_delivery_gates_fail_when_security_risk_too_high(monkeypatch, tmp_path):
    pipeline, DummyResult = _build_pipeline(monkeypatch, tmp_path)

    backend_files = [
        {"path": "backend/main.py", "content": "from fastapi import FastAPI\neval('bad')\napp = FastAPI()\n"},
        {"path": "backend/app/api.py", "content": "router = object()\n"},
        {"path": "backend/app/models.py", "content": "class User: pass\n"},
        {"path": "backend/requirements.txt", "content": "fastapi\nuvicorn\nsqlalchemy\n"},
    ]
    frontend_files = [
        {"path": "frontend/package.json", "content": '{"name":"taskflow"}\n'},
        {"path": "frontend/app/page.tsx", "content": "export default function Page(){return null}\n"},
        {"path": "frontend/src/main.tsx", "content": "import App from './App'\n"},
    ]
    compose_yaml = (
        "services:\n"
        "  postgres:\n    image: postgres:16\n"
        "  backend:\n    build: .\n"
        "  frontend:\n    build: ./frontend\n"
    )

    def fake_run_agent(agent, task, stage):
        if stage == "02_architecture":
            return _agent_result(agent, task, {"architecture": {"style": "monolith"}})
        if stage == "03_code_gen_backend":
            return _agent_result(agent, task, {"files": backend_files})
        if stage == "03_code_gen_frontend":
            return _agent_result(agent, task, {"files": frontend_files})
        if stage == "03_code_gen_k8s":
            return _agent_result(agent, task, {"manifests": []})
        if stage == "04_security_review":
            return _agent_result(agent, task, {
                "risk_score": 7,
                "vulnerabilities": [{"severity": "high", "cve": "CVE-TEST", "location": "auth"}],
            })
        if stage == "05_unit_tests":
            return _agent_result(agent, task, {"test_files": [{"path": "tests/test_main.py", "content": "def test_ok(): pass\n"}]})
        if stage == "05_integration_tests":
            return _agent_result(agent, task, {"test_files": [{"path": "tests/integration/test_health.py", "content": "def test_health(): pass\n"}]})
        if stage.startswith("05_dockerfile"):
            return _agent_result(agent, task, {"dockerfile": "FROM python:3.12\nWORKDIR /app\n"})
        if stage.startswith("05_docker_compose"):
            return _agent_result(agent, task, {"compose_yaml": compose_yaml})
        if stage.startswith("05_docker_readme"):
            return _agent_result(agent, task, {"readme_md": "# TaskFlow\n\nRun docker compose up.\n"})
        return _agent_result(agent, task, {})

    pipeline._run_agent = fake_run_agent
    pipeline._verifier = type(
        "Verifier",
        (),
        {"run": lambda self, task: DummyResult({"passed": True, "issues": []})},
    )()

    response = pipeline.run(
        "Build TaskFlow MVP",
        {"intent": "sw_delivery", "risk_level": "low", "sub_goals": ["compose up"]},
    )

    assert response["status"] == "failed"
    assert response["delivery_gates"]["passed"] is False
    assert response["delivery_gates"]["security_scan_passed"] is False
    assert any("Security risk score" in issue for issue in response["delivery_gates"]["issues"])
    assert response["steps"]["09_release_plan"]["skipped"] is True
    assert response["approval_required"] is True


def test_delivery_gates_ignore_parse_error_when_docker_on_disk(monkeypatch, tmp_path):
    pipeline, _DummyResult = _build_pipeline(monkeypatch, tmp_path)
    bundle_dir = tmp_path / "wf-gates-disk" / "bundle"
    compose_dir = bundle_dir / "project" / "deploy"
    compose_dir.mkdir(parents=True)
    (compose_dir / "docker-compose.yml").write_text(
        "services:\n  postgres:\n    image: postgres:16\n"
        "  backend:\n    build: ../backend\n  frontend:\n    build: ../frontend\n"
    )
    (compose_dir / "Dockerfile").write_text("FROM python:3.12\n")

    result = sw_pipeline_module.SWDeliveryResult(workflow_id="wf-gates-disk")
    result.artifacts["dockerfile"] = {"parse_error": True, "dockerfile": "FROM python:3.12\n", "compose_yaml": "services:\n  api:\n"}
    result.step_results["08_containerize"] = {"parse_error": True}

    issues = pipeline._has_parse_errors(result, bundle_dir)
    assert not any("08_containerize" in issue for issue in issues)
    assert not any("dockerfile artifact" in issue for issue in issues)


def test_fix_compose_build_dockerfile_sibling_key():
    from pipelines.sw_delivery_pipeline import fix_compose_build_dockerfile

    raw = (
        "services:\n"
        "  backend:\n"
        "    build: ../backend\n"
        "    dockerfile: ../deploy/Dockerfile\n"
        "    ports:\n"
        "      - \"8000:8000\"\n"
    )
    fixed = fix_compose_build_dockerfile(raw)
    assert "build: ../backend\n    dockerfile:" not in fixed
    assert "context: ../backend" in fixed
    assert "dockerfile: ../deploy/Dockerfile" in fixed


def test_normalize_compose_fixes_healthchecks_and_vvolumes():
    from pipelines.sw_delivery_pipeline import normalize_compose_yaml

    raw = (
        "version: '3'\n"
        "services:\n"
        "  backend:\n"
        "    build: ../backend\n"
        "    dockerfile: ../deploy/Dockerfile\n"
        "  frontend:\n"
        "    build: ../frontend\n"
        "healthchecks:\n"
        "  backend:\n"
        "    test: ['CMD', 'curl', '-f', 'http://localhost:8000/health']\n"
        "    interval: 30s\n"
        "vvolumes:\n"
        "  db-data:\n"
    )
    fixed = normalize_compose_yaml(raw)
    assert "healthchecks:" not in fixed
    assert "vvolumes:" not in fixed
    assert "healthcheck:" in fixed
    assert "volumes:" in fixed
    assert "context: ../backend" in fixed


def test_normalize_docker_fixes_invalid_compose():
    from pipelines.sw_delivery_pipeline import SWDeliveryPipeline

    pipeline = SWDeliveryPipeline(router=object(), workflow_id="wf-compose-fix")
    merged = pipeline._normalize_docker_artifacts({
        "dockerfile": "FROM python:3.12\n",
        "compose_yaml": (
            "services:\n  backend:\n    build: ../backend\n"
            "    dockerfile: ../deploy/Dockerfile\n"
        ),
    })
    assert "context: ../backend" in merged["compose_yaml"]


def test_ensure_backend_requirements_scaffold_without_llm():
    from pipelines.sw_delivery_pipeline import SWDeliveryPipeline, BACKEND_REQUIREMENTS_TXT

    pipeline = SWDeliveryPipeline(router=object(), workflow_id="wf-req")
    files = pipeline._ensure_backend_requirements({}, [{"path": "backend/main.py", "content": "x"}])
    assert any(f.get("path") == "requirements.txt" for f in files)
    req = next(f for f in files if f.get("path") == "requirements.txt")
    assert req["content"] == BACKEND_REQUIREMENTS_TXT


def test_verification_security_and_tests_counts_test_files():
    from agents.qa.verification_agent import VerificationAgent

    agent = VerificationAgent()
    result = agent._rule_check(
        "sw",
        "security_and_tests",
        {
            "risk_score": 2,
            "test_file_count": 3,
            "test_files": [{"path": "tests/test_main.py"}],
            "backend_files": [{}, {}, {}],
            "frontend_files": [{}, {}],
            "dockerfile": {"dockerfile": "FROM x\n", "compose_yaml": "services:\n  api:\n"},
        },
    )
    assert "No test cases generated" not in result["issues"]



def test_backend_codegen_marks_progress(monkeypatch, tmp_path):
    pipeline, DummyResult = _build_pipeline(monkeypatch, tmp_path)
    updates = []

    class DummyMonitor:
        def update_workflow(self, *args, **kwargs):
            updates.append((kwargs.get("stage"), kwargs.get("current_agent")))

    monkeypatch.setattr(sw_pipeline_module, "get_runtime_monitor", lambda: DummyMonitor())
    monkeypatch.setattr(pipeline, "_backend_swarm_guidance", lambda *a, **k: {})
    monkeypatch.setattr(
        pipeline,
        "_backend_agent_result",
        lambda *a, **k: DummyResult({
            "files": [
                {"path": "backend/main.py", "content": "print('ok')\n"},
                {"path": "backend/models.py", "content": "print('ok')\n"},
                {"path": "backend/routes.py", "content": "print('ok')\n"},
            ],
            "setup_instructions": [],
            "test_commands": [],
        }),
    )

    result = pipeline._generate_backend_artifact("build fintech api", {"architecture": {"style": "monolith"}})

    assert result.results["provider"] == "swarm+backend"
    assert ("03_backend_guidance", "backend") in updates
    assert ("03_code_gen_backend", "backend") in updates
