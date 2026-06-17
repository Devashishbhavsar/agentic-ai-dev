import React, { useEffect, useMemo, useState, useCallback, startTransition } from "react";
import { createRoot } from "react-dom/client";

// ── WebSocket / data hook ─────────────────────────────────────────────────────

const WS_RETRY_BASE = 1200;
const WS_RETRY_MAX  = 8000;

function useDashboard() {
  const [state, setState] = useState({
    loading: true, data: null, error: null, updatedAt: null, streamState: "connecting",
  });

  useEffect(() => {
    let alive = true;
    let socket = null;
    let retryTimer = null;
    let retryDelay = WS_RETRY_BASE;

    const applySnapshot = (payload) => {
      if (!alive) return;
      const snap = payload?.snapshot || payload;
      startTransition(() => {
        setState((prev) => ({
          ...prev,
          loading: false, error: null,
          data: snap,
          updatedAt: snap?.generated_at || new Date().toISOString(),
          streamState: payload?.type === "snapshot" ? prev.streamState : "live",
        }));
      });
    };

    const loadInitial = async () => {
      try {
        const r = await fetch("/v1/dashboard", { cache: "no-store" });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const d = await r.json();
        if (alive) applySnapshot({ type: "snapshot", snapshot: d });
      } catch (err) {
        if (alive) setState((p) => ({ ...p, loading: false, error: err.message || String(err), streamState: "degraded" }));
      }
    };

    const connect = () => {
      if (!alive || typeof window.WebSocket === "undefined") {
        setState((p) => ({ ...p, streamState: "degraded" }));
        return;
      }
      const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
      socket = new WebSocket(`${proto}//${window.location.host}/v1/dashboard/stream`);
      setState((p) => ({ ...p, streamState: "connecting" }));
      socket.onopen  = () => { retryDelay = WS_RETRY_BASE; if (alive) setState((p) => ({ ...p, streamState: "live" })); };
      socket.onmessage = (e) => {
        if (!alive) return;
        try { const m = JSON.parse(e.data); if (m && (m.snapshot || m.type === "snapshot")) applySnapshot(m); } catch { /* ignore */ }
      };
      socket.onerror = () => { if (alive) setState((p) => ({ ...p, streamState: "degraded" })); };
      socket.onclose = () => {
        if (!alive) return;
        setState((p) => ({ ...p, streamState: "reconnecting" }));
        retryTimer = window.setTimeout(connect, retryDelay);
        retryDelay = Math.min(retryDelay * 1.6, WS_RETRY_MAX);
      };
    };

    loadInitial().then(() => { if (alive) connect(); });
    return () => {
      alive = false;
      if (retryTimer) window.clearTimeout(retryTimer);
      if (socket) socket.close();
    };
  }, []);

  return state;
}

// ── Formatters ────────────────────────────────────────────────────────────────

function fmt(v, digits = 0) {
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: digits, minimumFractionDigits: digits,
  }).format(Number(v || 0));
}

