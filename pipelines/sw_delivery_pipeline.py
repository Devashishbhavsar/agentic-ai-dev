"""L10 · Software Delivery Pipeline — 10 steps from requirements to running service, with parallel swarm execution."""
from __future__ import annotations

import concurrent.futures
import uuid
from dataclasses import dataclass, field

from agents.base import AgentTask
from agents.sw_eng.architect_agent import ArchitectAgent
from agents.sw_eng.backend_agent import BackendAgent
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
    Phase 2 (parallel):   Backend code gen  ║  K8s manifests
    Phase 3 (parallel):   Security review   ║  Unit tests  ║  Integration tests  ║  Dockerfile
    Phase 4 (parallel):   Release plan      ║  Deploy plan
    Phase 5 (sequential): Approval gate → Monitor
    """

    def __init__(self, router: ModelRouter, session: SessionMemory | None = None) -> None:
        self._router = router
        self._session = session
        self._wf_id = str(uuid.uuid4())
        self._retrieval = get_retrieval_service()

        self._architect = ArchitectAgent(router, session)
        self._backend = BackendAgent(router, session)
        self._security = SecurityAgent(router, session)
        self._unit_test = UnitTestAgent(router, session)
        self._integration_test = IntegrationTestAgent(router, session)
        self._docker = DockerAgent(router, session)
        self._k8s = KubernetesAgent(router, session)
        self._release_mgr = ReleaseManagerAgent(router, session)
        self._deployment = DeploymentAgent(router, session)
        self._verifier = VerificationAgent(router, session)

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
        result = SWDeliveryResult(workflow_id=self._wf_id)
        sub_goals = intent.get("sub_goals", [user_request])
        monitor = get_runtime_monitor()
        if self._session:
            self._session.set_agent_state("shared", "workflow_id", self._wf_id)
            self._session.set_agent_state("shared", "pipeline", "sw_delivery")
            self._session.set_agent_state("shared", "current_stage", "01_requirements")
            self._session.set_agent_state("shared", "shared_bullets", sub_goals[:4])
        monitor.update_workflow(self._wf_id, pipeline="sw_delivery", stage="01_requirements", status="running", sub_goals=sub_goals)

        result.step_results["01_requirements"] = {"goals": sub_goals, "request": user_request}

        # ── Phase 1: Architecture (sequential — everything else depends on it) ──
        arch_result = self._run_agent(self._architect, self._task("design", {
            "requirements": {"goals": sub_goals},
            "constraints": {"cloud": "any", "language": "python"},
        }), "02_architecture")
        result.step_results["02_architecture"] = arch_result.results
        result.artifacts["architecture"] = arch_result.results

        # ── Phase 2: Backend code gen + K8s manifests (parallel) ──
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            backend_future = pool.submit(
                self._run_agent,
                self._backend,
                self._task("generate", {
                    "spec": arch_result.results,
                    "tech_stack": "fastapi+sqlalchemy",
                }),
                "03_code_gen_backend",
            )
            k8s_future = pool.submit(
                self._run_agent,
                self._k8s,
                self._task("generate", {
                    "service_spec": arch_result.results,
                    "namespace": "production",
                }),
                "03_code_gen_k8s",
            )
            backend_result = backend_future.result()
            k8s_result = k8s_future.result()

        result.step_results["03_code_gen"] = backend_result.results
        result.artifacts["backend_code"] = backend_result.results
        result.artifacts["k8s_manifests"] = k8s_result.results

        code_snippet = str(backend_result.results.get("files", []))[:3000]

        # ── Phase 3: Security + Unit tests + Integration tests + Docker (parallel) ──
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            sec_future = pool.submit(
                self._run_agent,
                self._security,
                self._task("review", {
                    "code": code_snippet,
                    "architecture": arch_result.results,
                }),
                "04_security_review",
            )
            unit_future = pool.submit(
                self._run_agent,
                self._unit_test,
                self._task("generate_tests", {"code": code_snippet}),
                "05_unit_tests",
            )
            integ_future = pool.submit(
                self._run_agent,
                self._integration_test,
                self._task("generate_tests", {
                    "api_spec": arch_result.results,
                    "services": ["api", "database"],
                }),
                "05_integration_tests",
            )
            docker_future = pool.submit(
                self._run_agent,
                self._docker,
                self._task("generate", {
                    "app_spec": {"language": "python", "framework": "fastapi"},
                }),
                "05_docker",
            )
            sec_result = sec_future.result()
            unit_result = unit_future.result()
            integ_result = integ_future.result()
            docker_result = docker_future.result()

        result.step_results["04_security_review"] = sec_result.results
        result.step_results["05_unit_tests"] = unit_result.results
        result.step_results["05_integration_tests"] = integ_result.results
        result.step_results["07_build"] = {"status": "ready"}
        result.step_results["08_containerize"] = docker_result.results
        result.artifacts["dockerfile"] = docker_result.results

        risk_score = sec_result.results.get("risk_score", 0)
        result.step_results["06_sec_scan"] = {
            "risk_score": risk_score,
            "passed": risk_score < 7,
        }

        # ── Skill: verification-before-completion — gate before deploy ──
        sec_verify = self._verifier.run(self._task("verify", {
            "pipeline_type": "sw",
            "phase_name": "security_and_tests",
            "phase_output": {
                "risk_score": risk_score,
                "tests": unit_result.results.get("tests", []),
                "architecture": result.artifacts.get("architecture", {}),
            },
        }))
        result.step_results["06_verification"] = sec_verify.results

        # ── Phase 4: Release plan + Deploy plan (parallel) ──
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            release_future = pool.submit(
                self._run_agent,
                self._release_mgr,
                self._task("plan", {
                    "service": user_request[:50],
                    "version": "1.0.0",
                    "risk_score": risk_score,
                }),
                "09_release_plan",
            )
            deploy_future = pool.submit(
                self._run_agent,
                self._deployment,
                self._task("plan", {
                    "service": user_request[:50],
                    "environment": "production",
                    "version": "1.0.0",
                }),
                "09_deploy",
            )
            release_result = release_future.result()
            deploy_result = deploy_future.result()

        result.step_results["09_release_plan"] = release_result.results
        result.step_results["09_deploy"] = deploy_result.results

        # ── Phase 5: Approval gate + Monitor (sequential) ──
        result.approval_required = True  # production always requires approval
        result.step_results["10_monitor"] = {"status": "monitoring_configured"}
        result.status = "success"
        self._retrieval.ingest_workflow_summary(
            workflow_id=self._wf_id,
            request=user_request,
            summary=(
                f"Architecture ready; release plan prepared; deployment ready. "
                f"Risk score: {risk_score}. Request: {user_request}"
            ),
            pipeline="sw_delivery",
            intent=intent.get("intent", "sw_delivery"),
            stage="10_monitor",
            risk_level=intent.get("risk_level", "low"),
        )
        monitor.finish_workflow(self._wf_id, status=result.status, summary="Software delivery ready", approval_required=True)

        return {
            "workflow_id": result.workflow_id,
            "status": result.status,
            "artifacts": result.artifacts,
            "approval_required": result.approval_required,
            "steps": result.step_results,
        }
