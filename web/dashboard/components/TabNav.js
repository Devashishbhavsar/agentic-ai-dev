// web/dashboard/components/TabNav.js
import React from "react";

const h = React.createElement;

const TABS = [
  { id: "overview",   label: "Overview" },
  { id: "agents",     label: "Agents" },
  { id: "orgchart",   label: "Org Chart" },
  { id: "workflows",  label: "Workflows" },
  { id: "history",    label: "History" },
  { id: "analytics",  label: "Analytics" },
  { id: "system",     label: "System" },
  { id: "settings",   label: "Settings" },
];

export function TabNav({ activeTab, onTabChange }) {
  return h("nav", { className: "tab-nav" },
    TABS.map(t =>
      h("button", {
        key: t.id,
        className: `tab-nav__item${activeTab === t.id ? " is-active" : ""}`,
        onClick: () => onTabChange(t.id),
      }, t.label)
    )
  );
}
