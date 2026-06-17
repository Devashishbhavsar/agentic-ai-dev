import React, { useState, useMemo } from "react";
const h = React.createElement;

const SWARM_COLOURS = {
  bi: "#6366f1", qa: "#f59e0b", devops: "#10b981",
  sw_eng: "#ec4899", ai_eng: "#8b5cf6", data_eng: "#06b6d4", release: "#f97316",
};

const COLUMNS = ["inbox","assigned","in_progress","review","done"];
const COL_LABELS = { inbox:"Inbox", assigned:"Assigned", in_progress:"In Progress",
                     review:"Review", done:"Done" };

function categorise(run) {
  if (run.status === "success" || run.status === "failed") return "done";
  if (run.stage === "review")       return "review";
  if (run.stage === "in_progress" || run.status === "running") return "in_progress";
  if (run.current_agent)            return "assigned";
  return "inbox";
}

function BoardCard({ run, isSelected, onClick }) {
  const dur = run.duration_ms ? `${(run.duration_ms/1000).toFixed(1)}s` : "—";
  return h("button", { className: `board__card${isSelected ? " is-selected" : ""}`, onClick },
    h("div", { className: "flex-center gap-8", style: { marginBottom: 4 } },
      h("span", { className: `badge badge--${run.pipeline || "cache"}` }, run.pipeline || "general"),
      h("span", { className: `badge badge--${run.status || "running"}` }, run.status || "running"),
    ),
    h("div", { className: "board__card-name truncate" }, run.request || "—"),
    h("div", { className: "board__card-meta text-mono" },
      `${dur} · ${run.current_agent || run.stage || "—"}`),
  );
}

function GanttTimeline({ run, events }) {
  if (!run) return h("div", { className: "gantt" },
    h("div", { className: "gantt__empty" }, "Select a workflow card to inspect its timeline"));

  const wfEvents = (events || []).filter(e => e.workflow_id === run.workflow_id);
  const agentNames = [...new Set(wfEvents.map(e => e.agent_name).filter(Boolean))];
  if (!agentNames.length && run.current_agent) agentNames.push(run.current_agent);

  const startMs = run.started_at ? new Date(run.started_at).getTime() : Date.now();
  const endMs = run.finished_at
    ? new Date(run.finished_at).getTime()
    : startMs + (run.duration_ms || 5000);
  const totalMs = Math.max(endMs - startMs, 1000);

  const lanes = agentNames.map(name => {
    const starts = wfEvents.filter(e => e.agent_name === name && e.event_type === "agent_started");
    const ends   = wfEvents.filter(e => e.agent_name === name && e.event_type === "agent_finished");
    const laneStart = starts[0]?.timestamp
      ? (new Date(starts[0].timestamp).getTime() - startMs) / totalMs : 0;
    const laneEnd   = ends[0]?.timestamp
      ? (new Date(ends[0].timestamp).getTime() - startMs) / totalMs
      : run.status === "running" ? 1 : laneStart + 0.2;
    const running = ends.length === 0 && run.status === "running";
    const swarm = Object.keys(SWARM_COLOURS).find(s => name.includes(s)) || "bi";
    return { name, start: laneStart, end: laneEnd, running, colour: SWARM_COLOURS[swarm] };
  });

  return h("div", { className: "gantt" },
    h("div", { className: "gantt__header" },
      h("span", { className: "gantt__title" }, "Timeline"),
      h("span", { className: "text-xs text-muted" }, `${(totalMs/1000).toFixed(1)}s total`),
    ),
    lanes.map(lane =>
      h("div", { key: lane.name, className: "gantt__lane" },
        h("div", { className: "gantt__lane-name" }, lane.name.replace("_agent","")),
        h("div", { className: "gantt__track" },
          h("div", {
            className: `gantt__bar ${lane.running ? "gantt__bar--running" : "gantt__bar--done"}`,
            style: { left: `${lane.start * 100}%`,
              width: `${Math.max((lane.end - lane.start) * 100, 4)}%`,
              background: lane.colour },
          }),
        ),
      )
    ),
    lanes.length === 0 && h("div", { className: "gantt__empty", style: { padding: 16 } },
      "No agent timing data for this workflow yet"),
  );
}

