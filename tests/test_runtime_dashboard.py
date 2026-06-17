from __future__ import annotations

import asyncio
from collections import deque

from fastapi.testclient import TestClient

from api import gateway
from core.runtime import RuntimeMonitor


def test_runtime_monitor_records_traces_and_snapshots():
    monitor = RuntimeMonitor()
    messages: list[dict] = []
    monitor.register_listener(messages.append)

    monitor.start_workflow(workflow_id="wf-1", request="Build dashboard", user_id="user-1", channel="api")
    monitor.record_agent_trace(
        workflow_id="wf-1",
        agent_name="agent-a",
        kind="tool",
        tool="llm_request",
        stage="stage-1",
        task="run",
        input={"prompt": "hello"},
        output={"status": "ok"},
    )

    snapshot = monitor.snapshot()

    assert snapshot["summary"]["recent_traces"] == 1
    assert snapshot["recent_traces"][-1]["agent_name"] == "agent-a"
    assert messages[-1]["type"] == "agent_trace"
    assert messages[-1]["snapshot"]["summary"]["recent_traces"] == 1


def test_demo_workflow_can_seed_runtime_snapshot(monkeypatch):
    monitor = RuntimeMonitor()

    async def instant_sleep(_: float) -> None:
        return None

    asyncio.run(gateway.run_demo_workflow(monitor, sleep_fn=instant_sleep))

    snapshot = monitor.snapshot()

    assert snapshot["summary"]["recent_runs"] == 1
    assert snapshot["summary"]["recent_traces"] >= 1
    assert snapshot["task_board"]["total_cards"] >= 1
    assert snapshot["recent_runs"][0]["workflow_id"].startswith("demo-")


def test_dashboard_startup_auto_seeds_demo_workflow(monkeypatch):
    monitor = RuntimeMonitor()

    async def instant_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(gateway, "get_runtime_monitor", lambda: monitor)
    monkeypatch.setattr(gateway.asyncio, "sleep", instant_sleep)

    with TestClient(gateway.app) as client:
        response = client.get("/v1/dashboard")
        assert response.status_code == 200
        data = response.json()

    assert data["summary"]["recent_runs"] == 1
    assert data["summary"]["active_workflows"] == 0
    assert data["task_board"]["total_cards"] >= 1


def test_dashboard_api_includes_workflow_connections(monkeypatch):
    monitor = RuntimeMonitor()
    monkeypatch.setattr(gateway, "get_runtime_monitor", lambda: monitor)

    monitor.start_workflow(
        workflow_id="wf-dashboard-connections",
        request="Expose dashboard connections",
        user_id="user-api",
        channel="api",
    )

    with monitor.track_agent(
        workflow_id="wf-dashboard-connections",
        agent_name="planner",
        swarm="coordination",
        stage="01_planning",
        task="shape the plan",
    ):
        pass

    with monitor.track_agent(
        workflow_id="wf-dashboard-connections",
        agent_name="reviewer",
        swarm="quality",
        stage="02_review",
        task="review the plan",
    ):
        pass

    with TestClient(gateway.app) as client:
        response = client.get("/v1/dashboard")

    assert response.status_code == 200
    data = response.json()

    assert "workflow_connections" in data
    assert data["workflow_connections"]
    assert data["workflow_connections"][0]["workflow_id"] == "wf-dashboard-connections"
    assert data["workflow_connections"][0]["from_agent"] == "planner"
    assert data["workflow_connections"][0]["to_agent"] == "reviewer"


def test_dashboard_websocket_stream_pushes_updates(monkeypatch):
    monitor = RuntimeMonitor()
    monkeypatch.setattr(gateway, "get_runtime_monitor", lambda: monitor)

    client = TestClient(gateway.app)
    with client.websocket_connect("/v1/dashboard/stream") as websocket:
        first = websocket.receive_json()
        assert first["type"] == "snapshot"
        assert first["snapshot"]["summary"]["recent_traces"] == 0

        monitor.start_workflow(workflow_id="wf-2", request="Stream test", user_id="user-2", channel="api")
        update = websocket.receive_json()
        assert update["type"] == "workflow_started"
        assert update["snapshot"]["summary"]["active_workflows"] == 1


