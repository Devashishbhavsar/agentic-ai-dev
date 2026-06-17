# Mission Control Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the existing dashboard into a mission-board-first interface with visible live agent handoffs and stronger empty/live state behavior.

**Architecture:** Keep the current FastAPI + plain React dashboard bundle, but push more dashboard-specific derived state into the runtime snapshot and simplify the frontend around mission-board primitives. Use derived communication edges rather than inventing a new persistence model.

**Tech Stack:** FastAPI, Python runtime monitor, React without JSX source authoring changes, CSS, pytest, Node bundle build

---

## File Structure

- Modify: `core/runtime.py`
  Purpose: derive workflow connection edges and expose them in the dashboard snapshot.
- Modify: `tests/test_runtime_dashboard.py`
  Purpose: verify connection payloads and mission-board state.
- Modify: `web/dashboard/app.js`
  Purpose: replace the oversized hero and static panels with a mission-board-first rendering and communication visuals.
- Modify: `web/dashboard/styles.css`
  Purpose: restyle the shell, mission board, communication layer, and empty state.

---

### Task 1: Add Derived Workflow Connections To Runtime Snapshot

**Files:**
- Modify: `core/runtime.py`
- Test: `tests/test_runtime_dashboard.py`

- [ ] **Step 1: Write the failing test**

Add a new test to `tests/test_runtime_dashboard.py`:

```python
def test_runtime_snapshot_includes_workflow_connections():
    monitor = RuntimeMonitor()
    monitor.start_workflow(workflow_id="wf-links", request="Show agent links", user_id="user-1", channel="api")
    with monitor.track_agent(
        workflow_id="wf-links",
        agent_name="planner",
        swarm="coordination",
        stage="01_plan",
        task="plan",
        model="anthropic/claude-sonnet-4-5",
    ):
        pass
    with monitor.track_agent(
        workflow_id="wf-links",
        agent_name="builder",
        swarm="delivery",
        stage="02_build",
        task="build",
        model="openai/gpt-4.1",
    ):
        pass

    snapshot = monitor.snapshot()

    assert snapshot["workflow_connections"]
    assert snapshot["workflow_connections"][0]["workflow_id"] == "wf-links"
    assert snapshot["workflow_connections"][0]["from_agent"] == "planner"
    assert snapshot["workflow_connections"][0]["to_agent"] == "builder"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/dev1029/openclaw-enterprise-agent/.venv/bin/python -m pytest tests/test_runtime_dashboard.py::test_runtime_snapshot_includes_workflow_connections -q`

Expected: `FAIL` with missing `workflow_connections` in the snapshot.

- [ ] **Step 3: Write minimal implementation**

Add a helper in `core/runtime.py` that derives ordered handoffs from recent workflow events:

```python
def _build_workflow_connections(recent_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    workflow_events: dict[str, list[dict[str, Any]]] = {}
    for event in recent_events:
        workflow_id = event.get("workflow_id", "")
        if workflow_id:
            workflow_events.setdefault(workflow_id, []).append(event)

    connections: list[dict[str, Any]] = []
    for workflow_id, events in workflow_events.items():
        agent_starts = [event for event in events if event.get("type") == "agent_started" and event.get("agent_name")]
        for previous, current in zip(agent_starts, agent_starts[1:]):
            if previous.get("agent_name") == current.get("agent_name"):
                continue
            connections.append({
                "workflow_id": workflow_id,
                "from_agent": previous.get("agent_name", ""),
                "to_agent": current.get("agent_name", ""),
                "signal": "handoff",
                "timestamp": current.get("timestamp", ""),
                "status": "recent",
            })
    return connections[-24:]
```

Then include it in `_snapshot_locked()`:

```python
workflow_connections = _build_workflow_connections(recent_events)
...
"workflow_connections": workflow_connections,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/home/dev1029/openclaw-enterprise-agent/.venv/bin/python -m pytest tests/test_runtime_dashboard.py::test_runtime_snapshot_includes_workflow_connections -q`

Expected: `PASS`

- [ ] **Step 5: Commit**

```bash
git add core/runtime.py tests/test_runtime_dashboard.py
git commit -m "feat: expose workflow connections in runtime snapshot"
```

---

### Task 2: Redesign The Dashboard Shell Around A Mission Board

**Files:**
- Modify: `web/dashboard/app.js`
- Test: `tests/test_runtime_dashboard.py`

