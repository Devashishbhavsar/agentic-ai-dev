import React, { useState } from "react";
const h = React.createElement;

function BarChart({ values, labels, colour = "#6366f1" }) {
  const max = Math.max(...values, 0.01);
  const W = 300, H = 80, barW = W / values.length - 4;
  return h("svg", { viewBox: `0 0 ${W} ${H + 20}`, className: "mini-chart__svg" },
    values.map((v, i) => {
      const barH = (v / max) * H;
      return h("g", { key: i },
        h("rect", {
          x: i * (barW + 4) + 2, y: H - barH,
          width: barW, height: barH,
          fill: colour, opacity: 0.8, rx: 2,
        }),
        labels && h("text", {
          x: i * (barW + 4) + barW / 2 + 2, y: H + 14,
          textAnchor: "middle", fontSize: 8, fill: "#94a3b8",
        }, labels[i]),
      );
    }),
  );
}

export function History({ data }) {
  const [expandedId, setExpandedId] = useState(null);
  const [filter, setFilter] = useState("all");

  const runs = (data?.recent_runs || []).filter(r =>
    filter === "all" || r.status === filter);

  const modelUsage = data?.model_usage || {};
  const modelRows = Object.entries(modelUsage).map(([model, stats]) => ({
    model: model.replace("openrouter/", ""),
    calls: stats.call_count || 0,
    avgLatency: stats.avg_latency_ms ? `${Math.round(stats.avg_latency_ms)} ms` : "—",
    avgCost: stats.avg_cost_usd ? `$${stats.avg_cost_usd.toFixed(4)}` : "—",
  }));

  const trend = data?.cost_trend || Array(7).fill(0);
  const days = Array.from({ length: 7 }, (_, i) => {
    const d = new Date(); d.setDate(d.getDate() - 6 + i);
    return d.toLocaleDateString("en", { weekday: "short" });
  });

  return h("div", { className: "page" },
    h("div", { className: "flex-center gap-8 mb-20" },
      h("h1", { className: "section-title", style: { margin: 0 } }, "Run History"),
      ["all","success","running","failed"].map(f =>
        h("button", {
          key: f,
          className: `badge badge--${f === "all" ? "pending" : f}`,
          style: { cursor: "pointer", marginLeft: f === "all" ? "auto" : 0,
                   opacity: filter === f ? 1 : 0.5 },
          onClick: () => setFilter(f),
        }, f)
      ),
    ),
    h("div", { style: { background: "var(--surface)", border: "1px solid var(--border)",
                         borderRadius: "var(--r-lg)", marginBottom: 24, overflow: "hidden" } },
      h("table", { className: "data-table" },
        h("thead", null,
          h("tr", null,
            ["Request","Pipeline","Status","Duration","Model Calls","Cost","Time"].map(col =>
              h("th", { key: col }, col)
            )
          )
        ),
        h("tbody", null,
          runs.map(r =>
            h(React.Fragment, { key: r.workflow_id },
              h("tr", {
                style: { cursor: "pointer" },
                className: expandedId === r.workflow_id ? "is-selected" : "",
                onClick: () => setExpandedId(r.workflow_id === expandedId ? null : r.workflow_id),
              },
                h("td", { className: "truncate", style: { maxWidth: 200 } }, r.request || "—"),
                h("td", null, h("span", { className: `badge badge--${r.pipeline||"cache"}` },
                  r.pipeline || "general")),
                h("td", null, h("span", { className: `badge badge--${r.status||"running"}` },
                  r.status || "running")),
                h("td", { className: "text-mono" },
                  r.duration_ms ? `${(r.duration_ms/1000).toFixed(1)}s` : "—"),
                h("td", { className: "text-mono" }, r.model_calls || "—"),
                h("td", { className: "text-mono" },
                  r.cost_usd ? `$${r.cost_usd.toFixed(4)}` : "—"),
                h("td", { className: "text-mono text-muted" },
                  r.started_at ? new Date(r.started_at).toLocaleTimeString() : "—"),
              ),
              expandedId === r.workflow_id && h("tr", null,
                h("td", { colSpan: 7, style: { padding: "12px 16px", background: "#f8fafc" } },
                  h("div", { className: "text-sm text-muted" },
                    `Workflow ID: ${r.workflow_id} · Stage: ${r.stage || "—"} · Agent: ${r.current_agent || "—"}`),
                ),
              ),
            )
          ),
          runs.length === 0 && h("tr", null,
            h("td", { colSpan: 7, style: { textAlign: "center", padding: 24,
                                           color: "var(--text-3)" } },
              "No runs match this filter"),
          ),
        ),
      ),
    ),
    h("div", { style: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 } },
      h("div", { className: "mini-chart" },
        h("div", { className: "mini-chart__title" }, "Model Performance"),
        h("table", { className: "data-table" },
          h("thead", null, h("tr", null,
            ["Model","Calls","Avg Latency","Avg Cost"].map(c => h("th",{key:c},c)))),
          h("tbody", null,
            modelRows.map(r =>
              h("tr", { key: r.model },
                h("td", { className: "text-mono text-sm" }, r.model),
                h("td", { className: "text-mono" }, r.calls),
                h("td", { className: "text-mono" }, r.avgLatency),
                h("td", { className: "text-mono" }, r.avgCost),
              )
            ),
            modelRows.length === 0 && h("tr", null,
              h("td", { colSpan: 4, style: { textAlign:"center", color:"var(--text-3)", padding:12 }},
                "No model data yet")),
          ),
        ),
      ),
      h("div", { className: "mini-chart" },
        h("div", { className: "mini-chart__title" }, "7-day Cost (USD)"),
        h(BarChart, { values: trend, labels: days, colour: "#6366f1" }),
      ),
    ),
  );
}