function AgentChatFeed({ run, events, traces }) {
  if (!run) return h("div", { className: "chat-feed" },
    h("div", { className: "chat-feed__empty" }, "Select a workflow to see the agent feed"));

  const wfEvents = (events || []).filter(e => e.workflow_id === run.workflow_id);
  const wfTraces = (traces || []).filter(t => t.workflow_id === run.workflow_id);
  const msgs = [
    ...wfEvents.map(e => ({ ts: e.timestamp, agent: e.agent_name || "system",
      text: `${e.event_type}${e.agent_name ? ` · ${e.agent_name}` : ""}` })),
    ...wfTraces.map(t => ({ ts: t.timestamp, agent: t.agent_name || "system",
      text: t.output || t.summary || JSON.stringify(t).slice(0, 120) })),
  ].sort((a, b) => new Date(a.ts) - new Date(b.ts));

  const swarmOf = name => Object.keys(SWARM_COLOURS).find(s => (name||"").includes(s)) || "bi";
  const isTyping = run.status === "running" && run.current_agent;

  return h("div", { className: "chat-feed", style: { maxHeight: 320, overflowY: "auto" } },
    msgs.slice(-30).map((m, i) =>
      h("div", { key: i, className: "chat-feed__msg" },
        h("div", { className: "chat-feed__avatar",
          style: { background: SWARM_COLOURS[swarmOf(m.agent)] || "#6366f1" } },
          (m.agent||"?").slice(0,2).toUpperCase()),
        h("div", { className: "chat-feed__body" },
          h("div", { className: "chat-feed__header" },
            h("span", { className: "chat-feed__name" }, m.agent),
            h("span", { className: "chat-feed__time" },
              m.ts ? new Date(m.ts).toLocaleTimeString() : ""),
          ),
          h("div", { className: "chat-feed__text" }, m.text),
        ),
      )
    ),
    isTyping && h("div", { className: "chat-feed__msg" },
      h("div", { className: "chat-feed__avatar",
        style: { background: SWARM_COLOURS[swarmOf(run.current_agent)] || "#6366f1" } },
        (run.current_agent||"?").slice(0,2).toUpperCase()),
      h("div", { className: "chat-feed__body" },
        h("div", { className: "chat-feed__header" },
          h("span", { className: "chat-feed__name" }, run.current_agent),
        ),
        h("div", { className: "chat-feed__typing" },
          h("span"), h("span"), h("span"),
          h("span", { style: { marginLeft: 4, fontSize: 11, color: "var(--text-3)" } }, "working…"),
        ),
      ),
    ),
    msgs.length === 0 && h("div", { className: "chat-feed__empty" },
      "No events recorded for this workflow yet"),
  );
}

export function Workflows({ data }) {
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState(null);
  const runs = data?.recent_runs || [];
  const events = data?.recent_events || [];
  const traces = data?.recent_traces || [];

  const filtered = query
    ? runs.filter(r =>
        r.request?.toLowerCase().includes(query) ||
        r.pipeline?.includes(query) ||
        r.current_agent?.includes(query))
    : runs;

  const grouped = useMemo(() => {
    const g = Object.fromEntries(COLUMNS.map(c => [c, []]));
    filtered.forEach(r => g[categorise(r)].push(r));
    return g;
  }, [filtered]);

  const selected = runs.find(r => r.workflow_id === selectedId);

  return h("div", { className: "page" },
    h("div", { className: "flex-center gap-12 mb-20" },
      h("h1", { className: "section-title", style: { margin: 0 } }, "Workflows"),
      h("input", {
        className: "search-input",
        placeholder: "Filter by agent, pipeline…",
        value: query,
        onChange: e => setQuery(e.target.value),
        style: { marginLeft: "auto" },
      }),
    ),
    h("div", { className: "board" },
      h("div", { className: "board__grid" },
        COLUMNS.map(col =>
          h("div", { key: col, className: "board__col" },
            h("div", { className: "board__col-head" },
              h("span", { className: "board__col-label" }, COL_LABELS[col]),
              h("span", { className: "board__col-count" }, grouped[col].length),
            ),
            grouped[col].length === 0
              ? h("div", { className: "board__empty" }, "Empty")
              : grouped[col].map(r =>
                  h(BoardCard, {
                    key: r.workflow_id,
                    run: r,
                    isSelected: r.workflow_id === selectedId,
                    onClick: () => setSelectedId(r.workflow_id === selectedId ? null : r.workflow_id),
                  })
                ),
          )
        )
      )
    ),
    h("div", { className: "detail-row", style: { marginTop: 24 } },
      h(GanttTimeline, { run: selected, events }),
      h(AgentChatFeed, { run: selected, events, traces }),
    ),
  );
}