- [ ] **Step 1: Write the failing test**

Extend the API-facing dashboard test with a payload check:

```python
def test_dashboard_api_includes_workflow_connections(monkeypatch):
    monitor = RuntimeMonitor()
    monitor.start_workflow(workflow_id="wf-api", request="API payload", user_id="user-2", channel="api")
    with monitor.track_agent(
        workflow_id="wf-api",
        agent_name="planner",
        swarm="coordination",
        stage="01_plan",
        task="plan",
    ):
        pass
    with monitor.track_agent(
        workflow_id="wf-api",
        agent_name="reviewer",
        swarm="quality",
        stage="02_review",
        task="review",
    ):
        pass

    monkeypatch.setattr(gateway, "get_runtime_monitor", lambda: monitor)
    client = TestClient(gateway.app)
    response = client.get("/v1/dashboard")
    data = response.json()

    assert "workflow_connections" in data
    assert data["workflow_connections"][0]["to_agent"] == "reviewer"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/dev1029/openclaw-enterprise-agent/.venv/bin/python -m pytest tests/test_runtime_dashboard.py::test_dashboard_api_includes_workflow_connections -q`

Expected: `FAIL` because `/v1/dashboard` does not yet include `workflow_connections`.

- [ ] **Step 3: Write minimal implementation**

Expose the new payload from `api/gateway.py`:

```python
"workflow_connections": runtime.get("workflow_connections", []),
```

In `web/dashboard/app.js`, remove the oversized editorial hero priority and replace it with:

- compact command header
- left system rail
- mission board as first large section
- selected workflow conversation ledger in the right rail

At minimum, add helper functions and render blocks like:

```javascript
function buildConversationLedger(workflowId, connections) {
  return (connections || [])
    .filter((row) => row.workflow_id === workflowId)
    .slice(-8)
    .reverse();
}
```

and:

```javascript
const workflowConnections = data?.workflow_connections || [];
const selectedConversation = selectedWorkflow
  ? buildConversationLedger(selectedWorkflow.workflow_id, workflowConnections)
  : [];
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/home/dev1029/openclaw-enterprise-agent/.venv/bin/python -m pytest tests/test_runtime_dashboard.py::test_dashboard_api_includes_workflow_connections -q`

Expected: `PASS`

- [ ] **Step 5: Commit**

```bash
git add api/gateway.py web/dashboard/app.js tests/test_runtime_dashboard.py
git commit -m "feat: wire mission board payload into dashboard api"
```

---

### Task 3: Add Visible Agent Handoff Components

**Files:**
- Modify: `web/dashboard/app.js`
- Modify: `web/dashboard/styles.css`

- [ ] **Step 1: Write the failing UI verification**

Run the frontend checks before implementation:

Run: `node --check web/dashboard/app.js`

Expected: `PASS` before changes, establishing the current syntax baseline.

- [ ] **Step 2: Implement communication-focused components**

Add render helpers in `web/dashboard/app.js`:

```javascript
function ConversationLedger({ workflow, connections }) {
  const rows = (connections || []).filter((row) => row.workflow_id === workflow.workflow_id).slice(-8).reverse();
  return React.createElement(
    "article",
    { className: "panel conversation-panel" },
    React.createElement("h3", null, "Agent Signals"),
    React.createElement(
      "div",
      { className: "conversation-list" },
      rows.length
        ? rows.map((row, index) => React.createElement(
            "div",
            { className: "conversation-item", key: `${row.timestamp}-${index}` },
            React.createElement("div", { className: "conversation-flow" }, `${row.from_agent} -> ${row.to_agent}`),
            React.createElement("div", { className: "conversation-meta" }, `${row.signal} · ${formatTime(row.timestamp)}`)
          ))
        : React.createElement("div", { className: "muted" }, "No agent handoffs visible yet.")
    )
  );
}
```

Also extend board cards with recency and activity treatment:

```javascript
const isHot = card.status === "running" || card.status === "active";
className: `board-card ${selected ? "selected" : ""} ${isHot ? "hot" : ""}`
```

- [ ] **Step 3: Implement the supporting CSS**

Add CSS for:

```css
.board-card.hot {
  box-shadow: 0 0 0 1px rgba(99,214,255,0.28), 0 24px 48px rgba(17, 35, 72, 0.32);
}

.board-card.hot::after {
  content: "";
  position: absolute;
  inset: auto 14px 14px 14px;
  height: 2px;
  border-radius: 999px;
  background: linear-gradient(90deg, transparent, var(--cyan), transparent);
  animation: sweep 1.6s linear infinite;
}

.conversation-list {
  display: grid;
  gap: 10px;
}

.conversation-item {
  border: 1px solid rgba(255,255,255,0.08);
  background: rgba(255,255,255,0.03);
  border-radius: 16px;
  padding: 12px;
}
```

and:

```css
@keyframes sweep {
  0% { transform: translateX(-18%); opacity: 0.15; }
  50% { transform: translateX(18%); opacity: 1; }
  100% { transform: translateX(36%); opacity: 0.15; }
}
```

- [ ] **Step 4: Run frontend verification**

Run:

- `node --check web/dashboard/app.js`
- `npm run build:dashboard`

Expected: both commands succeed.

- [ ] **Step 5: Commit**

```bash
git add web/dashboard/app.js web/dashboard/styles.css
git commit -m "feat: add visible agent handoff components to dashboard"
```

---

### Task 4: Rework Empty State And Live-State Hierarchy

**Files:**
- Modify: `web/dashboard/app.js`
- Modify: `web/dashboard/styles.css`

- [ ] **Step 1: Write the failing expectation**

Use the existing empty-state condition in `web/dashboard/app.js` as the target and verify the bundle still builds after replacing it.

Run: `npm run build:dashboard`

Expected: current build succeeds before the redesign.

- [ ] **Step 2: Replace the empty-state block with a dormant mission board**

Swap the static empty panel for a dormant board-oriented state:

```javascript
function EmptyMissionState({ streamState, updatedAt }) {
  return React.createElement(
    "section",
    { className: "panel empty-mission" },
    React.createElement("div", { className: "empty-mission-head" },
      React.createElement("div", null,
        React.createElement("div", { className: "label" }, "System armed"),
        React.createElement("h3", null, "Waiting for the next workflow")
      ),
      React.createElement("span", { className: `pill ${streamState === "live" ? "good" : "warn"}` }, streamState)
    ),
    React.createElement("div", { className: "empty-lanes" },
      ["Inbox", "Assigned", "In Progress", "Review", "Done"].map((lane) =>
        React.createElement("div", { className: "empty-lane", key: lane }, lane)
      )
    ),
    React.createElement("div", { className: "muted" }, `Live stream ${streamState} · Updated ${formatTime(updatedAt)}`)
  );
}
```

- [ ] **Step 3: Add CSS for the dormant board state**

Add:

```css
.empty-mission {
  display: grid;
  gap: 18px;
}

.empty-lanes {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
}

.empty-lane {
  min-height: 132px;
  border-radius: 18px;
  border: 1px dashed rgba(99,214,255,0.18);
  background: linear-gradient(180deg, rgba(99,214,255,0.05), rgba(255,255,255,0.02));
  display: grid;
  place-items: center;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.16em;
  font-size: 11px;
}
```

- [ ] **Step 4: Run verification**

Run:

- `node --check web/dashboard/app.js`
- `npm run build:dashboard`

Expected: both commands succeed with the new empty state.

- [ ] **Step 5: Commit**

```bash
git add web/dashboard/app.js web/dashboard/styles.css
git commit -m "feat: redesign dashboard empty state for mission control"
```

---

### Task 5: Final Verification

**Files:**
- Verify only

- [ ] **Step 1: Run runtime dashboard tests**

Run: `/home/dev1029/openclaw-enterprise-agent/.venv/bin/python -m pytest tests/test_runtime_dashboard.py -q`

Expected: all dashboard tests pass.

- [ ] **Step 2: Run bundle and syntax checks**

Run:

- `node --check web/dashboard/app.js`
- `npm run build:dashboard`
- `python3 -m py_compile api/gateway.py core/runtime.py`

Expected: all commands succeed without syntax errors.

- [ ] **Step 3: Manual browser verification**

Open `/dashboard` and confirm:

- the mission board is the dominant surface
- active cards show visible “working” treatment
- the selected workflow shows agent handoffs in the right rail
- the empty state looks intentional when there is no active work

- [ ] **Step 4: Commit**

```bash
git add core/runtime.py api/gateway.py web/dashboard/app.js web/dashboard/styles.css tests/test_runtime_dashboard.py
git commit -m "feat: ship mission control dashboard redesign"
```
