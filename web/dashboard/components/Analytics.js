// web/dashboard/components/Analytics.js — pure SVG charts, no extra deps
import React, { useState, useEffect } from "react";
const h = React.createElement;

// ── Shared chart helpers ─────────────────────────────────────────────────────

function shortDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleDateString("en", { month: "short", day: "numeric" });
}

function fmt(n, prefix = "", suffix = "") {
  if (n === undefined || n === null) return "—";
  return `${prefix}${Number(n).toLocaleString(undefined, { maximumFractionDigits: 4 })}${suffix}`;
}

// ── Line Chart ───────────────────────────────────────────────────────────────

function LineChart({ points, xKey, yKey, colour = "#6366f1", yFormat, title }) {
  const W = 340, H = 120, padL = 44, padR = 12, padT = 12, padB = 28;
  const inner = { w: W - padL - padR, h: H - padT - padB };

  if (!points?.length) return h("div", { className: "mini-chart" },
    h("div", { className: "mini-chart__title" }, title),
    h("div", { className: "empty-state__body", style: { padding: 20 } }, "No data yet"),
  );

  const vals = points.map(p => p[yKey]);
  const maxV = Math.max(...vals, 0.001);
  const minV = Math.min(...vals, 0);

  const cx = (i) => padL + (i / Math.max(points.length - 1, 1)) * inner.w;
  const cy = (v) => padT + inner.h - ((v - minV) / Math.max(maxV - minV, 0.001)) * inner.h;

  const pathD = points.map((p, i) => `${i === 0 ? "M" : "L"}${cx(i).toFixed(1)} ${cy(p[yKey]).toFixed(1)}`).join(" ");
  const areaD = pathD
    + ` L${cx(points.length - 1).toFixed(1)} ${(padT + inner.h).toFixed(1)}`
    + ` L${padL.toFixed(1)} ${(padT + inner.h).toFixed(1)} Z`;

  const ticks = 3;
  const yLabels = Array.from({ length: ticks + 1 }, (_, i) => {
    const v = minV + ((maxV - minV) / ticks) * i;
    return { v, y: cy(v) };
  });

  return h("div", { className: "mini-chart" },
    h("div", { className: "mini-chart__title" }, title),
    h("svg", { viewBox: `0 0 ${W} ${H}`, className: "mini-chart__svg" },
      h("defs", null,
        h("linearGradient", { id: `grad-${title.replace(/\s/g, "")}`, x1: 0, y1: 0, x2: 0, y2: 1 },
          h("stop", { offset: "0%", stopColor: colour, stopOpacity: 0.18 }),
          h("stop", { offset: "100%", stopColor: colour, stopOpacity: 0.01 }),
        ),
      ),
      // Grid lines
      yLabels.map(({ v, y }, i) =>
        h("g", { key: i },
          h("line", { x1: padL, y1: y, x2: W - padR, y2: y,
            stroke: "#e2e8f0", strokeWidth: 1, strokeDasharray: "3,3" }),
          h("text", { x: padL - 4, y: y + 4, textAnchor: "end",
            fontSize: 9, fill: "#94a3b8" },
            yFormat ? yFormat(v) : v.toFixed(1)),
        )
      ),
      // Area fill
      h("path", { d: areaD, fill: `url(#grad-${title.replace(/\s/g, "")})` }),
      // Line
      h("path", { d: pathD, fill: "none", stroke: colour, strokeWidth: 2, strokeLinejoin: "round" }),
      // Dots
      points.map((p, i) =>
        h("circle", { key: i, cx: cx(i), cy: cy(p[yKey]), r: 3,
          fill: colour, stroke: "#fff", strokeWidth: 1.5 })
      ),
      // X labels
      points.filter((_, i) => i === 0 || i === points.length - 1 || points.length <= 7).map((p, i, arr) => {
        const origIdx = points.indexOf(p);
        return h("text", { key: i, x: cx(origIdx), y: H - 4, textAnchor: "middle",
          fontSize: 9, fill: "#94a3b8" }, shortDate(p[xKey]));
      }),
    ),
  );
}

// ── Bar Chart ────────────────────────────────────────────────────────────────

