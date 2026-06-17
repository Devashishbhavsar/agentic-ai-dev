import React, { useState, useEffect } from "react";
const h = React.createElement;

function ResourceBar({ percent, warn = 70, danger = 90 }) {
  const cls = percent >= danger ? "danger" : percent >= warn ? "warn" : "";
  return h("div", { className: "resource-bar" },
    h("div", {
      className: `resource-bar__fill${cls ? ` resource-bar__fill--${cls}` : ""}`,
      style: { width: `${Math.min(percent, 100)}%` },
    }),
  );
}

export function System() {
  const [status, setStatus]    = useState(null);
  const [res, setRes]          = useState(null);
  const [discord, setDiscord]  = useState(null);
  const [orStatus, setOrStatus] = useState(null);
  const [restarting, setRestarting] = useState({});

  async function load() {
    try {
      const [s, r, d] = await Promise.all([
        fetch("/v1/system/status").then(x => x.json()),
        fetch("/v1/system/resources").then(x => x.json()),
        fetch("/v1/system/discord").then(x => x.json()),
      ]);
      setStatus(s); setRes(r); setDiscord(d);
    } catch(e) { console.error(e); }
  }

  useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, []);

  const restart = async (name) => {
    setRestarting(r => ({...r, [name]: true}));
    try {
      await fetch("/v1/system/restart", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ service: name }),
      });
      setTimeout(load, 3000);
    } finally {
      setTimeout(() => setRestarting(r => ({...r, [name]: false})), 3000);
    }
  };

  const testOpenRouter = async () => {
    setOrStatus("testing…");
    try {
      const r = await fetch("/v1/system/openrouter-check").then(x => x.json());
      setOrStatus(r.valid ? "✓ Valid" : `✗ ${r.reason}`);
    } catch { setOrStatus("✗ Request failed"); }
  };

  const fmtUptime = (s) => {
    if (!s) return "—";
    const d = Math.floor(s / 86400), hh = Math.floor((s % 86400) / 3600),
          m = Math.floor((s % 3600) / 60);
    return d > 0 ? `${d}d ${hh}h` : hh > 0 ? `${hh}h ${m}m` : `${m}m`;
  };

  return h("div", { className: "page" },
    h("div", { className: "sys-section" },
      h("h3", null, "Services"),
      h("div", { style: { background:"var(--surface)", border:"1px solid var(--border)",
                           borderRadius:"var(--r-lg)", overflow:"hidden" } },
        h("table", { className: "data-table" },
          h("thead", null, h("tr", null,
            ["Service","Status","PID","Uptime","Restarts","Actions"].map(c=>h("th",{key:c},c)))),
          h("tbody", null,
            (status?.services || []).map(svc =>
              h("tr", { key: svc.name },
                h("td", { className: "text-mono" }, svc.name),
                h("td", null, h("span", {
                  className: `pill ${svc.active ? "pill--ok" : "pill--error"}` },
                  svc.active ? "● running" : "✗ stopped")),
                h("td", { className: "text-mono text-muted" }, svc.pid || "—"),
                h("td", { className: "text-mono" }, fmtUptime(svc.uptime_seconds)),
                h("td", { className: "text-mono" }, svc.restarts ?? "—"),
                h("td", null,
                  h("button", {
                    className: "btn-ghost text-sm",
                    disabled: restarting[svc.name],
                    onClick: () => restart(svc.name),
                  }, restarting[svc.name] ? "Restarting…" : "Restart"),
                ),
              )
            ),
            (!status?.services || status.services.length === 0) && h("tr", null,
              h("td", { colSpan: 6, style: { textAlign:"center", padding: 16, color:"var(--text-3)" } },
                "Loading…")),
          ),
        ),
      ),
    ),
    h("div", { className: "sys-section" },
      h("h3", null, "System Resources"),
      h("div", { className: "sys-grid-2" },
        h("div", { className: "sys-card" },
          h("div", { className: "text-xs text-muted", style:{marginBottom:8} }, "CPU"),
          h("div", { style:{fontSize:24,fontWeight:700} }, `${res?.cpu_percent ?? "—"}%`),
          res && h(ResourceBar, { percent: res.cpu_percent }),
          h("div", { className: "text-xs text-muted", style:{marginTop:16,marginBottom:8} }, "Memory"),
          res && h(React.Fragment, null,
            h("div", { style:{fontSize:14} },
              `${res.memory_used_mb} MB / ${res.memory_total_mb} MB`),
            h(ResourceBar, { percent: res.memory_percent }),
          ),
        ),
        h("div", { className: "sys-card" },
          h("div", { className: "text-xs text-muted", style:{marginBottom:8} }, "Disk"),
          (res?.disk || []).map(d =>
            h("div", { key: d.label, style:{marginBottom:8} },
              h("div", { className: "flex-center gap-8" },
                h("span", { className: "text-sm" }, d.label),
                h("span", { className: "text-mono text-sm text-muted", style:{marginLeft:"auto"} },
                  `${d.size_mb} MB`),
              ),
              h("div", { className: "text-xs text-muted" }, d.path),
            )
          ),
          res?.disk?.length === 0 && h("div", { className: "text-sm text-muted" }, "No disk entries"),
        ),
      ),
    ),
    h("div", { className: "sys-section" },
      h("h3", null, "OpenRouter"),
      h("div", { className: "sys-card" },
        h("div", { className: "flex-center gap-12" },
          h("span", { className: "text-sm" }, "API Key configured"),
          h("button", { className: "btn-ghost text-sm", onClick: testOpenRouter },
            "Test Connection"),
          orStatus && h("span", {
            className: "text-sm",
            style: { color: orStatus.startsWith("✓") ? "var(--green)" : "var(--red)" },
          }, orStatus),
        ),
      ),
    ),
    h("div", { className: "sys-section" },
      h("h3", null, "Discord"),
      h("div", { className: "sys-card" },
        discord
          ? h("div", { style:{display:"grid",gridTemplateColumns:"1fr 1fr",gap:12} },
              [
                ["Status", discord.connected ? "● Connected" : "✗ Disconnected"],
                ["Reconnects today", discord.reconnects_today ?? "—"],
                ["Last activity", discord.last_activity || "—"],
              ].map(([k,v]) =>
                h("div", { key: k },
                  h("div", { className: "text-xs text-muted" }, k),
                  h("div", { className: "text-sm", style:{marginTop:2} }, String(v)),
                )
              )
            )
          : h("div", { className: "text-sm text-muted" }, "Loading…"),
      ),
    ),
  );
}
