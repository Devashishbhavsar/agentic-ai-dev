"""Smoke tests for the BI pipeline — mock the LLM calls."""
from __future__ import annotations

import json
import uuid
from unittest.mock import patch, MagicMock

import pytest

from agents.base import AgentTask
from agents.bi.requirements_agent import RequirementsAgent
from core.model_router import ModelRouter


MOCK_REQUIREMENTS = json.dumps({
    "metrics": ["total_revenue", "churn_rate"],
    "data_sources": ["postgres"],
    "audience": "executives",
    "time_range": "Q1 2024",
    "filters": [],
    "output_format": "dashboard",
    "acceptance_criteria": ["KPIs updated daily"],
    "clarifying_questions": [],
})


@pytest.fixture
def mock_router():
    router = MagicMock(spec=ModelRouter)
    router.complete.return_value = MOCK_REQUIREMENTS
    return router


def make_task(params: dict) -> AgentTask:
    return AgentTask(
        task_id=str(uuid.uuid4()),
        workflow_id=str(uuid.uuid4()),
        operation="parse",
        parameters=params,
    )


def test_requirements_agent_parses_request(mock_router):
    agent = RequirementsAgent(router=mock_router)
    task = make_task({"request": "Show me Q1 revenue and churn for the exec team"})
    result = agent.run(task)
    assert result.status == "success"
    assert "metrics" in result.results
    assert result.confidence_score > 0


def test_requirements_agent_returns_structured_output(mock_router):
    agent = RequirementsAgent(router=mock_router)
    task = make_task({"request": "Monthly active users by region"})
    result = agent.run(task)
    assert isinstance(result.results, dict)
    assert result.agent_name == "requirements"