function BarChart({ points, xKey, yKey, colour = "#6366f1", title, yFormat }) {
  const W = 340, H = 120, padL = 44, padR = 12, padT = 12, padB = 28;
  const inner = { w: W - padL - padR, h: H - padT - padB };

  if (!points?.length) return h("div", { className: "mini-chart" },
    h("div", { className: "mini-chart__title" }, title),
    h("div", { className: "empty-state__body", style: { padding: 20 } }, "No data yet"),
  );

  const vals = points.map(p => p[yKey]);
  const maxV = Math.max(...vals, 1);
  const barW = Math.max(inner.w / points.length - 4, 4);

  return h("div", { className: "mini-chart" },
    h("div", { className: "mini-chart__title" }, title),
    h("svg", { viewBox: `0 0 ${W} ${H}`, className: "mini-chart__svg" },
      points.map((p, i) => {
        const bh = (p[yKey] / maxV) * inner.h;
        const x = padL + (i / points.length) * inner.w + 2;
        const y = padT + inner.h - bh;
        return h("g", { key: i },
          h("rect", { x, y, width: barW, height: Math.max(bh, 2),
            fill: colour, opacity: 0.85, rx: 2 }),
          h("text", { x: x + barW / 2, y: H - 4, textAnchor: "middle",
            fontSize: 9, fill: "#94a3b8" }, shortDate(p[xKey])),
        );
      }),
      // max label
      h("text", { x: padL - 4, y: padT + 4, textAnchor: "end", fontSize: 9, fill: "#94a3b8" },
        yFormat ? yFormat(maxV) : maxV),
      h("text", { x: padL - 4, y: padT + inner.h, textAnchor: "end", fontSize: 9, fill: "#94a3b8" }, "0"),
    ),
  );
}

// ── Horizontal Bar ───────────────────────────────────────────────────────────

function HBarChart({ rows, labelKey, valueKey, colour = "#6366f1", title, valueFormat }) {
  if (!rows?.length) return h("div", { className: "mini-chart" },
    h("div", { className: "mini-chart__title" }, title),
    h("div", { className: "empty-state__body", style: { padding: 20 } }, "No data yet"),
  );

  const maxV = Math.max(...rows.map(r => r[valueKey]), 1);
  const rowH = 22;
  const padL = 120, padR = 60, W = 340;
  const innerW = W - padL - padR;
  const H = rows.length * rowH + 8;

  return h("div", { className: "mini-chart" },
    h("div", { className: "mini-chart__title" }, title),
    h("svg", { viewBox: `0 0 ${W} ${H}`, className: "mini-chart__svg",
      style: { height: H } },
      rows.map((r, i) => {
        const bw = Math.max((r[valueKey] / maxV) * innerW, 2);
        const y = i * rowH + 4;
        return h("g", { key: i },
          h("text", { x: padL - 6, y: y + rowH / 2 + 4, textAnchor: "end",
            fontSize: 10, fill: "#475569" },
            (r[labelKey] || "").replace("_agent","").replace(/_/g," ").slice(0,16)),
          h("rect", { x: padL, y: y + 3, width: bw, height: rowH - 8,
            fill: r.colour || colour, opacity: 0.85, rx: 3 }),
          h("text", { x: padL + bw + 4, y: y + rowH / 2 + 4,
            fontSize: 10, fill: "#94a3b8" },
            valueFormat ? valueFormat(r[valueKey]) : r[valueKey]),
        );
      }),
    ),
  );
}

// ── Donut Chart ──────────────────────────────────────────────────────────────

function DonutChart({ slices, title }) {
  const R = 50, cx = 80, cy = 70, strokeW = 20;
  const total = slices.reduce((s, sl) => s + sl.value, 0) || 1;

  const COLOURS = ["#6366f1","#f59e0b","#10b981","#ec4899","#8b5cf6","#06b6d4","#f97316","#ef4444"];

  let angle = -Math.PI / 2;
  const arcs = slices.map((sl, i) => {
    const frac = sl.value / total;
    const startA = angle;
    angle += frac * Math.PI * 2;
    const endA = angle;
    const x1 = cx + R * Math.cos(startA), y1 = cy + R * Math.sin(startA);
    const x2 = cx + R * Math.cos(endA),   y2 = cy + R * Math.sin(endA);
    const large = frac > 0.5 ? 1 : 0;
    const d = `M${cx} ${cy} L${x1.toFixed(2)} ${y1.toFixed(2)} A${R} ${R} 0 ${large} 1 ${x2.toFixed(2)} ${y2.toFixed(2)} Z`;
    return { ...sl, d, colour: sl.colour || COLOURS[i % COLOURS.length] };
  });

  return h("div", { className: "mini-chart" },
    h("div", { className: "mini-chart__title" }, title),
    h("svg", { viewBox: "0 0 340 140", className: "mini-chart__svg", style: { height: 140 } },
      // Donut arcs
      arcs.map((arc, i) =>
        h("path", { key: i, d: arc.d, fill: arc.colour, opacity: 0.9 })
      ),
      // Inner white circle for donut effect
      h("circle", { cx, cy, r: R - strokeW, fill: "#fff" }),
      // Legend
      arcs.map((arc, i) =>
        h("g", { key: i, transform: `translate(170, ${14 + i * 18})` },
          h("rect", { x: 0, y: 0, width: 10, height: 10, fill: arc.colour, rx: 2 }),
          h("text", { x: 14, y: 9, fontSize: 10, fill: "#475569" },
            `${arc.label.slice(0, 18)} (${Math.round(arc.value / total * 100)}%)`),
        )
      ),
    ),
  );
}

