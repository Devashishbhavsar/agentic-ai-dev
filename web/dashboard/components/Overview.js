import React, { useState, useRef, useEffect } from "react";
const h = React.createElement;

function KpiCard({ label, value, sub, spark }) {
  return h("div", { className: "kpi-card" },
    h("div", { className: "kpi-card__label" }, label),
    h("div", { className: "kpi-card__value" }, value),
    sub   && h("div", { className: "kpi-card__sub" }, sub),
    spark && h(Sparkline, { values: spark }),
  );
}

function Sparkline({ values }) {
  if (!values?.length) return null;
  const w = 80, h2 = 24, pad = 2;
  const max = Math.max(...values, 1);
  const xs = values.map((_, i) => pad + (i / (values.length - 1 || 1)) * (w - pad * 2));
  const ys = values.map(v => h2 - pad - (v / max) * (h2 - pad * 2));
  const d = xs.map((x, i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)} ${ys[i].toFixed(1)}`).join(" ");
  return h("svg", { viewBox: `0 0 ${w} ${h2}`, style: { width: "100%", height: 24, marginTop: 8 } },
    h("path", { d, fill: "none", stroke: "var(--accent)", strokeWidth: 1.5 }),
  );
}

function WorkflowItem({ wf }) {
  const elapsed = wf.duration_ms
    ? `${(wf.duration_ms / 1000).toFixed(1)}s`
    : wf.started_at
      ? `${Math.floor((Date.now() - new Date(wf.started_at).getTime()) / 1000)}s`
      : "—";
  return h("div", { className: "board__card", style: { marginBottom: 8 } },
    h("div", { className: "flex-center gap-8", style: { marginBottom: 4 } },
      h("span", { className: `badge badge--${wf.pipeline || "pending"}` }, wf.pipeline || "general"),
      h("span", { className: `badge badge--${wf.status || "running"}` }, wf.status || "running"),
    ),
    h("div", { className: "board__card-name truncate" }, wf.request || "—"),
    h("div", { className: "board__card-meta text-mono" }, `${elapsed} · ${wf.current_agent || "—"}`),
  );
}

const EVENT_COLOURS = {
  workflow_finished: "type--workflow_finished",
  workflow_started:  "type--workflow_started",
  agent_finished:    "type--agent_finished",
  agent_started:     "type--agent_started",
  model_call:        "type--model_call",
  agent_trace:       "type--agent_trace",
};

function EventFeed({ events }) {
  const [paused, setPaused] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    if (!paused && ref.current) ref.current.scrollTop = 0;
  }, [events, paused]);
  return h("div", { className: "event-feed" },
    h("div", { className: "event-feed__header" },
      h("span", { className: "event-feed__title" }, "Live Events"),
      h("span", { className: "event-feed__autoscroll", onClick: () => setPaused(p => !p) },
        paused ? "▶ Resume" : "⏸ Pause"),
    ),
    h("div", { ref, style: { maxHeight: 340, overflowY: "auto" } },
      (events || []).slice(0, 50).map((ev, i) =>
        h("div", { key: i, className: "event-item" },
          h("span", { className: `event-item__type ${EVENT_COLOURS[ev.event_type] || ""}` },
            ev.event_type || "event"),
          h("span", { className: "event-item__agent truncate" },
            ev.agent_name || ev.workflow_id?.slice(-8) || "—"),
          h("span", { className: "event-item__time" },
            ev.timestamp ? new Date(ev.timestamp).toLocaleTimeString() : "—"),
        )
      ),
      (!events || events.length === 0) && h("div", { className: "chat-feed__empty" }, "Waiting for events…"),
    ),
  );
}

export function Overview({ data }) {
  if (!data) {
    return h("div", { className: "page" },
      h("div", { className: "empty-state" },
        h("div", { className: "empty-state__icon" }, "⟳"),
        h("div", { className: "empty-state__title" }, "Connecting…"),
      )
    );
  }
  const s = data.summary || {};
  const runs = data.recent_runs || [];
  const events = data.recent_events || [];
  const active = runs.filter(r => r.status === "running");
  const cacheRate = s.cache_hits
    ? Math.round((s.cache_hits / (s.cache_hits + (s.cache_misses || 0))) * 100)
    : 0;
  const trendCost = (data.latency_trend || []).slice(-7);

  return h("div", { className: "page" },
    h("div", { className: "kpi-grid" },
      h(KpiCard, { label: "Active Workflows", value: s.active_workflows ?? 0,
        sub: `${s.active_agents ?? 0} agents busy` }),
      h(KpiCard, { label: "Agents Busy", value: s.active_agents ?? 0,
        sub: "across all swarms" }),
      h(KpiCard, { label: "Cost Today",
        value: `$${(s.total_model_cost_usd || 0).toFixed(4)}`,
        sub: `${Math.round(s.avg_latency_ms || 0)} ms avg latency` }),
      h(KpiCard, { label: "Model Calls", value: s.total_model_calls ?? 0,
        sub: `Cache hit ${cacheRate}%`, spark: trendCost }),
      h(KpiCard, { label: "Cache Hit Rate", value: `${cacheRate}%`,
        sub: `${s.cache_hits ?? 0} hits · ${s.cache_misses ?? 0} misses` }),
    ),
    h("div", { className: "two-col" },
      h("div", null,
        h("h2", { className: "section-title" }, "Active Workflows"),
        active.length === 0
          ? h("div", { className: "empty-state", style: { padding: 24 } },
              h("div", { className: "empty-state__body" },
                "No active workflows — send a message via Discord to start one"))
          : active.map((wf, i) => h(WorkflowItem, { key: wf.workflow_id || i, wf })),
        runs.slice(0, 5).length > 0 && h("div", { style: { marginTop: 16 } },
          h("h3", { style: { fontSize: 13, fontWeight: 600, marginBottom: 8 } }, "Recent Runs"),
          runs.slice(0, 5).map((r, i) => h(WorkflowItem, { key: r.workflow_id || i, wf: r })),
        ),
      ),
      h(EventFeed, { events }),
    ),
  );
}