def test_runtime_snapshot_includes_mission_control_board():
    monitor = RuntimeMonitor()
    monitor.start_workflow(workflow_id="wf-board", request="Build mission control", user_id="user-3", channel="api")
    monitor.update_workflow(
        "wf-board",
        pipeline="sw_delivery",
        stage="pipeline:sw_delivery",
        status="running",
        intent="sw_delivery",
        risk_level="low",
        current_agent="architect",
        sub_goals=["board", "traces"],
    )
    with monitor.track_agent(
        workflow_id="wf-board",
        agent_name="architect",
        swarm="sw_eng",
        stage="02_architecture",
        task="design",
    ):
        pass

    snapshot = monitor.snapshot()
    board = snapshot["task_board"]

    assert [column["id"] for column in board["columns"]] == ["inbox", "assigned", "in_progress", "review", "done"]
    assert board["total_cards"] >= 1
    assert board["columns"][2]["cards"][0]["agent_name"] == "architect"
    assert board["columns"][2]["cards"][0]["workflow_id"] == "wf-board"


def test_runtime_snapshot_includes_workflow_connections():
    monitor = RuntimeMonitor()
    monitor.start_workflow(workflow_id="wf-chain", request="Build chained workflow", user_id="user-4", channel="api")

    with monitor.track_agent(
        workflow_id="wf-chain",
        agent_name="planner",
        swarm="coordination",
        stage="01_planning",
        task="shape the plan",
    ):
        pass

    with monitor.track_agent(
        workflow_id="wf-chain",
        agent_name="builder",
        swarm="delivery",
        stage="02_execution",
        task="execute the plan",
    ):
        pass

    snapshot = monitor.snapshot()
    connections = snapshot["workflow_connections"]

    assert connections
    assert connections[0]["workflow_id"] == "wf-chain"
    assert connections[0]["from_agent"] == "planner"
    assert connections[0]["to_agent"] == "builder"
    assert connections[0]["signal"] == "handoff"


def test_runtime_snapshot_excludes_workflow_connections_for_overlapping_agents():
    monitor = RuntimeMonitor()
    monitor.start_workflow(workflow_id="wf-overlap", request="Build overlapping workflow", user_id="user-5", channel="api")

    with monitor.track_agent(
        workflow_id="wf-overlap",
        agent_name="planner",
        swarm="coordination",
        stage="01_planning",
        task="shape the plan",
    ):
        with monitor.track_agent(
            workflow_id="wf-overlap",
            agent_name="builder",
            swarm="delivery",
            stage="02_execution",
            task="execute in parallel",
        ):
            pass

    snapshot = monitor.snapshot()

    assert snapshot["workflow_connections"] == []


def test_runtime_snapshot_does_not_create_false_handoff_when_overlap_start_ages_out():
    monitor = RuntimeMonitor()
    monitor._recent_events = deque(maxlen=6)
    monitor.start_workflow(
        workflow_id="wf-aged-overlap",
        request="Keep bounded history honest",
        user_id="user-5b",
        channel="api",
    )

    with monitor.track_agent(
        workflow_id="wf-aged-overlap",
        agent_name="builder",
        swarm="delivery",
        stage="02_execution",
        task="keep running",
    ):
        with monitor.track_agent(
            workflow_id="wf-aged-overlap",
            agent_name="planner",
            swarm="coordination",
            stage="01_planning",
            task="finish early",
        ):
            pass

        for step in range(4):
            monitor.record_agent_trace(
                workflow_id="wf-aged-overlap",
                agent_name="builder",
                kind="tool",
                tool=f"progress_{step}",
                stage="02_execution",
                task="keep running",
                output={"step": step},
            )

        with monitor.track_agent(
            workflow_id="wf-aged-overlap",
            agent_name="reviewer",
            swarm="qa",
            stage="03_review",
            task="join late",
        ):
            snapshot = monitor.snapshot()

    assert snapshot["workflow_connections"] == []