// ── Analytics Tab ─────────────────────────────────────────────────────────────

export function Analytics() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [refreshed, setRefreshed] = useState(null);

  const load = async () => {
    try {
      const d = await fetch("/v1/analytics").then(r => r.json());
      setData(d);
      setRefreshed(new Date());
      setError(null);
    } catch (e) {
      setError("Failed to load analytics data");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    const t = setInterval(load, 30000);
    return () => clearInterval(t);
  }, []);

  if (loading) return h("div", { className: "page" },
    h("div", { className: "empty-state" },
      h("div", { className: "empty-state__icon" }, "📊"),
      h("div", { className: "empty-state__title" }, "Loading analytics…"),
    )
  );

  if (error) return h("div", { className: "page" },
    h("div", { className: "empty-state" },
      h("div", { className: "empty-state__icon" }, "⚠"),
      h("div", { className: "empty-state__title" }, error),
      h("button", { className: "btn-primary", style: { marginTop: 12 }, onClick: load }, "Retry"),
    )
  );

  const d = data || {};

  // Model donut slices
  const modelSlices = (d.model_breakdown || []).slice(0, 6).map(m => ({
    label: m.model,
    value: m.calls,
  }));

  // Swarm hbar rows (sorted by runs)
  const swarmRows = (d.swarm_activity || []).sort((a, b) => b.runs - a.runs);

  return h("div", { className: "page" },
    // Header
    h("div", { className: "flex-center gap-12 mb-20" },
      h("h1", { className: "section-title", style: { margin: 0 } }, "Analytics"),
      refreshed && h("span", { className: "text-xs text-muted", style: { marginLeft: "auto" } },
        `Updated ${refreshed.toLocaleTimeString()}`),
      h("button", { className: "btn-ghost text-sm", onClick: load }, "↻ Refresh"),
    ),

    // Row 1 — time series charts
    h("div", { style: { display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 16, marginBottom: 16 } },
      h(LineChart, {
        points: d.daily_cost || [],
        xKey: "date", yKey: "cost_usd",
        colour: "#6366f1",
        title: "Daily Cost (USD)",
        yFormat: v => `$${v.toFixed(3)}`,
      }),
      h(LineChart, {
        points: d.daily_latency || [],
        xKey: "date", yKey: "avg_latency_ms",
        colour: "#f59e0b",
        title: "Avg Latency (ms)",
        yFormat: v => `${Math.round(v)}ms`,
      }),
      h(BarChart, {
        points: d.daily_throughput || [],
        xKey: "date", yKey: "count",
        colour: "#10b981",
        title: "Workflows Completed / Day",
      }),
    ),

    // Row 2 — model breakdown + top agents + swarm activity
    h("div", { style: { display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 16, marginBottom: 16 } },
      h(DonutChart, {
        slices: modelSlices.length ? modelSlices : [{ label: "No data", value: 1 }],
        title: "Model Usage (calls)",
      }),
      h(HBarChart, {
        rows: (d.top_agents || []).slice(0, 8),
        labelKey: "agent", valueKey: "runs",
        colour: "#8b5cf6",
        title: "Top Agents by Runs",
      }),
      h(HBarChart, {
        rows: swarmRows,
        labelKey: "swarm", valueKey: "runs",
        title: "Swarm Activity",
      }),
    ),

    // Row 3 — model performance table
    h("div", { className: "mini-chart", style: { marginBottom: 16 } },
      h("div", { className: "mini-chart__title" }, "Model Performance Table"),
      h("table", { className: "data-table" },
        h("thead", null, h("tr", null,
          ["Model","Calls","Avg Latency","Total Cost"].map(c => h("th", { key: c }, c))
        )),
        h("tbody", null,
          (d.model_breakdown || []).length === 0
            ? h("tr", null, h("td", { colSpan: 4,
                style: { textAlign: "center", padding: 16, color: "var(--text-3)" } },
                "Run some workflows to see model performance data"))
            : (d.model_breakdown || []).map((m, i) =>
                h("tr", { key: i },
                  h("td", { className: "text-mono text-sm" }, m.model),
                  h("td", { className: "text-mono" }, m.calls),
                  h("td", { className: "text-mono" }, `${m.avg_latency_ms} ms`),
                  h("td", { className: "text-mono" }, fmt(m.cost_usd, "$")),
                )
              ),
        ),
      ),
    ),
  );
}
