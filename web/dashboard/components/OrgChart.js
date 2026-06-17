import React, { useState, useEffect, useRef } from "react";
const h = React.createElement;

const SWARM_COLOURS = {
  bi: "#6366f1", qa: "#f59e0b", devops: "#10b981",
  sw_eng: "#ec4899", ai_eng: "#8b5cf6", data_eng: "#06b6d4", release: "#f97316",
};

function HierarchyTree({ roster, activeAgents, onNodeClick }) {
  const activeSet = new Set((activeAgents || []).map(a => a.name || a.agent_name));
  const W = 900, H = 480;
  const rootX = W / 2, rootY = 40;
  const swarmY = 130;
  const agentY = 260;
  const swarmCount = roster.swarms.length;
  const swarmSpacing = W / (swarmCount + 1);

  const swarmNodes = roster.swarms.map((s, i) => ({
    ...s, x: swarmSpacing * (i + 1), y: swarmY,
  }));

  const agentNodes = swarmNodes.flatMap(swarm => {
    const count = swarm.agents.length;
    const totalW = (count - 1) * 90;
    const startX = swarm.x - totalW / 2;
    return swarm.agents.map((name, j) => ({
      name, swarm: swarm.name, colour: SWARM_COLOURS[swarm.name],
      x: startX + j * 90, y: agentY + Math.floor(j / 8) * 70,
      active: activeSet.has(name),
    }));
  });

  return h("svg", { viewBox: `0 0 ${W} ${H + 80}`, style: { width: "100%", height: "auto" } },
    swarmNodes.map(s =>
      h("line", { key: `root-${s.name}`,
        x1: rootX, y1: rootY + 16, x2: s.x, y2: swarmY - 16,
        stroke: "#e2e8f0", strokeWidth: 1.5 })
    ),
    swarmNodes.flatMap(sn =>
      agentNodes.filter(a => a.swarm === sn.name).slice(0, 6).map(a =>
        h("line", { key: `sw-ag-${a.name}`,
          x1: sn.x, y1: swarmY + 16, x2: a.x, y2: a.y - 10,
          stroke: "#e2e8f0", strokeWidth: 1 })
      )
    ),
    h("g", { className: "org-node", transform: `translate(${rootX},${rootY})` },
      h("circle", { r: 20, fill: "#6366f1" }),
      h("text", { textAnchor: "middle", dy: 32, fontSize: 10, fill: "#475569" }, "Orchestrator"),
    ),
    swarmNodes.map(s =>
      h("g", { key: s.name, className: "org-node",
        transform: `translate(${s.x},${s.y})`, style: { cursor: "pointer" },
        onClick: () => onNodeClick({ type: "swarm", name: s.name }) },
        h("circle", { r: 16, fill: SWARM_COLOURS[s.name], opacity: 0.85 }),
        h("text", { textAnchor: "middle", dy: 28, fontSize: 10, fill: "#475569" },
          s.name.replace(/_/g, " ")),
      )
    ),
    agentNodes.map(a =>
      h("g", { key: a.name, className: "org-node",
        transform: `translate(${a.x},${a.y})`, style: { cursor: "pointer" },
        onClick: () => onNodeClick({ type: "agent", name: a.name, swarm: a.swarm }) },
        h("circle", { r: 9,
          fill: a.active ? "#dcfce7" : "#f1f5f9",
          stroke: a.colour, strokeWidth: a.active ? 2.5 : 1.5 }),
        a.active && h("circle", { r: 13, fill: "none", stroke: "#16a34a",
          strokeWidth: 1, opacity: 0.4 }),
        h("text", { textAnchor: "middle", dy: 20, fontSize: 8, fill: "#94a3b8" },
          a.name.replace("_agent", "")),
      )
    ),
  );
}