function fmtTime(v) {
  if (!v) return "—";
  try { return new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit", second: "2-digit" }).format(new Date(v)); }
  catch { return v; }
}

function fmtDate(v) {
  if (!v) return "—";
  try { return new Intl.DateTimeFormat("en-US", { month: "short", day: "2-digit", hour: "numeric", minute: "2-digit" }).format(new Date(v)); }
  catch { return v; }
}

function fmtDur(ms) {
  if (ms == null) return "—";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function statusTone(status) {
  const v = String(status || "").toLowerCase();
  if (["success", "running", "healthy", "done", "active"].includes(v)) return "green";
  if (["pending_approval", "degraded", "partial", "reconnecting"].includes(v)) return "amber";
  if (["failure", "failed", "down"].includes(v)) return "red";
  return "cyan";
}

function agentKey(a) { return `${a.workflow_id}:${a.agent_name}:${a.stage}:${a.task}`; }

function clip(v, len = 200) {
  if (!v) return "";
  let s;
  try { s = typeof v === "string" ? v : JSON.stringify(v); } catch { s = String(v); }
  return s.length > len ? s.slice(0, len - 1) + "…" : s;
}

// ── Sparkline ─────────────────────────────────────────────────────────────────

function makePath(vals, W = 80, H = 28, pad = 2, bot = 2) {
  const pts = (Array.isArray(vals) ? vals : []).filter((v) => Number.isFinite(Number(v))).map(Number);
  if (!pts.length) return { line: `M${pad} ${H/2} L${W-pad} ${H/2}`, fill: `M${pad} ${H/2} L${W-pad} ${H/2} L${W-pad} ${H-bot} L${pad} ${H-bot}Z` };
  const mx = Math.max(...pts), mn = Math.min(...pts), rng = Math.max(1, mx - mn);
  const step = pts.length === 1 ? 0 : (W - pad * 2) / (pts.length - 1);
  const coords = pts.map((v, i) => [pad + i * step, H - bot - ((v - mn) / rng) * (H - pad * 2 - bot)]);
  const line = coords.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`).join(" ");
  return { line, fill: `${line} L${W-pad} ${H-bot} L${pad} ${H-bot}Z` };
}

function Spark({ values, color }) {
  const p = useMemo(() => makePath(values, 80, 28, 2, 2), [values]);
  return React.createElement(
    "svg",
    { viewBox: "0 0 80 28", preserveAspectRatio: "none", style: { width: "100%", height: 28, display: "block", marginTop: 8 } },
    React.createElement("path", { d: p.fill, fill: `${color}18` }),
    React.createElement("path", { d: p.line, fill: "none", stroke: color, strokeWidth: "1.8", strokeLinecap: "round", strokeLinejoin: "round" })
  );
}

// ── Primitives ────────────────────────────────────────────────────────────────

function Dot({ state }) {
  return React.createElement("span", { className: `dot dot--${state}` });
}

function Badge({ tone = "cyan", children }) {
  return React.createElement("span", { className: `badge badge--${tone}` }, children);
}

// ── KPI Card ─────────────────────────────────────────────────────────────────

const TONE_COLORS = { cyan: "#63d6ff", green: "#57e3a0", amber: "#ffce73", red: "#ff6b6b" };

function KpiCard({ label, value, sub, t = "cyan", spark }) {
  return React.createElement(
    "div",
    { className: `kpi-card kpi-card--${t}` },
    React.createElement("div", { className: "kpi-card__header" },
      React.createElement("span", { className: "kpi-card__label" }, label),
      React.createElement(Badge, { tone: t }, t === "green" ? "live" : t === "amber" ? "warn" : t === "red" ? "alert" : "info")
    ),
    React.createElement("div", { className: "kpi-card__value" }, value),
    spark && spark.length > 1 && React.createElement(Spark, { values: spark, color: TONE_COLORS[t] || "#63d6ff" }),
    sub && React.createElement("div", { className: "kpi-card__sub" }, sub)
  );
}

// ── Sidebar ───────────────────────────────────────────────────────────────────

function Sidebar({ streamState, updatedAt, sections, onJump, alerts, onDemo, demoStatus }) {
  return React.createElement(
    "aside",
    { className: "sidebar" },
    React.createElement("div", { className: "sidebar__brand" },
      React.createElement("div", { className: "sidebar__eyebrow" }, "OpenClaw / Control Plane"),
      React.createElement("h1", { className: "sidebar__title" }, "Command Center")
    ),
    React.createElement("div", { className: "sidebar__stream" },
      React.createElement(Dot, { state: streamState }),
      React.createElement("div", { className: "sidebar__stream-info" },
        React.createElement("strong", null,
          streamState === "live" ? "Live stream" :
          streamState === "reconnecting" ? "Reconnecting" :
          streamState === "connecting"   ? "Connecting" : "Degraded"
        ),
        React.createElement("span", null, `Updated ${fmtTime(updatedAt)}`)
      )
    ),
    React.createElement("nav", { className: "sidebar__nav" },
      sections.map((s) => React.createElement(
        "button",
        { key: s.id, type: "button", className: `sidebar__nav-item${s.active ? " is-active" : ""}`, onClick: () => onJump(s.id) },
        React.createElement("span", null, s.label),
        s.count > 0 && React.createElement("span", { className: "sidebar__nav-count" }, s.count)
      ))
    ),
    alerts.length > 0 && React.createElement("div", { className: "sidebar__alerts" },
      React.createElement("div", { className: "sidebar__section-label" }, "Alerts"),
      alerts.map((a, i) => React.createElement(
        "div",
        { key: i, className: `sidebar__alert sidebar__alert--${a.tone || "cyan"}` },
        React.createElement("strong", null, a.title),
        React.createElement("span", null, a.body)
      ))
    ),
    React.createElement("div", { className: "sidebar__footer" },
      React.createElement("button", { type: "button", className: "btn-demo", onClick: onDemo, disabled: demoStatus === "starting" },
        demoStatus === "starting" ? "Launching…" : "Launch demo workflow"
      ),
      React.createElement("p", { className: "sidebar__demo-hint" },
        demoStatus === "idle" ? "Spin up a synthetic run with parallel agents." : clip(demoStatus, 52)
      )
    )
  );
}

// ── Mission Board ─────────────────────────────────────────────────────────────

function MissionBoard({ board, query, setQuery, selectedWorkflowId, onSelectWorkflow }) {
  const q = String(query || "").trim().toLowerCase();
  const columns = (board?.columns || []).map((col) => ({
    ...col,
    cards: (col.cards || []).filter((c) => {
      if (!q) return true;
      return [c.title, c.agent_name, c.stage, c.task, c.pipeline, c.status, c.summary]
        .filter(Boolean).join(" ").toLowerCase().includes(q);
    }),
  }));

  return React.createElement(
    "div",
    { className: "board" },
    React.createElement("div", { className: "board__header" },
      React.createElement("div", { className: "board__title-row" },
        React.createElement("h2", { className: "board__title" }, "Mission Board"),
        React.createElement(Badge, { tone: "cyan" }, `${board?.total_cards || 0} cards`)
      ),
      React.createElement("input", {
        type: "search", className: "board__search",
        value: query, onChange: (e) => setQuery(e.target.value),
        placeholder: "Filter by agent, stage, or pipeline…",
        "aria-label": "Filter board",
      })
    ),
    React.createElement("div", { className: "board__grid" },
      columns.map((col) => React.createElement(
        "div",
        { key: col.id, className: "board__col" },
        React.createElement("div", { className: "board__col-head" },
          React.createElement("span", { className: "board__col-label" }, col.label),
          React.createElement("span", { className: "board__col-count" }, col.cards.length)
        ),
        col.cards.length
          ? col.cards.map((card) => {
              const sel = selectedWorkflowId === card.workflow_id;
              const hot = card.status === "running" || card.status === "active";
              return React.createElement(
                "button",
                {
                  key: `${col.id}:${card.workflow_id}:${card.agent_name}:${card.stage}`,
                  type: "button",
                  className: `board__card${sel ? " is-selected" : ""}${hot ? " is-hot" : ""}`,
                  onClick: () => onSelectWorkflow(card.workflow_id),
                },
                React.createElement("div", { className: "board__card-top" },
                  React.createElement("code", { className: "board__card-agent" }, card.agent_name || card.workflow_id?.slice(0, 8)),
                  React.createElement(Badge, { tone: statusTone(card.status) }, card.status || "—")
                ),
                React.createElement("div", { className: "board__card-name" }, card.title || card.workflow_id),
                React.createElement("div", { className: "board__card-meta" },
                  `${card.stage || "—"} · ${card.pipeline || "—"} · ${fmtDur(card.duration_ms)}`
                ),
                card.approval_required && React.createElement("div", { className: "board__card-flag" }, "⚑ Approval required"),
                card.summary && React.createElement("div", { className: "board__card-summary" }, clip(card.summary, 72))
              );
            })
          : React.createElement("div", { className: "board__col-empty" }, "Empty")
      ))
    )
  );
}

// ── Workflow Drilldown ────────────────────────────────────────────────────────

function WorkflowDrilldown({ workflow, agents, events, traces, onSelectAgent, selectedAgentKey }) {
  if (!workflow) {
    return React.createElement(
      "div",
      { className: "drilldown drilldown--empty" },
      React.createElement("div", { className: "drilldown__empty-icon" }, "⊙"),
      React.createElement("p", null, "Select a workflow card to inspect its agents, traces, and events.")
    );
  }

  const wfAgents = agents.filter((a) => a.workflow_id === workflow.workflow_id);
  const wfEvents = events.filter((e) => e.workflow_id === workflow.workflow_id);
  const agMap    = wfAgents.reduce((acc, a) => { acc[agentKey(a)] = a; return acc; }, {});
  const selAgent = agMap[selectedAgentKey] || wfAgents[0] || null;
  const wfTraces = selAgent
    ? traces.filter((t) => t.workflow_id === workflow.workflow_id && t.agent_name === selAgent.agent_name).slice(-5)
    : [];

  return React.createElement(
    "div",
    { className: "drilldown" },
    React.createElement("div", { className: "drilldown__header" },
      React.createElement("div", { className: "drilldown__wf-name" }, clip(workflow.request || workflow.workflow_id, 64)),
      React.createElement(Badge, { tone: statusTone(workflow.status) }, workflow.status || "—")
    ),
    React.createElement("div", { className: "drilldown__meta" },
      `${workflow.pipeline || "—"} · ${workflow.stage || "—"} · ${fmtDur(workflow.duration_ms)}`
    ),

    wfAgents.length > 0 && React.createElement("div", { className: "drilldown__section" },
      React.createElement("div", { className: "drilldown__section-label" }, `Active agents (${wfAgents.length})`),
      wfAgents.map((a) => {
        const k = agentKey(a);
        return React.createElement(
          "button",
          {
            key: k, type: "button",
            className: `drilldown__agent${k === selectedAgentKey ? " is-selected" : ""}`,
            onClick: () => onSelectAgent(k),
          },
          React.createElement("div", { className: "drilldown__agent-row" },
            React.createElement("code", null, a.agent_name),
            React.createElement(Badge, { tone: statusTone(a.status) }, a.status || "running")
          ),
          React.createElement("div", { className: "drilldown__agent-meta" },
            `${a.stage} · ${a.swarm} · ${fmtDur(a.duration_ms)}`
          )
        );
      })
    ),

    wfTraces.length > 0 && React.createElement("div", { className: "drilldown__section" },
      React.createElement("div", { className: "drilldown__section-label" }, `Trace · ${selAgent.agent_name}`),
      wfTraces.map((t, i) => React.createElement(
        "details",
        { key: `${t.timestamp}-${i}`, className: "drilldown__trace" },
        React.createElement("summary", { className: "drilldown__trace-summary" },
          React.createElement("code", null, `${t.kind} · ${t.tool || t.model || "—"}`),
          React.createElement("span", null, fmtDate(t.timestamp))
        ),
        t.output && React.createElement("pre", { className: "drilldown__trace-body" }, clip(t.output, 280))
      ))
    ),

    wfEvents.length > 0 && React.createElement("div", { className: "drilldown__section" },
      React.createElement("div", { className: "drilldown__section-label" }, `Events (${wfEvents.length})`),
      wfEvents.slice(-8).reverse().map((ev, i) => React.createElement(
        "div",
        { key: `${ev.timestamp}-${i}`, className: "drilldown__event" },
        React.createElement("code", null, ev.type),
        React.createElement("span", null, `${ev.agent_name || "—"} · ${ev.stage || ev.status || ""}`),
        React.createElement("span", null, fmtTime(ev.timestamp))
      ))
    )
  );
}

// ── Agent Signals ─────────────────────────────────────────────────────────────

function AgentSignals({ workflow, connections }) {
  const rows = workflow
    ? (connections || []).filter((c) => c.workflow_id === workflow.workflow_id).slice(-8).reverse()
    : [];

  return React.createElement(
    "div",
    { className: "signals" },
    React.createElement("div", { className: "signals__header" }, "Agent Signals"),
    rows.length
      ? rows.map((r, i) => React.createElement(
          "div",
          { key: `${r.timestamp}-${i}`, className: "signals__item" },
          React.createElement("div", { className: "signals__flow" },
            React.createElement("code", null, r.from_agent || "—"),
            React.createElement("span", { className: "signals__arrow" }, "→"),
            React.createElement("code", null, r.to_agent || "—")
          ),
          React.createElement("div", { className: "signals__meta" },
            `${r.signal || "handoff"} · ${fmtTime(r.timestamp)}`
          )
        ))
      : React.createElement("div", { className: "signals__empty" },
          workflow ? "No agent handoffs recorded yet." : "Select a workflow to see handoffs."
        )
  );
}

// ── Model Usage ───────────────────────────────────────────────────────────────

function ModelUsage({ modelUsage }) {
  const rows = Object.entries(modelUsage || {}).sort((a, b) => (b[1]?.calls || 0) - (a[1]?.calls || 0));
  const maxCalls = Math.max(1, ...rows.map(([, v]) => v?.calls || 0));

  return React.createElement(
    "div",
    { className: "model-usage" },
    React.createElement("div", { className: "model-usage__header" }, "Model Pressure"),
    rows.length
      ? rows.map(([model, d]) => React.createElement(
          "div",
          { key: model, className: "model-usage__row" },
          React.createElement("div", { className: "model-usage__name" },
            React.createElement("code", null, model.split("/").pop()),
            React.createElement("span", null, `${d.calls} calls`)
          ),
          React.createElement("div", { className: "model-usage__bar-track" },
            React.createElement("div", {
              className: "model-usage__bar-fill",
              style: { width: `${Math.max(4, (d.calls / maxCalls) * 100)}%` },
            })
          ),
          React.createElement("div", { className: "model-usage__cost" },
            `$${fmt(d.cost_usd, 4)} · ${fmt(d.avg_latency_ms, 0)}ms avg`
          )
        ))
      : React.createElement("div", { className: "model-usage__empty" }, "No model activity yet.")
  );
}

// ── Event Stream ──────────────────────────────────────────────────────────────

function EventStream({ events }) {
  return React.createElement(
    "div",
    { className: "event-stream" },
    React.createElement("div", { className: "event-stream__header" }, "Event Stream"),
    events.length
      ? events.slice(-10).reverse().map((ev, i) => React.createElement(
          "div",
          { key: `${ev.timestamp}-${i}`, className: "event-stream__item" },
          React.createElement("code", {
            className: `event-stream__type event-stream__type--${
              ev.type?.includes("failed") ? "red" : ev.type?.includes("finished") || ev.type?.includes("success") ? "green" : "cyan"
            }`,
          }, ev.type),
          React.createElement("span", null,
            ev.agent_name ? `${ev.agent_name}${ev.stage ? " · " + ev.stage : ""}` : ev.request || ev.status || ""
          ),
          React.createElement("span", { className: "event-stream__time" }, fmtTime(ev.timestamp))
        ))
      : React.createElement("div", { className: "event-stream__empty" }, "No events recorded yet.")
  );
}

// ── Mini Chart ────────────────────────────────────────────────────────────────

function MiniChart({ title, values, color, unit }) {
  const pts = (values || []).filter((v) => Number.isFinite(Number(v))).map(Number);
  const p   = useMemo(() => makePath(pts, 360, 60, 8, 6), [pts.join(",")]);
  const mx  = pts.length ? Math.max(...pts) : 0;
  const mn  = pts.length ? Math.min(...pts) : 0;

  return React.createElement(
    "div",
    { className: "mini-chart" },
    React.createElement("div", { className: "mini-chart__header" },
      React.createElement("span", { className: "mini-chart__title" }, title),
      React.createElement("span", { className: "mini-chart__range" }, `${fmt(mn, 1)} – ${fmt(mx, 1)} ${unit}`)
    ),
    React.createElement(
      "svg",
      { viewBox: "0 0 360 60", preserveAspectRatio: "none", className: "mini-chart__svg" },
      React.createElement("path", { d: p.fill, fill: `${color}18` }),
      React.createElement("path", { d: p.line, fill: "none", stroke: color, strokeWidth: "2", strokeLinecap: "round", strokeLinejoin: "round" })
    )
  );
}

// ── History ───────────────────────────────────────────────────────────────────

function History({ runs, activeAgents, onSelectWorkflow }) {
  return React.createElement(
    "div",
    { className: "history" },
    React.createElement("h3", { className: "history__title" }, "Run History"),
    runs.length
      ? runs.map((r) => React.createElement(
          "button",
          {
            key: r.workflow_id, type: "button", className: "history__item",
            onClick: () => {
              const ag = activeAgents.find((a) => a.workflow_id === r.workflow_id);
              onSelectWorkflow(r.workflow_id, ag ? agentKey(ag) : "");
            },
          },
          React.createElement("div", { className: "history__item-row" },
            React.createElement("code", { className: "history__pipeline" }, r.pipeline || "unknown"),
            React.createElement(Badge, { tone: statusTone(r.status) }, r.status),
            r.approval_required && React.createElement(Badge, { tone: "amber" }, "approval")
          ),
          React.createElement("div", { className: "history__request" },
            clip(r.request || r.summary || r.workflow_id, 96)
          ),
          React.createElement("div", { className: "history__meta" },
            `${fmtDur(r.duration_ms)} · ${r.stage || "finished"} · ${fmtDate(r.finished_at)}`
          )
        ))
      : React.createElement("div", { className: "history__empty" }, "No completed runs yet.")
  );
}

// ── Empty Mission State ───────────────────────────────────────────────────────

function EmptyMissionState({ streamState, updatedAt }) {
  return React.createElement(
    "div",
    { className: "empty-mission" },
    React.createElement("div", { className: "empty-mission__header" },
      React.createElement("div", null,
        React.createElement("div", { className: "empty-mission__label" }, "System armed"),
        React.createElement("h3", { className: "empty-mission__title" }, "Waiting for the first workflow")
      ),
      React.createElement(Badge, { tone: streamState === "live" ? "green" : "amber" }, streamState)
    ),
    React.createElement("div", { className: "empty-mission__lanes" },
      ["Inbox", "Assigned", "In Progress", "Review", "Done"].map((lane) =>
        React.createElement("div", { key: lane, className: "empty-mission__lane" },
          React.createElement("span", null, lane)
        )
      )
    ),
    React.createElement("p", { className: "empty-mission__hint" },
      `Send a request to /v1/chat to populate this board. Live stream ${streamState} · ${fmtTime(updatedAt)}`
    )
  );
}

// ── Alert builder ─────────────────────────────────────────────────────────────

function buildAlerts(summary, recentRuns, recentEvents, streamState, activeAgents) {
  const a = [];
  if (streamState !== "live") {
    a.push({
      tone: streamState === "reconnecting" ? "amber" : "red",
      title: "Stream " + streamState,
      body: streamState === "degraded" ? "WebSocket unavailable. Using last snapshot." : "Reconnecting to live stream…",
    });
  }
  if ((summary.cache_hit_rate || 0) < 0.35)
    a.push({ tone: "amber", title: "Cache pressure", body: `Hit rate ${fmt((summary.cache_hit_rate || 0) * 100, 1)}%` });
  if ((summary.active_agents || 0) > 6)
    a.push({ tone: "cyan", title: "High parallelism", body: `${summary.active_agents} agents active` });
  if (recentRuns.some((r) => r.approval_required)) {
    const n = recentRuns.filter((r) => r.approval_required).length;
    a.push({ tone: "amber", title: "Approval gate", body: `${n} run${n > 1 ? "s" : ""} need review` });
  }
  if (!recentEvents.length && !a.length)
    a.push({ tone: "cyan", title: "Quiet system", body: "No runtime events yet." });
  if (!a.length && activeAgents.length)
    a.push({ tone: "green", title: "All healthy", body: "Workflows moving, stream live." });
  return a.slice(0, 4);
}

// ── App ───────────────────────────────────────────────────────────────────────

function App() {
  const { loading, data, error, updatedAt, streamState } = useDashboard();
  const [query,              setQuery]              = useState("");
  const [selectedWorkflowId, setSelectedWorkflowId] = useState("");
  const [selectedAgentKey,   setSelectedAgentKey]   = useState("");
  const [demoStatus,         setDemoStatus]          = useState("idle");

  const summary            = data?.summary           || {};
  const activeWorkflows    = data?.active_workflows  || [];
  const activeAgents       = data?.active_agents     || [];
  const recentRuns         = data?.recent_runs       || [];
  const recentEvents       = data?.recent_events     || [];
  const recentTraces       = data?.recent_traces     || [];
  const workflowConnections= data?.workflow_connections || [];
  const modelUsage         = data?.model_usage       || {};
  const trendPoints        = data?.trend_points      || [];
  const taskBoard          = data?.task_board        || { columns: [], total_cards: 0 };

  const allWorkflows    = [...activeWorkflows, ...recentRuns.filter((r) => !activeWorkflows.some((w) => w.workflow_id === r.workflow_id))];
  const selectedWorkflow = allWorkflows.find((w) => w.workflow_id === selectedWorkflowId) || activeWorkflows[0] || recentRuns[0] || null;
  const isEmpty          = !activeWorkflows.length && !recentRuns.length && !recentEvents.length && !activeAgents.length;
  const approved         = recentRuns.filter((r) => r.approval_required).length;
  const cacheRate        = Number(summary.cache_hit_rate || 0);
  const trendLat         = trendPoints.map((r) => r.latency_ms);
  const trendCost        = trendPoints.map((r) => r.cost_usd * 1e6);
  const alerts           = buildAlerts(summary, recentRuns, recentEvents, streamState, activeAgents);

  // Auto-select first workflow
  useEffect(() => {
    if (!selectedWorkflowId && selectedWorkflow) {
      setSelectedWorkflowId(selectedWorkflow.workflow_id);
      const ag = activeAgents.find((a) => a.workflow_id === selectedWorkflow.workflow_id);
      if (ag) setSelectedAgentKey(agentKey(ag));
    }
  }, [selectedWorkflow, selectedWorkflowId, activeAgents]);

  // Keep selected agent in sync
  useEffect(() => {
    if (!selectedWorkflow) return;
    const wfAgents = activeAgents.filter((a) => a.workflow_id === selectedWorkflow.workflow_id);
    if (!wfAgents.length) { setSelectedAgentKey(""); return; }
    if (!wfAgents.some((a) => agentKey(a) === selectedAgentKey))
      setSelectedAgentKey(agentKey(wfAgents[0]));
  }, [activeAgents, selectedAgentKey, selectedWorkflow]);

  const onSelectWorkflow = useCallback((wfId, agKey) => {
    setSelectedWorkflowId(wfId);
    if (agKey) {
      setSelectedAgentKey(agKey);
    } else {
      const ag = activeAgents.find((a) => a.workflow_id === wfId);
      setSelectedAgentKey(ag ? agentKey(ag) : "");
    }
  }, [activeAgents]);

  const launchDemo = async () => {
    setDemoStatus("starting");
    try {
      const r = await fetch("/v1/demo/workflow", { method: "POST", headers: { "Content-Type": "application/json" } });
      const payload = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(payload?.detail || `HTTP ${r.status}`);
      onSelectWorkflow(payload.workflow_id || "");
      setDemoStatus(`started ${(payload.workflow_id || "demo").slice(-8)}`);
    } catch (err) {
      setDemoStatus(`error: ${err.message || err}`);
    }
  };

  const [activeNav, setActiveNav] = useState("kpis");

  const jumpTo = (id) => {
    setActiveNav(id);
    const el = document.getElementById(id);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const sections = [
    { id: "kpis",    label: "Overview",  count: summary.active_workflows || 0 },
    { id: "board",   label: "Board",     count: taskBoard.total_cards || 0 },
    { id: "detail",  label: "Workflow",  count: activeAgents.length },
    { id: "history", label: "History",   count: summary.recent_runs || 0 },
  ].map((s) => ({ ...s, active: s.id === activeNav }));

  if (loading && !data) {
    return React.createElement("div", { className: "app-boot" },
      React.createElement("div", { className: "app-boot__text" }, "Connecting to runtime…")
    );
  }

  if (error && !data) {
    return React.createElement("div", { className: "app-error" }, `Connection error: ${error}`);
  }

  return React.createElement(
    "div",
    { className: "app" },
    React.createElement(
      "div",
      { className: "app__layout" },

      // ── Sidebar ───────────────────────────────────────────────────────────
      React.createElement(Sidebar, { streamState, updatedAt, sections, onJump: jumpTo, alerts, onDemo: launchDemo, demoStatus }),

      // ── Main ──────────────────────────────────────────────────────────────
      React.createElement(
        "main",
        { className: "app__main" },

        // KPIs
        React.createElement("section", { id: "kpis" },
          React.createElement("div", { className: "kpi-grid" },
            React.createElement(KpiCard, {
              label: "Active workflows",
              value: fmt(summary.active_workflows || 0),
              sub: `${summary.active_agents || 0} agents · ${Object.keys(data?.pipeline_counts || {}).length} pipelines`,
              t: "cyan", spark: trendLat.slice(-12),
            }),
            React.createElement(KpiCard, {
              label: "Model calls",
              value: fmt(summary.total_model_calls || 0),
              sub: `Cache hit rate ${fmt(cacheRate * 100, 1)}%`,
              t: "amber", spark: trendCost.slice(-12),
            }),
            React.createElement(KpiCard, {
              label: "Total cost",
              value: `$${fmt(summary.total_model_cost_usd || 0, 4)}`,
              sub: `${fmt(summary.avg_latency_ms || 0, 0)}ms avg latency`,
              t: "green", spark: trendLat.slice(-12),
            }),
            React.createElement(KpiCard, {
              label: "Awaiting approval",
              value: fmt(approved),
              sub: `${summary.recent_runs || 0} total recent runs`,
              t: approved > 0 ? "amber" : "cyan",
            })
          )
        ),

        // Mission board
        React.createElement("section", { id: "board" },
          isEmpty
            ? React.createElement(EmptyMissionState, { streamState, updatedAt })
            : React.createElement(MissionBoard, { board: taskBoard, query, setQuery, selectedWorkflowId, onSelectWorkflow })
        ),

        // Detail + Ops row
        React.createElement("div", { className: "detail-row", id: "detail" },
          React.createElement("div", { className: "detail-row__drilldown" },
            React.createElement(WorkflowDrilldown, {
              workflow: selectedWorkflow,
              agents: activeAgents,
              events: recentEvents,
              traces: recentTraces,
              onSelectAgent: setSelectedAgentKey,
              selectedAgentKey,
            })
          ),
          React.createElement("div", { className: "detail-row__ops" },
            React.createElement(AgentSignals, { workflow: selectedWorkflow, connections: workflowConnections }),
            React.createElement(ModelUsage, { modelUsage }),
            React.createElement(EventStream, { events: recentEvents })
          )
        ),

        // Charts
        React.createElement("div", { className: "charts-row" },
          React.createElement(MiniChart, { title: "Latency trend", values: trendLat, color: "#63d6ff", unit: "ms" }),
          React.createElement(MiniChart, { title: "Cost trend (μUSD)", values: trendCost, color: "#ffce73", unit: "μ$" })
        ),

        // History
        React.createElement("section", { id: "history" },
          React.createElement(History, { runs: recentRuns, activeAgents, onSelectWorkflow })
        )
      )
    )
  );
}

createRoot(document.getElementById("root")).render(React.createElement(App));
