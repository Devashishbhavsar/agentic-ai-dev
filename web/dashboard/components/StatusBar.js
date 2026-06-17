// web/dashboard/components/StatusBar.js
import React, { useState, useEffect } from "react";

const h = React.createElement;

export function StatusBar() {
  const [status, setStatus] = useState({
    gateway: null, discord: null, agent: null, update: null,
  });

  useEffect(() => {
    async function fetchStatus() {
      try {
        const sys = await fetch("/v1/system/status").then(r => r.json());
        const agent = sys.services?.find(s => s.name === "enterprise-agent");
        const gw    = sys.services?.find(s => s.name === "openclaw-gateway");
        setStatus(prev => ({
          ...prev,
          agent:   agent?.active ? "ok" : "error",
          gateway: gw?.active    ? "ok" : "error",
        }));
      } catch { /* services may not be ready */ }

      try {
        const disc = await fetch("/v1/system/discord").then(r => r.json());
        setStatus(prev => ({
          ...prev,
          discord: disc.connected ? "ok" : "warn",
        }));
      } catch { }
    }
    fetchStatus();
    const t = setInterval(fetchStatus, 30000);
    return () => clearInterval(t);
  }, []);

  const pill = (label, state) => {
    const cls = state === "ok" ? "pill--ok" : state === "warn" ? "pill--warn" : "pill--neutral";
    const dot = state === "ok" ? "● " : state === "error" ? "✗ " : "○ ";
    return h("span", { key: label, className: `pill ${cls}`, title: label }, dot + label);
  };

  return h("div", { className: "status-bar" },
    h("span", { className: "status-bar__brand" }, "OpenClaw / Control Plane"),
    pill("Gateway", status.gateway),
    pill("Discord", status.discord),
    pill("Agent Service", status.agent),
    status.update && h("span", { className: "status-bar__update" },
      `⬆ ${status.update} available`),
  );
}
