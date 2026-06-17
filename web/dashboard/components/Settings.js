import React, { useState, useEffect } from "react";
const h = React.createElement;

const METRICS = [
  { value: "total_cost_usd",      label: "Daily Cost (USD)" },
  { value: "avg_latency_ms",      label: "Avg Latency (ms)" },
  { value: "agent_failure_count", label: "Agent Failures (per hour)" },
  { value: "service_down",        label: "Service Down" },
];

const OPERATORS = [
  { value: "gt", label: "greater than" },
  { value: "lt", label: "less than" },
  { value: "eq", label: "equals" },
];

const CHANNELS = [
  { value: "banner",  label: "Banner only" },
  { value: "discord", label: "Discord only" },
  { value: "both",    label: "Banner + Discord" },
];

export function Settings() {
  const [rules, setRules] = useState([]);
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({
    label: "", metric: "total_cost_usd", operator: "gt",
    threshold: "", channel: "banner", enabled: true,
  });

  const load = () =>
    fetch("/v1/alerts/rules").then(r => r.json()).then(d => setRules(d.rules || [])).catch(console.error);

  useEffect(() => { load(); }, []);

  const toggle = async (rule) => {
    await fetch("/v1/alerts/rules", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...rule, id: undefined, enabled: !rule.enabled }),
    });
    load();
  };

  const del = async (id) => {
    await fetch(`/v1/alerts/rules/${id}`, { method: "DELETE" });
    load();
  };

  const submit = async (e) => {
    e.preventDefault();
    await fetch("/v1/alerts/rules", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...form, threshold: parseFloat(form.threshold) }),
    });
    setAdding(false);
    setForm({ label:"", metric:"total_cost_usd", operator:"gt",
               threshold:"", channel:"banner", enabled:true });
    load();
  };

  return h("div", { className: "page" },
    h("div", { className: "flex-center gap-12 mb-20" },
      h("h1", { className: "section-title", style: { margin: 0 } }, "Alert Rules"),
      h("button", {
        className: "btn-primary",
        style: { marginLeft: "auto" },
        onClick: () => setAdding(a => !a),
      }, adding ? "Cancel" : "+ Add Rule"),
    ),
    adding && h("form", {
      onSubmit: submit,
      style: { background:"var(--surface)", border:"1px solid var(--border)",
               borderRadius:"var(--r-lg)", padding:16, marginBottom:16,
               display:"grid", gridTemplateColumns:"1fr 1fr 1fr 1fr auto", gap:10, alignItems:"end" },
    },
      h("div", { className: "field", style:{margin:0} },
        h("label", null, "Label"),
        h("input", { required:true, value:form.label,
                     onChange: e => setForm(f=>({...f,label:e.target.value})),
                     placeholder:"e.g. Cost spike" }),
      ),
      h("div", { className: "field", style:{margin:0} },
        h("label", null, "Metric"),
        h("select", { value:form.metric,
                      onChange: e => setForm(f=>({...f,metric:e.target.value})) },
          METRICS.map(m => h("option",{key:m.value,value:m.value},m.label))),
      ),
      h("div", { className: "field", style:{margin:0} },
        h("label", null, "Threshold"),
        h("div", { className: "flex-center gap-8" },
          h("select", { value:form.operator, style:{width:100},
                        onChange: e => setForm(f=>({...f,operator:e.target.value})) },
            OPERATORS.map(o => h("option",{key:o.value,value:o.value},o.label))),
          h("input", { required:true, type:"number", step:"any", value:form.threshold,
                       onChange: e => setForm(f=>({...f,threshold:e.target.value})),
                       placeholder:"0" }),
        ),
      ),
      h("div", { className: "field", style:{margin:0} },
        h("label", null, "Notify via"),
        h("select", { value:form.channel,
                      onChange: e => setForm(f=>({...f,channel:e.target.value})) },
          CHANNELS.map(c => h("option",{key:c.value,value:c.value},c.label))),
      ),
      h("button", { type:"submit", className:"btn-primary" }, "Add"),
    ),
    h("div", { style:{background:"var(--surface)",border:"1px solid var(--border)",
                       borderRadius:"var(--r-lg)",overflow:"hidden"} },
      rules.map(rule =>
        h("div", { key: rule.id, className: "alert-rule", style: { padding: "10px 16px" } },
          h("label", { className: "toggle", title: rule.enabled ? "Enabled" : "Disabled" },
            h("input", { type:"checkbox", checked: rule.enabled,
                         onChange: () => toggle(rule) }),
            h("span", { className: "toggle__slider" }),
          ),
          h("div", { className: "alert-rule__label" },
            h("div", { style:{fontWeight:500} }, rule.label),
            h("div", { className: "text-xs text-muted" },
              `${rule.metric} ${rule.operator} ${rule.threshold}`),
          ),
          h("span", { className: "badge badge--pending alert-rule__channel" }, rule.channel),
          h("button", { className: "btn-danger", onClick: () => del(rule.id) }, "Delete"),
        )
      ),
      rules.length === 0 && h("div", {
        style:{textAlign:"center",padding:24,color:"var(--text-3)"}},
        "No alert rules yet — click Add Rule to create one"),
    ),
  );
}
