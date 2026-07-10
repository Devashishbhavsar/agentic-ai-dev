"""L10 · Software Delivery Pipeline — 10 steps from requirements to running service, with parallel swarm execution."""
from __future__ import annotations

import json
import re
import subprocess
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agents.base import AgentTask, AgentResult
from agents.sw_eng.architect_agent import ArchitectAgent
from agents.sw_eng.api_agent import APIAgent
from agents.sw_eng.backend_agent import BackendAgent
from agents.sw_eng.frontend_agent import FrontendAgent
from agents.sw_eng.security_agent import SecurityAgent
from agents.qa.unit_test_agent import UnitTestAgent
from agents.qa.integration_test_agent import IntegrationTestAgent
from agents.devops.docker_agent import DockerAgent
from agents.devops.kubernetes_agent import KubernetesAgent
from agents.release.release_manager_agent import ReleaseManagerAgent
from agents.release.deployment_agent import DeploymentAgent
from agents.qa.verification_agent import VerificationAgent
from core.model_router import ModelRouter
from core.runtime import get_runtime_monitor
from core.retrieval import get_retrieval_service
from core.memory.short_term import SessionMemory
from core.swarm import ParallelSwarmJob, SwarmEngine
from core.external.claw_code import merge_file_entries, ClawCodeAdapter
from core.gates import SECURITY_RISK_PASS_THRESHOLD, effective_risk_score, security_scan_passed

WORKFLOW_OUTPUT_DIR = Path(__file__).resolve().parents[1] / "generated" / "workflows"

RUNNABLE_BUNDLE_PATHS = (
    "project/deploy/docker-compose.yml",
    "project/deploy/Dockerfile",
    "README.md",
)

MIN_BACKEND_FILES = 3
MIN_FRONTEND_FILES = 2

BACKEND_REQUIREMENTS_TXT = (
    "fastapi>=0.110\n"
    "uvicorn[standard]>=0.27\n"
    "sqlalchemy>=2.0\n"
    "psycopg2-binary>=2.9\n"
    "pydantic-settings>=2.0\n"
)

REQUIRED_FRONTEND_SCAFFOLD: tuple[tuple[str, str], ...] = (
    ("frontend/package.json", "package.json with name, scripts dev/build, react and react-dom deps"),
    ("frontend/src/main.tsx", "React 18 entry mounting App from ./App"),
)

README_FALLBACK_TEMPLATE = """# TaskFlow MVP

## Prerequisites
- Docker and Docker Compose

## Run
```bash
cd project/deploy
docker compose up --build
```

## Health checks
- Backend: http://localhost:8000/health
- Frontend: http://localhost:3000

## Request
{request}
"""


def fix_compose_build_dockerfile(compose: str) -> str:
    """Convert invalid `build: path` + sibling `dockerfile:` to Compose v3 build dict."""
    if not compose.strip():
        return compose
    lines = compose.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        build_match = re.match(r"^(\s+)build:\s*(.+?)\s*$", line)
        if build_match and i + 1 < len(lines):
            indent, context = build_match.group(1), build_match.group(2).strip()
            if not context.startswith("{") and not context.startswith("["):
                next_line = lines[i + 1]
                df_match = re.match(r"^(\s+)dockerfile:\s*(.+?)\s*$", next_line)
                if df_match and len(df_match.group(1)) == len(indent):
                    dockerfile = df_match.group(2).strip()
                    out.append(f"{indent}build:")
                    out.append(f"{indent}  context: {context}")
                    out.append(f"{indent}  dockerfile: {dockerfile}")
                    i += 2
                    continue
        out.append(line)
        i += 1
    return "\n".join(out) + ("\n" if compose.endswith("\n") else "")


def normalize_compose_yaml(compose: str) -> str:
    """Fix common LLM compose mistakes (typos, misplaced healthchecks/volumes)."""
    if not compose.strip():
        return compose

    import yaml

    compose = fix_compose_build_dockerfile(compose)
    compose = re.sub(r"(?m)^(vvolumes|volums)\s*:", "volumes:", compose)

    try:
        data = yaml.safe_load(compose)
    except yaml.YAMLError:
        return compose
    if not isinstance(data, dict):
        return compose

    if "vvolumes" in data and "volumes" not in data:
        data["volumes"] = data.pop("vvolumes")

    misplaced_healthchecks = data.pop("healthchecks", None)
    if isinstance(misplaced_healthchecks, dict):
        services = data.setdefault("services", {})
        if isinstance(services, dict):
            for service_name, health_cfg in misplaced_healthchecks.items():
                if (
                    service_name in services
                    and isinstance(services[service_name], dict)
                    and isinstance(health_cfg, dict)
                ):
                    services[service_name].setdefault("healthcheck", health_cfg)

    normalized = yaml.dump(
        data,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
    )
    return normalized if normalized.endswith("\n") else normalized + "\n"


def _compose_effective_risk_score(
    sec_results: dict[str, Any],
    backend_files: list[Any],
    frontend_files: list[Any],
) -> float:
    return effective_risk_score(
        sec_results,
        backend_files=backend_files,
        frontend_files=frontend_files,
    )


@dataclass
class SWDeliveryResult:
    workflow_id: str
    step_results: dict = field(default_factory=dict)
    artifacts: dict = field(default_factory=dict)
    approval_required: bool = False
    status: str = "success"


