"""
VerificationAgent — enforces the verification-before-completion skill.

Skill: verification-before-completion (obra/superpowers via skills.sh)
Rule: Evidence before claims. Never mark a step complete without running
      the verification gate and confirming output.
"""
from __future__ import annotations

import json
import re
from agents.base import BaseAgent, AgentTask, AgentResult
from core.model_router import ModelTier


class VerificationAgent(BaseAgent):
    """
    Quality gate that verifies pipeline phase output before passing it downstream.

    For BI pipelines: checks KPIs are complete, dashboard is valid, exec summary exists.
    For SW pipelines: checks architecture is present, security score is acceptable, artifacts exist.
    """

    name = "verification"
    swarm = "qa"
    default_tier = ModelTier.FAST

    @property
    def system_prompt(self) -> str:
        return (
            "You are a verification agent. Your ONLY job is to check whether a pipeline phase "
            "output is complete and correct. Apply the verification-before-completion principle: "
            "evidence before claims, always. "
            "Return JSON: {passed: bool, score: 0-1, issues: [str], recommendations: [str]}"
        )

    def run(self, task: AgentTask) -> AgentResult:
        pipeline_type = task.parameters.get("pipeline_type", "bi")
        phase_name = task.parameters.get("phase_name", "unknown")
        phase_output = task.parameters.get("phase_output", {})

        # Run rule-based checks first (no LLM cost)
        rule_result = self._rule_check(pipeline_type, phase_name, phase_output)

        if rule_result["passed"] and rule_result["score"] >= 0.8:
            # Sufficient evidence — no LLM needed
            return self._make_result(
                task,
                results=rule_result,
                status="success",
                confidence=rule_result["score"],
            )

        # Rule check found issues — use LLM for deeper analysis
        try:
            llm_result = self._llm_json(
                f"Verify this {pipeline_type} pipeline phase '{phase_name}' output.\n"
                f"Rule check result: {json.dumps(rule_result)}\n"
                f"Phase output keys: {list(phase_output.keys())[:15]}\n"
                "Determine if this is sufficient to proceed. "
                "Return JSON: {passed: bool, score: float, issues: [str], recommendations: [str]}"
            )
            merged = {
                "passed": rule_result["passed"] and llm_result.get("passed", True),
                "score": (rule_result["score"] + llm_result.get("score", 0.5)) / 2,
                "issues": rule_result["issues"] + llm_result.get("issues", []),
                "recommendations": llm_result.get("recommendations", []),
                "phase": phase_name,
                "pipeline": pipeline_type,
            }
        except Exception:
            merged = {**rule_result, "phase": phase_name, "pipeline": pipeline_type}

        return self._make_result(
            task,
            results=merged,
            status="success" if merged["passed"] else "partial",
            confidence=merged["score"],
        )

    def _rule_check(self, pipeline_type: str, phase: str, output: dict) -> dict:
        issues = []
        score = 1.0

        if pipeline_type == "bi":
            if "kpi" in phase:
                kpis = output.get("kpis", [])
                if not kpis:
                    issues.append("No KPIs generated")
                    score -= 0.5
                elif len(kpis) < 2:
                    issues.append(f"Only {len(kpis)} KPI — expected 3+")
                    score -= 0.2
                for k in kpis:
                    if not k.get("name"):
                        issues.append("KPI missing name")
                        score -= 0.1
                        break

            if "dashboard" in phase:
                dash = output.get("title") or output.get("dashboard_config", {})
                if not dash:
                    issues.append("Dashboard config missing")
                    score -= 0.4
                charts = output.get("charts", [])
                if not charts:
                    issues.append("No charts in dashboard")
                    score -= 0.2

            if "summary" in phase or "exec" in phase:
                summary = output if isinstance(output, str) else output.get("exec_summary", "")
                if not summary or len(str(summary)) < 50:
                    issues.append("Exec summary too short or missing")
                    score -= 0.3

        elif pipeline_type == "sw":
            if "arch" in phase:
                if not output.get("architecture"):
                    issues.append("Architecture spec missing")
                    score -= 0.5

            if "security" in phase or "sec" in phase:
                risk = output.get("risk_score", 0)
                if risk > 8:
                    issues.append(f"Security risk score {risk}/10 is too high")
                    score -= 0.4

            if "test" in phase:
                if not output.get("tests") and not output.get("test_cases"):
                    issues.append("No test cases generated")
                    score -= 0.3

        score = max(0.0, min(1.0, score))
        return {
            "passed": score >= 0.6 and not any("missing" in i.lower() and "critical" in i.lower() for i in issues),
            "score": score,
            "issues": issues,
            "recommendations": [f"Fix: {i}" for i in issues[:3]],
        }