function NetworkGraph({ roster, activeAgents, connections, onNodeClick }) {
  const [nodes, setNodes] = useState([]);
  const [links, setLinks] = useState([]);
  const simRef = useRef(null);
  const W = 800, H = 480;

  useEffect(() => {
    const allNodes = [
      { id: "orchestrator", label: "Orchestrator", type: "root", colour: "#6366f1", r: 22,
        x: W/2, y: H/2 },
      ...roster.swarms.map((s, i) => ({
        id: `swarm_${s.name}`, label: s.name.replace(/_/g, " "), type: "swarm",
        colour: SWARM_COLOURS[s.name], swarm: s.name, r: 16,
        x: W/2 + Math.cos(i * Math.PI * 2 / roster.swarms.length) * 150,
        y: H/2 + Math.sin(i * Math.PI * 2 / roster.swarms.length) * 150,
      })),
      ...roster.swarms.flatMap((s, si) =>
        s.agents.map((name, ai) => ({
          id: name, label: name.replace("_agent",""), type: "agent",
          colour: SWARM_COLOURS[s.name], swarm: s.name, r: 8,
          x: W/2 + Math.cos(si * Math.PI * 2 / roster.swarms.length) * 150
             + Math.cos(ai * Math.PI * 2 / s.agents.length) * 60,
          y: H/2 + Math.sin(si * Math.PI * 2 / roster.swarms.length) * 150
             + Math.sin(ai * Math.PI * 2 / s.agents.length) * 60,
        }))
      ),
    ];
    const allLinks = [
      ...roster.swarms.map(s => ({ source: "orchestrator", target: `swarm_${s.name}`, type: "hierarchy" })),
      ...roster.swarms.flatMap(s => s.agents.map(name => ({
        source: `swarm_${s.name}`, target: name, type: "hierarchy",
      }))),
      ...(connections || []).map(c => ({ source: c.from_agent, target: c.to_agent, type: "handoff" })),
    ];

    setNodes(allNodes.map(n => ({...n})));
    setLinks(allLinks);

    import("d3-force").then(({ forceSimulation, forceLink, forceManyBody, forceCenter, forceCollide }) => {
      if (simRef.current) simRef.current.stop();
      const nodeCopies = allNodes.map(n => ({...n}));
      const sim = forceSimulation(nodeCopies)
        .force("link", forceLink(allLinks.map(l => ({...l}))).id(d => d.id).distance(60).strength(0.3))
        .force("charge", forceManyBody().strength(-120))
        .force("center", forceCenter(W/2, H/2))
        .force("collide", forceCollide(d => d.r + 6))
        .on("tick", () => setNodes([...nodeCopies]))
        .on("end", () => setNodes([...nodeCopies]));
      simRef.current = sim;
    });

    return () => simRef.current?.stop();
  }, [roster, connections]);

  const nodeById = new Map(nodes.map(n => [n.id, n]));

  return h("svg", { viewBox: `0 0 ${W} ${H}`, style: { width: "100%", height: 480 } },
    links.map((l, i) => {
      const src = nodeById.get(l.source?.id || l.source);
      const tgt = nodeById.get(l.target?.id || l.target);
      if (!src || !tgt) return null;
      return h("line", { key: i,
        x1: src.x || 0, y1: src.y || 0, x2: tgt.x || 0, y2: tgt.y || 0,
        stroke: l.type === "handoff" ? "#6366f1" : "#e2e8f0",
        strokeWidth: l.type === "handoff" ? 2 : 1,
        strokeDasharray: l.type === "handoff" ? "4,2" : undefined,
        opacity: 0.7 });
    }),
    nodes.map(n =>
      h("g", { key: n.id, className: "org-node",
        transform: `translate(${n.x || 0},${n.y || 0})`,
        style: { cursor: "pointer" },
        onClick: () => onNodeClick(n) },
        h("circle", { r: n.r, fill: n.colour, opacity: 0.85 }),
        h("text", { textAnchor: "middle", dy: n.r + 12,
          fontSize: n.type === "root" ? 10 : 8, fill: "#475569" }, n.label),
      )
    ),
  );
}

export function OrgChart({ data, activeAgents = [] }) {
  const [view, setView] = useState("tree");
  const [roster, setRoster] = useState(null);
  const [agentDetail, setAgentDetail] = useState(null);

  useEffect(() => {
    fetch("/v1/agents").then(r => r.json()).then(setRoster).catch(console.error);
  }, []);

  const connections = data?.workflow_connections || [];

  const handleNodeClick = async (node) => {
    const name = node.name || node.id;
    if (!name || name === "orchestrator" || name.startsWith("swarm_")) return;
    try {
      const d = await fetch(`/v1/agents/${name}`).then(r => r.json());
      setAgentDetail(d);
    } catch {
      setAgentDetail({ name, swarm: node.swarm, stats: {}, override: {} });
    }
  };

  if (!roster) return h("div", { className: "page" },
    h("div", { className: "empty-state" },
      h("div", { className: "empty-state__body" }, "Loading org chart…"))
  );

  return h("div", { className: "page" },
    h("div", { className: "org-chart" },
      h("div", { className: "org-chart__toolbar" },
        h("button", {
          className: `org-chart__view-btn${view === "tree" ? " is-active" : ""}`,
          onClick: () => setView("tree"),
        }, "🌳 Hierarchy"),
        h("button", {
          className: `org-chart__view-btn${view === "network" ? " is-active" : ""}`,
          onClick: () => setView("network"),
        }, "🕸 Network"),
      ),
      view === "tree"
        ? h(HierarchyTree, { roster, activeAgents, onNodeClick: handleNodeClick })
        : h(NetworkGraph, { roster, activeAgents, connections, onNodeClick: handleNodeClick }),
    ),
    agentDetail && h(React.Fragment, null,
      h("div", { className: "slideover-backdrop is-open",
        onClick: () => setAgentDetail(null) }),
      h("div", { className: "slideover is-open" },
        h("div", { className: "slideover__header" },
          h("div", { className: "slideover__title" }, agentDetail.name),
          h("button", { className: "slideover__close",
            onClick: () => setAgentDetail(null) }, "×"),
        ),
        h("div", { className: "slideover__section" },
          h("div", { className: "slideover__section-label" }, "Stats"),
          h("div", { className: "text-sm text-muted" },
            `Runs: ${agentDetail.stats?.total_runs ?? 0} · Cost: $${(agentDetail.stats?.total_cost_usd || 0).toFixed(4)}`),
        ),
      ),
    ),
  );
}