class SWDeliveryPipeline:
    """
    10-step SW delivery pipeline with parallel swarm execution:

    Phase 1 (sequential): Architecture design
    Phase 2 (parallel):   Backend code gen  ║  Frontend code gen  ║  K8s manifests
    Phase 3 (parallel):   Security review   ║  Unit tests  ║  Integration tests  ║  Dockerfile
    Phase 4 (parallel):   Release plan      ║  Deploy plan
    Phase 5 (sequential): Approval gate → Persist artifacts → Monitor
    """

    def __init__(
        self,
        router: ModelRouter,
        session: SessionMemory | None = None,
        workflow_id: str | None = None,
    ) -> None:
        self._router = router
        self._session = session
        self._wf_id = workflow_id or str(uuid.uuid4())
        self._retrieval = get_retrieval_service()
        self._swarm = SwarmEngine(router=router, session=session)

        self._architect = ArchitectAgent(router, session)
        self._api = APIAgent(router, session)
        self._backend = BackendAgent(router, session)
        self._frontend = FrontendAgent(router, session)
        self._security = SecurityAgent(router, session)
        self._unit_test = UnitTestAgent(router, session)
        self._integration_test = IntegrationTestAgent(router, session)
        self._docker = DockerAgent(router, session)
        self._k8s = KubernetesAgent(router, session)
        self._release_mgr = ReleaseManagerAgent(router, session)
        self._deployment = DeploymentAgent(router, session)
        self._verifier = VerificationAgent(router, session)
        self._claw_code = ClawCodeAdapter()

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

    def _mark_progress(self, stage: str, *, current_agent: str | None = None) -> None:
        monitor = get_runtime_monitor()
        if self._session:
            self._session.set_agent_state("shared", "current_stage", stage)
            if current_agent:
                self._session.set_agent_state("shared", "current_agent", current_agent)
        monitor.update_workflow(
            self._wf_id,
            stage=stage,
            status="running",
            current_agent=current_agent,
        )

    def _run_swarm_phase(
        self,
        jobs: list[ParallelSwarmJob],
        *,
        stage_label: str,
    ) -> dict[str, AgentResult]:
        """Execute a heterogeneous parallel phase via the in-repo Ruflo swarm engine."""
        monitor = get_runtime_monitor()
        monitor.update_workflow(self._wf_id, stage=stage_label, status='running')
        swarm_result = self._swarm.run_parallel(
            jobs,
            workflow_id=self._wf_id,
            runner=self._run_agent,
        )
        by_task_id = {result.task_id: result for result in swarm_result.results}
        return {
            job.label: by_task_id[job.task.task_id]
            for job in jobs
            if job.task.task_id in by_task_id
        }

    def _backend_agent_result(self, architecture: dict, *, extra_instruction: str = "") -> object:
        params: dict[str, Any] = {
            "spec": architecture,
            "tech_stack": "fastapi+sqlalchemy",
        }
        if extra_instruction:
            params["extra_instruction"] = extra_instruction
        return self._run_agent(
            self._backend,
            self._task("generate", params),
            "03_code_gen_backend",
        )

    def _backend_swarm_guidance(self, user_request: str, architecture: dict) -> dict[str, dict[str, Any]]:
        """Collect parallel planning guidance from in-repo agents before codegen."""
        arch_spec = architecture.get("architecture") if isinstance(architecture, dict) else None
        if not isinstance(arch_spec, dict):
            arch_spec = architecture if isinstance(architecture, dict) else {}
        components = arch_spec.get("components") if isinstance(arch_spec, dict) else []
        resources: list[str] = []
        if isinstance(components, list):
            for component in components:
                if isinstance(component, dict):
                    name = str(component.get("name") or "").strip()
                    if name:
                        resources.append(name.lower().replace(" ", "_"))
        if not resources:
            resources = ["users", "accounts", "ledger_entries", "payments", "transfers", "notifications", "audit_events"]

        jobs = [
            ParallelSwarmJob(
                agent=self._architect,
                task=self._task(
                    "design",
                    {
                        "requirements": {
                            "request": user_request,
                            "architecture": architecture,
                        },
                        "constraints": {"stack": "fastapi+sqlalchemy", "scope": "backend_codegen"},
                    },
                ),
                stage="03_backend_guidance_architecture",
                label="architect",
            ),
            ParallelSwarmJob(
                agent=self._api,
                task=self._task(
                    "design",
                    {
                        "resources": resources,
                        "auth_scheme": "bearer",
                    },
                ),
                stage="03_backend_guidance_api",
                label="api",
            ),
            ParallelSwarmJob(
                agent=self._security,
                task=self._task(
                    "review",
                    {
                        "code": "",
                        "architecture": architecture,
                    },
                ),
                stage="03_backend_guidance_security",
                label="security",
            ),
        ]

        swarm_result = self._swarm.run_parallel(
            jobs,
            workflow_id=self._wf_id,
            runner=self._run_agent,
        )
        by_task_id = {result.task_id: result for result in swarm_result.results}
        by_label: dict[str, dict[str, Any]] = {}
        for job in jobs:
            result = by_task_id.get(job.task.task_id)
            if not result:
                continue
            by_label[job.label] = result.results if isinstance(result.results, dict) else {"status": result.status, "error": result.error or ""}
        return by_label

    def _generate_backend_artifact(self, user_request: str, architecture: dict) -> object:
        tech_stack = "fastapi+sqlalchemy"
        self._mark_progress("03_backend_guidance", current_agent="backend")
        guidance = self._backend_swarm_guidance(user_request, architecture)

        if hasattr(self, "_claw_code") and self._claw_code.is_available():
            self._mark_progress("03_code_gen_backend", current_agent="backend")
            res = self._claw_code.generate_backend(
                request=user_request,
                architecture=architecture,
                tech_stack=tech_stack,
            )
            payload = {
                "provider": "claw-code+backend",
                "files": res.get("files", []),
                "setup_instructions": res.get("setup_instructions", []),
                "test_commands": res.get("test_commands", []),
                "swarm_guidance": guidance,
                "guidance_spec": {
                    "request": user_request,
                    "architecture": architecture,
                    "guidance": guidance,
                    "tech_stack": tech_stack,
                },
            }
            return type("ClawCodeResult", (), {"results": payload})()

        guidance_spec = {
            "request": user_request,
            "architecture": architecture,
            "guidance": guidance,
            "tech_stack": tech_stack,
        }
        self._mark_progress("03_code_gen_backend", current_agent="backend")
        backend_result = self._backend_agent_result(guidance_spec)
        backend_files = backend_result.results.get("files", []) if isinstance(backend_result.results, dict) else []
        merged_files = list(backend_files)

        if len(merged_files) < MIN_BACKEND_FILES:
            paths = ", ".join(entry["path"] for entry in merged_files) or "(none)"
            supplement = (
                f"Already generated: {paths}. "
                f"Add at least {MIN_BACKEND_FILES - len(merged_files)} more backend files "
                "(e.g. models.py, database.py, auth routes, config). "
                "Do not duplicate existing paths."
            )
            self._mark_progress("03_code_gen_backend_retry", current_agent="backend")
            extra = self._backend_agent_result(guidance_spec, extra_instruction=supplement)
            extra_files = extra.results.get("files", []) if isinstance(extra.results, dict) else []
            merged_files = merge_file_entries(merged_files, extra_files)

        if len(merged_files) < MIN_BACKEND_FILES:
            paths = ", ".join(entry["path"] for entry in merged_files) or "(none)"
            supplement = (
                f"Still incomplete ({len(merged_files)} files). Existing: {paths}. "
                f"Add database.py, config.py, and api/routes.py with working imports."
            )
            self._mark_progress("03_code_gen_backend_retry", current_agent="backend")
            extra = self._backend_agent_result(guidance_spec, extra_instruction=supplement)
            extra_files = extra.results.get("files", []) if isinstance(extra.results, dict) else []
            merged_files = merge_file_entries(merged_files, extra_files)

        merged_files = self._ensure_backend_requirements(architecture, merged_files)

        if merged_files:
            provider = backend_result.results.get("provider", "swarm+backend")
            payload = {
                "provider": provider,
                "files": merged_files,
                "setup_instructions": backend_result.results.get("setup_instructions", []),
                "test_commands": backend_result.results.get("test_commands", []),
                "swarm_guidance": guidance,
                "guidance_spec": guidance_spec,
            }
            return type("MergedResult", (), {"results": payload})()

        return backend_result

    def _ensure_backend_requirements(self, architecture: dict, files: list[dict]) -> list[dict]:
        has_requirements = any(
            str(entry.get("path", "")).replace("\\", "/").rstrip("/").endswith("requirements.txt")
            for entry in files
            if isinstance(entry, dict)
        )
        if has_requirements:
            return files
        return merge_file_entries(
            files,
            [{"path": "requirements.txt", "content": BACKEND_REQUIREMENTS_TXT}],
        )

    def _frontend_paths(self, files: list[Any]) -> set[str]:
        paths: set[str] = set()
        for entry in files:
            if isinstance(entry, dict):
                path = str(entry.get("path", "")).strip().lstrip("/")
                if path:
                    paths.add(path)
        return paths

    def _generate_single_frontend_file(
        self,
        user_request: str,
        architecture: dict,
        rel_path: str,
        instruction: str,
        stage: str,
    ) -> AgentResult:
        return self._run_agent(
            self._frontend,
            self._task("generate", {
                "wireframe": user_request,
                "api_spec": architecture,
                "extra_instruction": (
                    f"Generate ONLY one file at path {rel_path}. {instruction} "
                    "Return JSON: files with a single {{path, content}} entry."
                ),
            }),
            stage,
        )

    def _ensure_frontend_files(self, user_request: str, architecture: dict, frontend_result: AgentResult) -> AgentResult:
        if not isinstance(frontend_result.results, dict):
            return frontend_result
        files = list(frontend_result.results.get("files", []))
        paths = self._frontend_paths(files)

        for rel_path, instruction in REQUIRED_FRONTEND_SCAFFOLD:
            basename = rel_path.rsplit("/", 1)[-1]
            if rel_path in paths or any(p.endswith(f"/{basename}") or p == basename for p in paths):
                continue
            part = self._generate_single_frontend_file(
                user_request,
                architecture,
                rel_path,
                instruction,
                f"03_code_gen_frontend_{basename.replace('.', '_')}",
            )
            if isinstance(part.results, dict):
                files = merge_file_entries(files, part.results.get("files", []))
                paths = self._frontend_paths(files)

        if len(files) < MIN_FRONTEND_FILES:
            paths_str = ", ".join(sorted(paths)) or "(none)"
            frontend_result = self._run_agent(
                self._frontend,
                self._task("generate", {
                    "wireframe": user_request,
                    "api_spec": architecture,
                    "extra_instruction": (
                        f"Already generated: {paths_str}. "
                        "Add one more scaffold file (e.g. vite.config.ts or tsconfig.json). "
                        "Do not duplicate existing paths."
                    ),
                }),
                "03_code_gen_frontend_retry",
            )
            if isinstance(frontend_result.results, dict):
                files = merge_file_entries(files, frontend_result.results.get("files", []))
                paths = self._frontend_paths(files)

        has_page = any(
            str(f.get("path", "")).endswith((".tsx", ".jsx"))
            and ("page" in str(f.get("path", "")).lower() or "app.tsx" in str(f.get("path", "")).lower())
            for f in files
            if isinstance(f, dict)
        )
        if not has_page:
            paths_str = ", ".join(sorted(paths)) or "(none)"
            part = self._generate_single_frontend_file(
                user_request,
                architecture,
                "frontend/src/App.tsx",
                "Root App component with a simple TaskFlow dashboard placeholder.",
                "03_code_gen_frontend_page",
            )
            if isinstance(part.results, dict):
                files = merge_file_entries(files, part.results.get("files", []))

        frontend_result.results["files"] = files
        return frontend_result

    def _normalize_docker_artifacts(self, merged: dict[str, Any]) -> dict[str, Any]:
        compose = str(merged.get("compose_yaml") or "")
        if compose:
            compose = normalize_compose_yaml(compose)
            compose = re.sub(
                r"(?m)^(\s*)dockerfile:\s*Dockerfile\s*$",
                r"\1dockerfile: ../deploy/Dockerfile",
                compose,
            )
            merged["compose_yaml"] = compose
        if merged.get("parse_error") and merged.get("dockerfile") and merged.get("compose_yaml"):
            merged.pop("parse_error", None)
            merged["issues"] = [
                issue for issue in merged.get("issues", [])
                if "parse failed" not in issue.lower()
            ]
        return merged

    def _ensure_readme(self, user_request: str, docker_merged: dict[str, Any]) -> str:
        readme = str(docker_merged.get("readme_md") or "").strip()
        if len(readme) >= 80:
            return readme
        if not readme:
            part = self._run_agent(
                self._docker,
                self._task("readme", {"app_spec": {"language": "python", "framework": "fastapi"}}),
                "05_docker_readme_retry",
            )
            if isinstance(part.results, dict):
                readme = str(part.results.get("readme_md") or "").strip()
        if len(readme) >= 80:
            return readme
        return README_FALLBACK_TEMPLATE.format(request=user_request[:500])

    def _generate_docker_artifact(self, app_spec: dict | None = None) -> AgentResult:
        spec = {"language": "python", "framework": "fastapi", **(app_spec or {})}
        merged: dict[str, Any] = {}
        issues: list[str] = []

        steps = (
            ("dockerfile", "05_dockerfile", "dockerfile"),
            ("compose", "05_docker_compose", "compose_yaml"),
            ("readme", "05_docker_readme", "readme_md"),
        )
        for operation, stage, key in steps:
            part = self._run_agent(
                self._docker,
                self._task(operation, {"app_spec": spec}),
                stage,
            )
            payload = part.results if isinstance(part.results, dict) else {}
            if payload.get("parse_error"):
                part = self._run_agent(
                    self._docker,
                    self._task(operation, {"app_spec": spec, "compact": True}),
                    f"{stage}_retry",
                )
                payload = part.results if isinstance(part.results, dict) else {}
            if payload.get("parse_error"):
                merged["parse_error"] = True
                issues.append(f"{stage} JSON parse failed")
            elif payload.get(key):
                merged[key] = payload[key]

        merged = self._normalize_docker_artifacts(merged)
        if issues and not merged.get("parse_error"):
            merged["issues"] = issues

        return AgentResult(
            task_id=str(uuid.uuid4()),
            agent_name="docker",
            operation="generate",
            status="success" if merged.get("dockerfile") and merged.get("compose_yaml") else "failure",
            results=merged,
            confidence_score=0.88 if not merged.get("parse_error") else 0.2,
        )

    def _blocking_issues_before_release(self, result: SWDeliveryResult) -> list[str]:
        issues = list(self._has_parse_errors(result))
        backend = result.artifacts.get("backend_code", {})
        frontend = result.artifacts.get("frontend_code", {})
        docker = result.artifacts.get("dockerfile", {})
        if isinstance(backend, dict) and len(backend.get("files", [])) < MIN_BACKEND_FILES:
            issues.append(f"Backend incomplete: {len(backend.get('files', []))} file(s), need {MIN_BACKEND_FILES}")
        if isinstance(frontend, dict):
            front_files = frontend.get("files", [])
            if len(front_files) < MIN_FRONTEND_FILES:
                issues.append(f"Frontend incomplete: {len(front_files)} file(s), need {MIN_FRONTEND_FILES}")
            if not any(str(f.get("path", "")).endswith((".tsx", ".jsx")) for f in front_files if isinstance(f, dict)):
                issues.append("Frontend missing page component (.tsx/.jsx)")
        if isinstance(docker, dict):
            has_docker = bool(docker.get("compose_yaml") and docker.get("dockerfile"))
            if not has_docker and (docker.get("parse_error") or not docker.get("compose_yaml") or not docker.get("dockerfile")):
                issues.append("Docker/compose generation incomplete")
        verification = result.step_results.get("06_verification", {})
        if isinstance(verification, dict) and verification.get("passed") is False:
            issues.append("Verification gate failed")
        sec_scan = result.step_results.get("06_sec_scan", {})
        if isinstance(sec_scan, dict) and sec_scan.get("passed") is False:
            issues.append(f"Security risk score too high: {sec_scan.get('risk_score')}")
        return list(dict.fromkeys(issues))

    def _generate_frontend_artifact(self, user_request: str, architecture: dict) -> object:
        return self._run_agent(
            self._frontend,
            self._task("generate", {
                "wireframe": user_request,
                "api_spec": architecture,
            }),
            "03_code_gen_frontend",
        )

    def _workflow_output_dir(self) -> Path:
        return WORKFLOW_OUTPUT_DIR / self._wf_id

    def _write_text(self, base_dir: Path, relative_path: str, content: str) -> str:
        sanitized = relative_path.strip().lstrip('/').replace('..', '_')
        target = (base_dir / sanitized).resolve()
        if not str(target).startswith(str(base_dir.resolve())):
            raise ValueError(f'Unsafe artifact path: {relative_path}')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding='utf-8')
        bundle_root = (self._workflow_output_dir() / 'bundle').resolve()
        return str(target.relative_to(bundle_root))

    def _persist_generated_files(self, base_dir: Path, files: list[Any]) -> list[str]:
        saved: list[str] = []
        for entry in files:
            if isinstance(entry, dict):
                rel_path = str(entry.get('path') or '').strip()
                content = entry.get('content')
            else:
                rel_path = str(entry or '').strip()
                content = f'Generated artifact placeholder for {rel_path}\n' if rel_path else None
            if not rel_path or content is None:
                continue
            saved.append(self._write_text(base_dir, rel_path, str(content)))
        return saved

    def _persist_named_blobs(self, base_dir: Path, blobs: list[tuple[str, Any]]) -> list[str]:
        saved: list[str] = []
        for rel_path, content in blobs:
            if content in (None, '', [], {}):
                continue
            text = content if isinstance(content, str) else json.dumps(content, indent=2, default=str)
            saved.append(self._write_text(base_dir, rel_path, text))
        return saved

    def _persist_workflow_bundle(self, user_request: str, intent: dict, result: SWDeliveryResult) -> dict[str, Any]:
        output_dir = self._workflow_output_dir()
        bundle_dir = output_dir / 'bundle'
        bundle_dir.mkdir(parents=True, exist_ok=True)

        saved_files: list[str] = []
        saved_files.extend(self._persist_named_blobs(bundle_dir, [
            ('meta/request.txt', user_request),
            ('meta/intent.json', intent),
            ('meta/step_results.json', result.step_results),
            ('meta/artifacts.json', result.artifacts),
        ]))

        frontend = result.artifacts.get('frontend_code', {})
        if isinstance(frontend, dict):
            saved_files.extend(self._persist_generated_files(bundle_dir / 'project' / 'frontend', frontend.get('files', [])))
            saved_files.extend(self._persist_named_blobs(bundle_dir, [
                ('project/frontend/FRONTEND_RAW_OUTPUT.txt', frontend.get('raw_output')),
                ('project/frontend/frontend-metadata.json', {
                    'dependencies': frontend.get('dependencies', []),
                    'storybook_stories': frontend.get('storybook_stories', []),
                }),
            ]))

        backend = result.artifacts.get('backend_code', {})
        if isinstance(backend, dict):
            saved_files.extend(self._persist_generated_files(bundle_dir / 'project' / 'backend', backend.get('files', [])))
            saved_files.extend(self._persist_named_blobs(bundle_dir, [
                ('project/backend/BACKEND_RAW_OUTPUT.txt', backend.get('raw_output')),
                ('project/backend/backend-metadata.json', {
                    'provider': backend.get('provider'),
                    'setup_instructions': backend.get('setup_instructions', []),
                    'test_commands': backend.get('test_commands', []),
                }),
            ]))

        k8s = result.artifacts.get('k8s_manifests', {})
        if isinstance(k8s, dict):
            manifests = []
            for manifest in k8s.get('manifests', []):
                if isinstance(manifest, dict):
                    filename = str(manifest.get('filename') or '').strip()
                    yaml_content = manifest.get('yaml_content')
                else:
                    filename = str(manifest or '').strip()
                    yaml_content = f'# Generated manifest placeholder for {filename}\n' if filename else None
                if filename and yaml_content:
                    manifests.append((f'project/deploy/k8s/{filename}', yaml_content))
            saved_files.extend(self._persist_named_blobs(bundle_dir, manifests))

        docker = result.artifacts.get('dockerfile', {})
        if isinstance(docker, dict):
            readme_md = docker.get('readme_md')
            if not readme_md:
                readme_md = self._ensure_readme(user_request, docker)
                docker['readme_md'] = readme_md
                result.artifacts['dockerfile'] = docker
            saved_files.extend(self._persist_named_blobs(bundle_dir, [
                ('project/deploy/Dockerfile', docker.get('dockerfile')),
                ('project/deploy/docker-compose.yml', docker.get('compose_yaml')),
                ('project/backend/Dockerfile', docker.get('dockerfile')),
                ('project/deploy/docker-metadata.json', {
                    'image_size_estimate_mb': docker.get('image_size_estimate_mb'),
                    'build_time_estimate_seconds': docker.get('build_time_estimate_seconds'),
                    'security_notes': docker.get('security_notes'),
                }),
            ]))
            if readme_md:
                saved_files.extend(self._persist_named_blobs(bundle_dir, [('README.md', readme_md)]))

        unit_tests = result.step_results.get('05_unit_tests', {})
        if isinstance(unit_tests, dict):
            saved_files.extend(self._persist_generated_files(bundle_dir / 'project' / 'tests' / 'unit', unit_tests.get('test_files', [])))
            saved_files.extend(self._persist_named_blobs(bundle_dir, [('project/tests/unit/metadata.json', unit_tests)]))

        integration_tests = result.step_results.get('05_integration_tests', {})
        if isinstance(integration_tests, dict):
            saved_files.extend(self._persist_generated_files(bundle_dir / 'project' / 'tests' / 'integration', integration_tests.get('test_files', [])))
            saved_files.extend(self._persist_named_blobs(bundle_dir, [
                ('project/tests/integration/metadata.json', integration_tests),
                ('project/tests/integration/RAW_RESPONSE.txt', integration_tests.get('raw_response')),
            ]))

        saved_files.extend(self._persist_named_blobs(bundle_dir, [
            ('reports/security-review.json', result.step_results.get('04_security_review', {})),
            ('reports/security-scan.json', result.step_results.get('06_sec_scan', {})),
            ('reports/verification.json', result.step_results.get('06_verification', {})),
            ('reports/release-plan.json', result.step_results.get('09_release_plan', {})),
            ('reports/deployment-plan.json', result.step_results.get('09_deploy', {})),
        ]))

        manifest = {
            'workflow_id': self._wf_id,
            'request': user_request,
            'status': result.status,
            'approval_required': result.approval_required,
            'bundle_dir': str(bundle_dir),
            'saved_files': sorted(saved_files),
            'files_count': len(saved_files),
            'browse_url': f'/v1/workflows/{self._wf_id}/artifacts',
            'download_base_url': f'/v1/workflows/{self._wf_id}/artifacts/files/',
        }
        self._write_text(bundle_dir, 'manifest.json', json.dumps(manifest, indent=2, default=str))
        self._publish_to_github(bundle_dir, user_request)
        return manifest

    def _publish_to_github(self, bundle_dir: Path, user_request: str) -> None:
        """Create new GitHub repository and push the generated code there using PAT."""
        import os
        import httpx
        import subprocess

        token = os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN")
        if not token:
            return

        try:
            # 1. Fetch authenticated user details to obtain username
            headers = {
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github.v3+json",
            }
            user_resp = httpx.get("https://api.github.com/user", headers=headers, timeout=10.0)
            if user_resp.status_code != 200:
                return
            username = user_resp.json().get("login")
            if not username:
                return

            # 2. Create the remote repository on GitHub
            repo_name = f"project-{self._wf_id}"
            repo_data = {
                "name": repo_name,
                "description": f"Automatically generated project workflow bundle for request: {user_request[:100]}",
                "private": True,
            }
            create_resp = httpx.post(
                "https://api.github.com/user/repos",
                headers=headers,
                json=repo_data,
                timeout=15.0
            )
            if create_resp.status_code not in (201, 422):
                return

            # 3. Initialize git and configure user details locally
            subprocess.run(["git", "init"], cwd=str(bundle_dir), capture_output=True, check=True)
            subprocess.run(["git", "config", "user.name", "Enterprise Agent"], cwd=str(bundle_dir), capture_output=True, check=True)
            subprocess.run(["git", "config", "user.email", "agent@enterprise.local"], cwd=str(bundle_dir), capture_output=True, check=True)
            
            # 4. Stage and commit files
            subprocess.run(["git", "add", "."], cwd=str(bundle_dir), capture_output=True, check=True)
            subprocess.run(["git", "commit", "-m", "Initial commit from Enterprise Agent"], cwd=str(bundle_dir), capture_output=True, check=True)
            subprocess.run(["git", "branch", "-M", "main"], cwd=str(bundle_dir), capture_output=True, check=True)

            # 5. Link origin remote and push to main
            remote_url = f"https://oauth2:{token}@github.com/{username}/{repo_name}.git"
            subprocess.run(["git", "remote", "add", "origin", remote_url], cwd=str(bundle_dir), capture_output=True, check=True)
            subprocess.run(["git", "push", "-u", "origin", "main"], cwd=str(bundle_dir), capture_output=True, check=True)

        except Exception:
            pass

    def _docker_artifacts_on_disk(self, bundle_dir: Path) -> bool:
        compose = bundle_dir / 'project' / 'deploy' / 'docker-compose.yml'
        dockerfile = bundle_dir / 'project' / 'deploy' / 'Dockerfile'
        return (
            compose.is_file() and compose.stat().st_size > 30
            and dockerfile.is_file() and dockerfile.stat().st_size > 20
        )

    def _integration_tests_on_disk(self, bundle_dir: Path) -> bool:
        integration_dir = bundle_dir / 'project' / 'tests' / 'integration'
        if not integration_dir.is_dir():
            return False
        return any(integration_dir.rglob('test_*.py'))

    def _architecture_valid(self, result: SWDeliveryResult) -> bool:
        arch = result.artifacts.get('architecture', {})
        if not isinstance(arch, dict):
            return False
        if arch.get('parse_error'):
            return bool(arch.get('architecture') or arch.get('components') or arch.get('tech_stack'))
        return bool(arch)

    def _has_parse_errors(self, result: SWDeliveryResult, bundle_dir: Path | None = None) -> list[str]:
        issues: list[str] = []
        docker_on_disk = bundle_dir is not None and self._docker_artifacts_on_disk(bundle_dir)
        if not docker_on_disk:
            docker_art = result.artifacts.get('dockerfile', {})
            if isinstance(docker_art, dict) and docker_art.get('dockerfile') and docker_art.get('compose_yaml'):
                docker_on_disk = True

        tests_on_disk = bundle_dir is not None and self._integration_tests_on_disk(bundle_dir)
        if not tests_on_disk:
            integ = result.step_results.get('05_integration_tests', {})
            if isinstance(integ, dict) and integ.get('test_files'):
                tests_on_disk = True

        for key in ('02_architecture', '05_integration_tests', '08_containerize', '09_deploy'):
            step = result.step_results.get(key, {})
            if not isinstance(step, dict) or not step.get('parse_error'):
                continue
            if key == '02_architecture' and self._architecture_valid(result):
                continue
            if key == '05_integration_tests' and tests_on_disk:
                continue
            if key == '08_containerize' and docker_on_disk:
                continue
            issues.append(f'{key} output was truncated or invalid JSON')

        docker_artifact = result.artifacts.get('dockerfile', {})
        if isinstance(docker_artifact, dict) and docker_artifact.get('parse_error'):
            if not (docker_on_disk or (docker_artifact.get('dockerfile') and docker_artifact.get('compose_yaml'))):
                issues.append('dockerfile artifact was truncated or invalid JSON')
        return issues

    def _validate_compose_config(self, bundle_dir: Path) -> list[str]:
        compose_dir = bundle_dir / 'project' / 'deploy'
        compose_file = compose_dir / 'docker-compose.yml'
        if not compose_file.is_file():
            return []
        try:
            raw = compose_file.read_text(encoding='utf-8')
            fixed = normalize_compose_yaml(raw)
            if fixed != raw:
                compose_file.write_text(fixed, encoding='utf-8')
        except OSError:
            pass
        try:
            proc = subprocess.run(
                ['docker', 'compose', '-f', 'docker-compose.yml', 'config'],
                cwd=compose_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except FileNotFoundError:
            return []
        except subprocess.TimeoutExpired:
            return ['docker compose config timed out']
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or 'invalid compose').strip()
            return [f'docker compose config: {err[:240]}']
        return []

    def _validate_runnable_bundle(self, bundle_dir: Path) -> dict[str, Any]:
        missing: list[str] = []
        for rel_path in RUNNABLE_BUNDLE_PATHS:
            target = bundle_dir / rel_path
            if not target.is_file() or target.stat().st_size < 20:
                missing.append(rel_path)

        backend_py = list((bundle_dir / 'project' / 'backend').rglob('*.py'))
        if len(backend_py) < 2:
            missing.append('project/backend (need multiple Python modules, not just main.py)')

        requirements = list((bundle_dir / 'project' / 'backend').rglob('requirements.txt'))
        if not requirements:
            missing.append('project/backend/requirements.txt')

        frontend_pages = (
            list((bundle_dir / 'project' / 'frontend').rglob('*.tsx'))
            + list((bundle_dir / 'project' / 'frontend').rglob('*.jsx'))
        )
        if len(frontend_pages) < MIN_FRONTEND_FILES:
            missing.append(f'project/frontend (need {MIN_FRONTEND_FILES}+ page/component files)')

        compose_path = bundle_dir / 'project' / 'deploy' / 'docker-compose.yml'
        if compose_path.is_file():
            compose_text = compose_path.read_text(encoding='utf-8').lower()
            for service in ('postgres', 'backend', 'frontend'):
                if service not in compose_text:
                    missing.append(f'docker-compose.yml missing {service} service')
            missing.extend(self._validate_compose_config(bundle_dir))

        return {'passed': not missing, 'missing': missing}

    def _evaluate_delivery_gates(self, result: SWDeliveryResult, bundle_dir: Path) -> dict[str, Any]:
        issues: list[str] = []
        issues.extend(self._has_parse_errors(result, bundle_dir))

        verification = result.step_results.get('06_verification', {})
        if isinstance(verification, dict) and not verification.get('passed', True):
            for issue in verification.get('issues', []) or []:
                if issue and issue not in issues:
                    issues.append(issue)
            if not verification.get('issues'):
                issues.append('Verification gate failed')

        sec_scan = result.step_results.get('06_sec_scan', {})
        if isinstance(sec_scan, dict) and sec_scan.get('passed') is False:
            risk = sec_scan.get('risk_score', '?')
            issues.append(f'Security risk score too high: {risk} (must be < {SECURITY_RISK_PASS_THRESHOLD})')

        release = result.step_results.get('09_release_plan', {})
        if isinstance(release, dict) and release.get('go_no_go') is False:
            issues.extend(release.get('blocking_issues', []) or ['Release plan blocked go-live'])
        elif isinstance(release, dict) and release.get('skipped'):
            for issue in release.get('blocking_issues', []) or []:
                if issue and issue not in issues:
                    issues.append(issue)

        bundle_check = self._validate_runnable_bundle(bundle_dir)
        if not bundle_check['passed']:
            issues.extend(bundle_check.get('missing', []))

        deduped = list(dict.fromkeys(str(issue) for issue in issues if issue))
        sec_passed = (
            sec_scan.get('passed', True)
            if isinstance(sec_scan, dict)
            else True
        )
        return {
            'passed': not deduped,
            'issues': deduped,
            'bundle_check': bundle_check,
            'verification_passed': verification.get('passed', True) if isinstance(verification, dict) else True,
            'security_scan_passed': sec_passed,
        }

    def run(self, user_request: str, intent: dict, *, finalize: bool = True) -> dict:
        result = SWDeliveryResult(workflow_id=self._wf_id)
        sub_goals = intent.get('sub_goals', [user_request])
        monitor = get_runtime_monitor()
        if self._session:
            self._session.set_agent_state('shared', 'workflow_id', self._wf_id)
            self._session.set_agent_state('shared', 'pipeline', 'sw_delivery')
            self._session.set_agent_state('shared', 'current_stage', '01_requirements')
            self._session.set_agent_state('shared', 'shared_bullets', sub_goals[:4])
        monitor.update_workflow(self._wf_id, pipeline='sw_delivery', stage='01_requirements', status='running', sub_goals=sub_goals)

        result.step_results['01_requirements'] = {'goals': sub_goals, 'request': user_request}

        arch_result = self._run_agent(self._architect, self._task('design', {
            'requirements': {'goals': sub_goals},
            'constraints': {'cloud': 'any', 'language': 'python'},
        }), '02_architecture')
        result.step_results['02_architecture'] = arch_result.results
        result.artifacts['architecture'] = arch_result.results

        backend_result = self._generate_backend_artifact(user_request, arch_result.results)
        codegen_swarm = self._run_swarm_phase(
            [
                ParallelSwarmJob(
                    agent=self._frontend,
                    task=self._task("generate", {"wireframe": user_request, "api_spec": arch_result.results}),
                    stage="03_code_gen_frontend",
                    label="frontend",
                ),
                ParallelSwarmJob(
                    agent=self._k8s,
                    task=self._task("generate", {"service_spec": arch_result.results, "namespace": "production"}),
                    stage="03_code_gen_k8s",
                    label="k8s",
                ),
            ],
            stage_label="03_code_gen_swarm",
        )
        frontend_result = codegen_swarm["frontend"]
        frontend_result = self._ensure_frontend_files(user_request, arch_result.results, frontend_result)
        k8s_result = codegen_swarm["k8s"]

        result.step_results['03_code_gen'] = backend_result.results
        result.step_results['03_frontend'] = frontend_result.results
        result.artifacts['backend_code'] = backend_result.results
        result.artifacts['frontend_code'] = frontend_result.results
        result.artifacts['k8s_manifests'] = k8s_result.results

        code_snippet = str(backend_result.results.get('files', []))[:3000]

        self._mark_progress("04_security_review", current_agent="security")
        qa_swarm = self._run_swarm_phase(
            [
                ParallelSwarmJob(
                    agent=self._security,
                    task=self._task('review', {'code': code_snippet, 'architecture': arch_result.results}),
                    stage='04_security_review',
                    label='security',
                ),
                ParallelSwarmJob(
                    agent=self._unit_test,
                    task=self._task('generate_tests', {'code': code_snippet}),
                    stage='05_unit_tests',
                    label='unit_tests',
                ),
                ParallelSwarmJob(
                    agent=self._integration_test,
                    task=self._task('generate_tests', {
                        'api_spec': arch_result.results,
                        'services': ['api', 'database'],
                    }),
                    stage='05_integration_tests',
                    label='integration_tests',
                ),
            ],
            stage_label='05_qa_swarm',
        )
        sec_result = qa_swarm['security']
        unit_result = qa_swarm['unit_tests']
        integ_result = qa_swarm['integration_tests']
        if isinstance(integ_result.results, dict) and integ_result.results.get('parse_error'):
            integ_result = self._run_agent(
                self._integration_test,
                self._task('generate_tests', {
                    'api_spec': arch_result.results,
                    'services': ['api', 'database'],
                    'compact': True,
                }),
                '05_integration_tests_retry',
            )

        self._mark_progress("08_containerize", current_agent="docker")
        docker_result = self._generate_docker_artifact()
        if isinstance(docker_result.results, dict):
            readme_md = self._ensure_readme(user_request, docker_result.results)
            docker_result.results['readme_md'] = readme_md

        result.step_results['04_security_review'] = sec_result.results
        result.step_results['05_unit_tests'] = unit_result.results
        result.step_results['05_integration_tests'] = integ_result.results
        result.step_results['07_build'] = {'status': 'ready'}
        result.step_results['08_containerize'] = docker_result.results
        result.artifacts['dockerfile'] = docker_result.results

        risk_score = _compose_effective_risk_score(
            sec_result.results if isinstance(sec_result.results, dict) else {},
            backend_result.results.get('files', []) if isinstance(backend_result.results, dict) else [],
            frontend_result.results.get('files', []) if isinstance(frontend_result.results, dict) else [],
        )
        result.step_results['06_sec_scan'] = {
            'risk_score': risk_score,
            'passed': security_scan_passed(risk_score),
        }

        sec_verify = self._verifier.run(self._task('verify', {
            'pipeline_type': 'sw',
            'phase_name': 'security_and_tests',
            'phase_output': {
                'risk_score': risk_score,
                'tests': unit_result.results.get('tests', []) if isinstance(unit_result.results, dict) else [],
                'test_files': (
                    (unit_result.results.get('test_files', []) if isinstance(unit_result.results, dict) else [])
                    + (integ_result.results.get('test_files', []) if isinstance(integ_result.results, dict) else [])
                ),
                'unit_test_files': unit_result.results.get('test_files', []) if isinstance(unit_result.results, dict) else [],
                'integration_test_files': integ_result.results.get('test_files', []) if isinstance(integ_result.results, dict) else [],
                'test_file_count': (
                    (len(unit_result.results.get('test_files', []) or [])
                     if isinstance(unit_result.results, dict) else 0)
                    + (len(integ_result.results.get('test_files', []) or [])
                       if isinstance(integ_result.results, dict) else 0)
                ),
                'architecture': result.artifacts.get('architecture', {}),
                'backend_files': backend_result.results.get('files', []),
                'frontend_files': frontend_result.results.get('files', []),
                'dockerfile': result.artifacts.get('dockerfile', {}),
            },
        }))
        result.step_results['06_verification'] = sec_verify.results

        blocking = self._blocking_issues_before_release(result)
        if blocking:
            result.step_results['09_release_plan'] = {'skipped': True, 'blocking_issues': blocking}
            result.step_results['09_deploy'] = {'skipped': True, 'blocking_issues': blocking}
            release_result = AgentResult(
                task_id=str(uuid.uuid4()),
                agent_name="release_manager",
                operation="plan",
                status="skipped",
                results=result.step_results['09_release_plan'],
            )
            deploy_result = AgentResult(
                task_id=str(uuid.uuid4()),
                agent_name="deployment",
                operation="plan",
                status="skipped",
                results=result.step_results['09_deploy'],
            )
        else:
            self._mark_progress("09_release_swarm", current_agent="release")
            release_swarm = self._run_swarm_phase(
                [
                    ParallelSwarmJob(
                        agent=self._release_mgr,
                        task=self._task('plan', {
                            'service': user_request[:50],
                            'version': '1.0.0',
                            'risk_score': risk_score,
                        }),
                        stage='09_release_plan',
                        label='release',
                    ),
                    ParallelSwarmJob(
                        agent=self._deployment,
                        task=self._task('plan', {
                            'service': user_request[:50],
                            'environment': 'production',
                            'version': '1.0.0',
                        }),
                        stage='09_deploy',
                        label='deploy',
                    ),
                ],
                stage_label='09_release_swarm',
            )
            release_result = release_swarm['release']
            deploy_result = release_swarm['deploy']
            result.step_results['09_release_plan'] = release_result.results
            result.step_results['09_deploy'] = deploy_result.results

        risk_level = intent.get('risk_level', 'low')
        result.approval_required = risk_level in ('high', 'medium')
        result.step_results['10_approval_gate'] = {
            'required': result.approval_required,
            'risk_level': risk_level,
        }
        self._mark_progress("10_monitor", current_agent="verification")
        bundle_manifest = self._persist_workflow_bundle(user_request, intent, result)
        gate_report = self._evaluate_delivery_gates(result, Path(bundle_manifest['bundle_dir']))
        result.step_results['11_delivery_gates'] = gate_report
        bundle_manifest['delivery_gates'] = gate_report
        self._write_text(
            Path(bundle_manifest['bundle_dir']),
            'manifest.json',
            json.dumps(bundle_manifest, indent=2, default=str),
        )
        result.artifacts['artifact_bundle'] = bundle_manifest
        result.step_results['10_monitor'] = {
            'status': 'artifacts_persisted',
            'artifact_bundle': bundle_manifest,
            'delivery_gates': gate_report,
        }

        if gate_report['passed']:
            result.status = 'success'
            finish_summary = 'Software delivery ready'
        else:
            result.status = 'failed'
            finish_summary = 'Delivery gates failed: ' + '; '.join(gate_report['issues'][:3])
            result.approval_required = True

        bundle_manifest['status'] = result.status
        bundle_manifest['approval_required'] = result.approval_required
        self._write_text(
            Path(bundle_manifest['bundle_dir']),
            'manifest.json',
            json.dumps(bundle_manifest, indent=2, default=str),
        )

        self._retrieval.ingest_workflow_summary(
            workflow_id=self._wf_id,
            request=user_request,
            summary=(
                (finish_summary if result.status != 'success' else
                 f'Architecture ready; release plan prepared; deployment ready. Risk score: {risk_score}.')
                + f' Request: {user_request}'
            ),
            pipeline='sw_delivery',
            intent=intent.get('intent', 'sw_delivery'),
            stage='10_monitor',
            risk_level=intent.get('risk_level', 'low'),
        )
        if finalize:
            monitor.finish_workflow(
                self._wf_id,
                status=result.status,
                summary=finish_summary,
                approval_required=result.approval_required,
            )

        return {
            'workflow_id': result.workflow_id,
            'status': result.status,
            'artifacts': result.artifacts,
            'approval_required': result.approval_required,
            'delivery_gates': gate_report,
            'steps': result.step_results,
            'artifact_bundle_url': bundle_manifest['browse_url'],
        }
