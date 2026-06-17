import React, { useState, useEffect } from "react";
const h = React.createElement;

const SWARM_COLOURS = {
  bi: "#6366f1", qa: "#f59e0b", devops: "#10b981",
  sw_eng: "#ec4899", ai_eng: "#8b5cf6", data_eng: "#06b6d4", release: "#f97316",
};

function AgentDetailPanel({ agent, onClose }) {
  const [config, setConfig] = useState({
    model_tier: agent?.override?.model_tier || "balanced",
    max_tokens: agent?.override?.max_tokens || 512,
    system_prompt: agent?.override?.system_prompt || "",
  });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  if (!agent) return null;

  const save = async () => {
    setSaving(true);
    try {
      await fetch(`/v1/agents/${agent.name}/config`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(config),
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } finally {
      setSaving(false);
    }
  };

  const s = agent.stats || {};

  return h(React.Fragment, null,
    h("div", { className: "slideover-backdrop is-open", onClick: onClose }),
    h("div", { className: "slideover is-open" },
      h("div", { className: "slideover__header" },
        h("div", null,
          h("div", { className: "slideover__title" }, agent.name),
          h("span", { className: "badge",
            style: { background: `${SWARM_COLOURS[agent.swarm] || "#6366f1"}22`,
                     color: SWARM_COLOURS[agent.swarm] || "#6366f1" } },
            agent.swarm),
        ),
        h("button", { className: "slideover__close", onClick: onClose }, "×"),
      ),
      h("div", { className: "slideover__section" },
        h("div", { className: "slideover__section-label" }, "Stats"),
        h("div", { style: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 } },
          [
            ["Runs", s.total_runs ?? 0],
            ["Avg latency", `${s.avg_latency_ms ?? 0} ms`],
            ["Total cost", `$${(s.total_cost_usd || 0).toFixed(4)}`],
            ["Last active", s.last_active || "—"],
          ].map(([label, val]) =>
            h("div", { key: label },
              h("div", { className: "text-xs text-muted" }, label),
              h("div", { style: { fontWeight: 600, fontFamily: "var(--font-mono)", fontSize: 13 } },
                String(val)),
            )
          )
        ),
      ),
      h("div", { className: "slideover__section" },
        h("div", { className: "slideover__section-label" }, "Config Overrides"),
        h("div", { className: "field" },
          h("label", null, "Model Tier"),
          h("select", { value: config.model_tier,
            onChange: e => setConfig(c => ({ ...c, model_tier: e.target.value })) },
            ["planning","balanced","fast","long-context"].map(t =>
              h("option", { key: t, value: t }, t))
          ),
        ),
        h("div", { className: "field" },
          h("label", null, "Max Tokens"),
          h("input", { type: "number", value: config.max_tokens,
            onChange: e => setConfig(c => ({ ...c, max_tokens: +e.target.value })) }),
        ),
        h("div", { className: "field" },
          h("label", null, "System Prompt Override"),
          h("textarea", { rows: 4, value: config.system_prompt,
            placeholder: "Leave blank to use default from code",
            onChange: e => setConfig(c => ({ ...c, system_prompt: e.target.value })) }),
        ),
        h("button", { className: "btn-primary", onClick: save, disabled: saving },
          saving ? "Saving…" : saved ? "✓ Saved" : "Save Changes"),
      ),
    ),
  );
}

function SwarmCard({ swarm, activeAgents, onAgentClick }) {
  const colour = SWARM_COLOURS[swarm.name] || "#6366f1";
  const activeSet = new Set((activeAgents || []).map(a => a.name || a.agent_name));
  const activeCount = swarm.agents.filter(n => activeSet.has(n)).length;

  return h("div", { className: `swarm-card swarm-card--${swarm.name}` },
    h("div", { className: "swarm-card__header" },
      h("div", null,
        h("span", { className: "swarm-card__name" }, swarm.name.replace(/_/g, " ")),
        activeCount > 0 && h("span", { className: "active-badge", style: { marginLeft: 8 } },
          `● ${activeCount} active`),
      ),
      h("span", { className: "swarm-card__count" }, `${swarm.count} agents`),
    ),
    h("div", { className: "agent-tags" },
      swarm.agents.map(name =>
        h("button", {
          key: name,
          className: `agent-tag${activeSet.has(name) ? " is-active" : ""}`,
          onClick: () => onAgentClick(name, swarm.name),
        }, name.replace("_agent", "").replace(/_/g, " "))
      )
    ),
  );
}

export function Agents({ activeAgents = [] }) {
  const [roster, setRoster]   = useState(null);
  const [query, setQuery]     = useState("");
  const [agentDetail, setAgentDetail] = useState(null);

  useEffect(() => {
    fetch("/v1/agents").then(r => r.json()).then(setRoster).catch(console.error);
  }, []);

  const openAgent = async (name, swarm) => {
    try {
      const d = await fetch(`/v1/agents/${name}`).then(r => r.json());
      setAgentDetail(d);
    } catch {
      setAgentDetail({ name, swarm, stats: {}, override: {} });
    }
  };

  if (!roster) return h("div", { className: "page" },
    h("div", { className: "empty-state" },
      h("div", { className: "empty-state__body" }, "Loading agents…"))
  );

  const filtered = query
    ? roster.swarms.map(s => ({
        ...s,
        agents: s.agents.filter(n => n.includes(query.toLowerCase())),
      })).filter(s => s.agents.length > 0)
    : roster.swarms;

  return h("div", { className: "page" },
    h("div", { className: "flex-center gap-12 mb-20" },
      h("h1", { className: "section-title", style: { margin: 0 } },
        `${roster.total} agents across ${roster.swarms.length} swarms`),
      h("input", {
        className: "search-input",
        placeholder: "Search agents…",
        value: query,
        onChange: e => setQuery(e.target.value),
        style: { marginLeft: "auto" },
      }),
    ),
    h("div", { className: "swarm-grid" },
      filtered.map(swarm =>
        h(SwarmCard, { key: swarm.name, swarm, activeAgents, onAgentClick: openAgent })
      )
    ),
    agentDetail && h(AgentDetailPanel, {
      agent: agentDetail,
      onClose: () => setAgentDetail(null),
    }),
  );
}