def test_task_board_keeps_agent_specific_traces_for_overlapping_agents():
    monitor = RuntimeMonitor()
    monitor.start_workflow(workflow_id="wf-parallel-traces", request="Trace isolation", user_id="user-6", channel="api")

    with monitor.track_agent(
        workflow_id="wf-parallel-traces",
        agent_name="planner",
        swarm="coordination",
        stage="01_planning",
        task="shape the plan",
    ):
        monitor.record_agent_trace(
            workflow_id="wf-parallel-traces",
            agent_name="planner",
            kind="tool",
            tool="plan_tool",
            stage="01_planning",
            task="shape the plan",
            output={"owner": "planner"},
        )
        with monitor.track_agent(
            workflow_id="wf-parallel-traces",
            agent_name="builder",
            swarm="delivery",
            stage="02_execution",
            task="build in parallel",
        ):
            monitor.record_agent_trace(
                workflow_id="wf-parallel-traces",
                agent_name="builder",
                kind="tool",
                tool="build_tool",
                stage="02_execution",
                task="build in parallel",
                output={"owner": "builder"},
            )

            snapshot = monitor.snapshot()

    in_progress_cards = snapshot["task_board"]["columns"][2]["cards"]
    cards_by_agent = {card["agent_name"]: card for card in in_progress_cards}

    assert cards_by_agent["planner"]["trace"]["tool"] == "plan_tool"
    assert cards_by_agent["planner"]["trace"]["output"] == "{\"owner\": \"planner\"}"
    assert cards_by_agent["builder"]["trace"]["tool"] == "build_tool"
    assert cards_by_agent["builder"]["trace"]["output"] == "{\"owner\": \"builder\"}"


def test_task_board_keeps_invocation_specific_traces_for_same_agent_name():
    monitor = RuntimeMonitor()
    monitor.start_workflow(workflow_id="wf-same-agent-traces", request="Invocation trace isolation", user_id="user-6b", channel="api")

    with monitor.track_agent(
        workflow_id="wf-same-agent-traces",
        agent_name="builder",
        swarm="delivery",
        stage="02_execution",
        task="implement feature",
    ):
        monitor.record_agent_trace(
            workflow_id="wf-same-agent-traces",
            agent_name="builder",
            kind="tool",
            tool="implement_tool",
            stage="02_execution",
            task="implement feature",
            output={"owner": "implement"},
        )
        with monitor.track_agent(
            workflow_id="wf-same-agent-traces",
            agent_name="builder",
            swarm="delivery",
            stage="03_validation",
            task="validate feature",
        ):
            monitor.record_agent_trace(
                workflow_id="wf-same-agent-traces",
                agent_name="builder",
                kind="tool",
                tool="validate_tool",
                stage="03_validation",
                task="validate feature",
                output={"owner": "validate"},
            )

            snapshot = monitor.snapshot()

    in_progress_cards = snapshot["task_board"]["columns"][2]["cards"]
    cards_by_invocation = {
        (card["agent_name"], card["stage"], card["task"]): card
        for card in in_progress_cards
    }

    implement_card = cards_by_invocation[("builder", "02_execution", "implement feature")]
    validate_card = cards_by_invocation[("builder", "03_validation", "validate feature")]

    assert implement_card["trace"]["tool"] == "implement_tool"
    assert implement_card["trace"]["output"] == "{\"owner\": \"implement\"}"
    assert validate_card["trace"]["tool"] == "validate_tool"
    assert validate_card["trace"]["output"] == "{\"owner\": \"validate\"}"


def test_task_board_falls_back_to_explicit_agent_trace_for_active_agent_outside_context():
    monitor = RuntimeMonitor()
    monitor.start_workflow(
        workflow_id="wf-explicit-trace-fallback",
        request="Explicit trace attribution",
        user_id="user-6c",
        channel="api",
    )

    with monitor.track_agent(
        workflow_id="wf-explicit-trace-fallback",
        agent_name="builder",
        swarm="delivery",
        stage="02_execution",
        task="build feature",
    ):
        with monitor.track_agent(
            workflow_id="wf-explicit-trace-fallback",
            agent_name="planner",
            swarm="coordination",
            stage="01_planning",
            task="review progress",
        ):
            monitor.record_agent_trace(
                workflow_id="wf-explicit-trace-fallback",
                agent_name="builder",
                kind="tool",
                tool="builder_tool",
                stage="02_execution",
                task="build feature",
                output={"owner": "builder"},
            )

            snapshot = monitor.snapshot()

    in_progress_cards = snapshot["task_board"]["columns"][2]["cards"]
    cards_by_agent = {card["agent_name"]: card for card in in_progress_cards}

    assert cards_by_agent["builder"]["trace"]["tool"] == "builder_tool"
    assert cards_by_agent["builder"]["trace"]["output"] == "{\"owner\": \"builder\"}"
    assert "trace" not in cards_by_agent["planner"]


def test_task_board_falls_back_to_explicit_model_call_for_active_agent_outside_context():
    monitor = RuntimeMonitor()
    monitor.start_workflow(
        workflow_id="wf-explicit-model-fallback",
        request="Explicit model attribution",
        user_id="user-6d",
        channel="api",
    )

    with monitor.track_agent(
        workflow_id="wf-explicit-model-fallback",
        agent_name="builder",
        swarm="delivery",
        stage="02_execution",
        task="build feature",
    ):
        with monitor.track_agent(
            workflow_id="wf-explicit-model-fallback",
            agent_name="planner",
            swarm="coordination",
            stage="01_planning",
            task="review progress",
        ):
            monitor.record_model_call(
                workflow_id="wf-explicit-model-fallback",
                agent_name="builder",
                model="gpt-test",
                input_tokens=10,
                output_tokens=5,
                cost_usd=0.12,
                latency_ms=45.0,
            )

            snapshot = monitor.snapshot()

    in_progress_cards = snapshot["task_board"]["columns"][2]["cards"]
    cards_by_agent = {card["agent_name"]: card for card in in_progress_cards}

    assert cards_by_agent["builder"]["trace"]["kind"] == "model_call"
    assert cards_by_agent["builder"]["trace"]["tool"] == "gpt-test"
    assert cards_by_agent["builder"]["trace"]["output"] == "5 output tokens · $0.12 · 45.0 ms"
    assert "trace" not in cards_by_agent["planner"]


def test_current_agent_remains_set_when_overlapping_agent_finishes():
    monitor = RuntimeMonitor()
    monitor.start_workflow(workflow_id="wf-current-agent", request="Keep current agent", user_id="user-7", channel="api")

    with monitor.track_agent(
        workflow_id="wf-current-agent",
        agent_name="planner",
        swarm="coordination",
        stage="01_planning",
        task="shape the plan",
    ):
        with monitor.track_agent(
            workflow_id="wf-current-agent",
            agent_name="builder",
            swarm="delivery",
            stage="02_execution",
            task="build in parallel",
        ):
            pass

        snapshot = monitor.snapshot()

    run = snapshot["active_workflows"][0]

    assert run["current_agent"] == "planner"
    assert snapshot["task_board"]["columns"][2]["cards"][0]["agent_name"] == "planner"


def test_identical_overlapping_agent_invocations_remain_distinct():
    monitor = RuntimeMonitor()
    monitor.start_workflow(workflow_id="wf-identical-overlap", request="Duplicate agent invocations", user_id="user-8", channel="api")

    with monitor.track_agent(
        workflow_id="wf-identical-overlap",
        agent_name="builder",
        swarm="delivery",
        stage="02_execution",
        task="build in parallel",
    ):
        with monitor.track_agent(
            workflow_id="wf-identical-overlap",
            agent_name="builder",
            swarm="delivery",
            stage="02_execution",
            task="build in parallel",
        ):
            snapshot = monitor.snapshot()

    identical_agents = [
        agent for agent in snapshot["active_agents"]
        if agent["workflow_id"] == "wf-identical-overlap"
        and agent["agent_name"] == "builder"
        and agent["stage"] == "02_execution"
        and agent["task"] == "build in parallel"
    ]

    assert len(identical_agents) == 2
    assert snapshot["summary"]["active_agents"] == 2
