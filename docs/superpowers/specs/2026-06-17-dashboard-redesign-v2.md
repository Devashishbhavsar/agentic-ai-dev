# Dashboard Redesign v2 — Design Spec
**Date:** 2026-06-17  
**Status:** Approved for implementation  
**Replaces:** `2026-06-17-mission-control-dashboard-design.md`

---

## 1. Overview

A complete rebuild of the OpenClaw dashboard from the current dark ops-console aesthetic to a clean **Enterprise Light** design (white/indigo, Linear/Notion feel). The new dashboard adds full agent visibility across all 35 agents, an org chart with two view modes, parallel-agent workflow detail, system monitoring, analytics, and configurable alerts.

### Goals
- Professional, readable UI that works in a bright office environment
- Every agent visible — all 35 across 7 swarms, with status at a glance
- Org chart showing agent hierarchy and live collaboration
- Parallel agent timeline + chat feed for workflow drill-down
- System health and Discord/OpenClaw/OpenRouter status always visible
- Configurable alert rules with Discord notification support

---

## 2. Visual Design System

### Palette
| Token | Value | Usage |
|---|---|---|
| `--bg` | `#f8fafc` | Page background |
| `--surface` | `#ffffff` | Cards, panels |
| `--border` | `#e2e8f0` | All borders |
| `--text` | `#0f172a` | Primary text |
| `--text-2` | `#475569` | Secondary text |
| `--text-3` | `#94a3b8` | Muted/placeholders |
| `--accent` | `#6366f1` | Indigo — primary accent, active tab underline |
| `--accent-bg` | `#eef2ff` | Indigo tint for tags/badges |
| `--green` | `#16a34a` | Active/success states |
| `--green-bg` | `#dcfce7` | Active state backgrounds |
| `--amber` | `#f59e0b` | Warnings |
| `--red` | `#ef4444` | Errors/failures |

### Swarm Colours (top-border accent on swarm cards)
| Swarm | Colour | Hex |
|---|---|---|
| BI | Indigo | `#6366f1` |
| QA | Amber | `#f59e0b` |
| DevOps | Emerald | `#10b981` |
| SW Eng | Pink | `#ec4899` |
| AI Eng | Violet | `#8b5cf6` |
| Data Eng | Cyan | `#06b6d4` |
| Release | Orange | `#f97316` |

### Typography
- Font: `Inter, system-ui, sans-serif`
- Mono: `'IBM Plex Mono', monospace` (for IDs, timestamps, code)
- Base size: 14px
- Tab labels: 13px, font-weight 500
- KPI values: 28px, font-weight 700

### Component Patterns
- Cards: `border-radius: 10px`, `border: 1px solid var(--border)`, `box-shadow: 0 1px 3px rgba(0,0,0,0.06)`
- Badges: `border-radius: 20px`, `padding: 2px 8px`, small caps 11px
- Active agent indicator: `box-shadow: 0 0 0 2px #16a34a` pulse animation
- Tab active underline: `2px solid var(--accent)` bottom border
- Hover state on cards: `background: #f8fafc`, `border-color: #c7d2fe`

---

## 3. Layout Structure

### Persistent Top Status Bar
Pinned across every tab. Single row, light grey background (`#f1f5f9`), 36px tall.

Left side — breadcrumb: `OpenClaw / Control Plane`  
Centre — 4 status pills (click to expand tooltip):
1. **Gateway** — `● live  v2026.6.5` or `● offline`
2. **Discord** — `● connected` or `● disconnected  last: 2m ago`
3. **Agent Service** — `● running  uptime: 2d 4h` or `● stopped`
4. **OpenRouter** — `● ok` or `⚠ low credits` or `✗ invalid key`

Right side — update badge (only shown when update available): `⬆ v2026.6.8 available`

### Top Tab Navigation
Full-width tab bar below the status bar. 7 tabs:
```
Overview  |  Agents  |  Org Chart  |  Workflows  |  History  |  System  |  Settings
```
Active tab: indigo `2px` bottom border, indigo text. Inactive: `--text-3`, hover `--text-2`.

---

## 4. Tab Specifications

### Tab 1 — Overview

**KPI Row** — 5 cards in a horizontal strip:
1. Active Workflows (value + "N agents busy" sub-label)
2. Agents Busy (value + swarm breakdown sub-label e.g. "3 bi · 2 devops")
3. Cost Today (USD with 4dp + "N ms avg latency" sub-label)
4. Model Calls (count + "Cache hit N%" sub-label with sparkline)
5. Cache Hit Rate (percentage + 7-day trend sparkline)

**OpenRouter Health Card** — below KPI row, full width, collapsed by default, amber border when warning:
- Key status (masked: `sk-or-v1-0db4...`), validity indicator
- Daily spend progress bar (spend / estimated limit)
- Rate limit window indicator

**Two-column content area** (60 / 40 split):

*Left — Active Workflows list:*
- Each workflow: request text (truncated to 60 chars), pipeline badge (colour-coded), elapsed time, agent count, status badge
- Empty state: "No active workflows — use the demo button or send a message via Discord"
- Below workflow list: **7-day Cost Bar Chart** — one bar per day, stacked by pipeline type

*Right — Live Event Feed:*
- Real-time WebSocket stream, max 50 events displayed, newest at top
- Each event: coloured type badge (`agent_started`, `model_call`, `agent_finished`, `workflow_finished`), agent name, swarm tag, timestamp
- Colour-coded by originating swarm (matching swarm colour palette)
- Auto-scroll toggle (pauses scroll when user scrolls up manually)

---

### Tab 2 — Agents

**Header row:** "35 agents across 7 swarms" + search input (filters agent tags across all cards)

**7 Swarm Cards** in a responsive grid (3 cols desktop, 2 cols tablet, 1 col mobile):

Each card:
- Coloured top border (3px, swarm colour)
- Header: swarm name (bold) + agent count badge + active count badge (green glow when >0)
- Agent tags: all agents listed as clickable chips. Active agents: green background + `●` dot. Idle: default style.
- Card hover: border colour shifts to swarm colour

**Agent Detail Slide-over Panel** (triggered by clicking any agent tag or swarm card header):
- Slides in from right, 380px wide, overlay backdrop
- Header: agent name, swarm badge, status indicator
- **Info section** (read-only): description, role, pipeline(s) it participates in
- **Config section** (editable, collapsible):
  - System prompt (textarea, 4 rows)
  - Model tier selector (planning / balanced / fast / long-context)
  - Max tokens (number input)
  - Save button → POST to `/v1/agents/{name}/config` — persists overrides to `data/agents/{name}.json`; the agent base class loads this override at runtime if the file exists, falling back to the Python-defined defaults
- **Stats section**: total runs, avg latency (ms), total cost (USD), last active timestamp
- **Recent Activity**: last 10 events this agent fired (type, workflow ID, timestamp)
- Close button (X) or click backdrop to dismiss

---

### Tab 3 — Org Chart

**View toggle** (top-right of tab): `[🌳 Hierarchy]  [🕸 Network]`

**Hierarchy Tree view** (default):
- Rendered as SVG (inline, no external library)
- Root node: "OpenClaw Orchestrator" (indigo, large)
- Level 2: 7 swarm nodes (colour-coded circles, swarm name label)
- Level 3: agent nodes (smaller circles, agent name label, swarm colour border)
- Active agents: green pulsing ring animation
- Click any node → Agent Detail Slide-over Panel (same as Agents tab)
- Zoom in/out controls (+ / - buttons, scroll to zoom)

**Network / Force Graph view**:
- `d3-force` (bundled, ~12kb) for physics simulation; nodes and edges rendered as SVG
- Agents as labelled bubbles clustered by swarm, swarm label in centre of cluster
- Swarm clusters colour-coded
- **Live workflow edges**: when a workflow is active, directed arrows animate between agents that have handed off (data from `workflow_connections` API)
- Edge thickness = recency (thicker = more recent)
- Zoom and pan supported (mouse drag + scroll)
- Click any bubble → Agent Detail Slide-over Panel
- Legend: swarm colour key, edge meaning

Both views share the same Agent Detail Slide-over Panel component.

---

### Tab 4 — Workflows

**Top section — Kanban Board** (same 5-column structure as current):
Inbox → Assigned → In Progress → Review → Done

Each card:
- Workflow request (truncated), pipeline badge, duration, status badge
- Click → selects card and populates the Workflow Detail section below
- Done column: scrollable with max-height

**Search + filter bar** above the board: text filter by agent/pipeline/stage

**Bottom section — Workflow Detail** (appears on card selection):
Two panels side by side (50/50 split):

*Left — Timeline / Gantt:*
- One horizontal lane per agent that participated
- Time axis (seconds elapsed) across the top
- Completed bars: solid swarm colour
- Running bar: animated shimmer/pulse in swarm colour
- Waiting bars: grey `#e2e8f0`
- Parallel agents show overlapping time windows clearly
- Hover on a bar: tooltip with agent name, start time, end time, tokens used
- When no workflow selected: "Select a workflow card above to inspect its timeline"

*Right — Agent Chat Feed:*
- Chronological feed, oldest at top
- Each message: avatar circle (agent initials, swarm colour background), agent name, timestamp, message content (from agent trace/summary)
- Active agent shows "typing…" indicator (animated dots)
- Messages sourced from `recent_traces` and `recent_events` filtered by workflow ID
- Scrollable, max height matches the Gantt panel

---

### Tab 5 — History

**Filters bar**: date range picker, pipeline type filter, status filter (success / failed / running)

**Runs table** — sortable by any column:
| Request | Pipeline | Status | Duration | Model Calls | Cost | Timestamp |

Clicking a row → expands inline (accordion) showing the same Workflow Detail view (Gantt + Chat Feed) as Workflows tab, read-only mode.

**Analytics panels** below the table (two side-by-side):

*Model Performance Table:*
| Model | Calls | Avg Latency | Avg Cost | Success Rate |

*7-day Cost Bar Chart:*
- One bar per day, stacked by pipeline type (bi, devops, general, etc.)
- Colour matches pipeline colours
- Y-axis in USD

---

### Tab 6 — System

Four sections:

**Services** (top, full width):
| Service | Status | PID | Uptime | Restarts | Last Restart | Actions |
|---|---|---|---|---|---|---|
| enterprise-agent | ● running | 1234 | 2d 4h | 0 | Jun 15 11:48 | [Restart] |
| openclaw-gateway | ● running | 1235 | 2d 4h | 2 | Jun 16 08:43 | [Restart] |

Restart button → calls `systemctl --user restart <service>` via `/v1/system/restart` API endpoint.

**Resources** (two-column):
- Left: CPU % gauge (live, refreshes every 5s), Memory bar (used / total MB)
- Right: Disk usage table — vector store path + size, cache dir + size, log dir + size

**OpenRouter** (card):
- API key: `sk-or-v1-0db4...` (masked), [Test Connection] button — fires `GET /v1/system/openrouter-check` which attempts a minimal API call
- Status: valid / invalid / rate-limited (derived from last API call result stored in runtime)
- Daily spend: total cost from `model_router` call log (source of truth, no external API needed)
- Avg latency: rolling average across all model calls today

**Discord** (card):
- Bot connection: ● connected / ● disconnected
- WebSocket session uptime
- Last message received: timestamp + truncated content
- Messages handled today: count
- Gateway WebSocket reconnects today: count (from logs)

---

### Tab 7 — Settings / Alerts

**Alert Rules** — list of configurable threshold rules. Each rule:
- Toggle (on/off)
- Description (editable label)
- Condition (metric dropdown + operator + threshold value)
- Notification channel (Discord / dashboard banner / both)
- [Delete] button

**Default rules** (pre-configured, off by default):
1. Daily cost > $1.00 → Discord + banner
2. Avg latency > 10,000ms → banner
3. Agent failure count > 3 in 1h → Discord + banner
4. OpenRouter credits < $2.00 → Discord + banner
5. Any service stopped → Discord + banner

**Add Rule** button — opens a form inline.

Alert state is persisted to `data/alerts/rules.json`.

---

## 5. Data Sources

All data served from existing `/v1/dashboard` WebSocket endpoint plus new REST endpoints:

| Data | Current source | New endpoint needed? |
|---|---|---|
| KPIs, events, runs, model usage | `/v1/dashboard` WS | No |
| Agent config (read) | None | Yes — `GET /v1/agents/{name}` |
| Agent config (write) | None | Yes — `POST /v1/agents/{name}/config` |
| Service status | None | Yes — `GET /v1/system/status` |
| Service restart | None | Yes — `POST /v1/system/restart` |
| System resources (CPU/mem/disk) | None | Yes — `GET /v1/system/resources` |
| Discord stats | None | Yes — `GET /v1/system/discord` (reads gateway logs) |
| Alert rules (read/write) | None | Yes — `GET/POST /v1/alerts/rules` |
| Org chart static data | None | Derived from `agents/` directory at startup |

---

## 6. New Backend Endpoints Required

```
GET  /v1/agents                        List all agents with metadata
GET  /v1/agents/{name}                 Get single agent config + stats
POST /v1/agents/{name}/config          Update agent config (prompt, tier, tokens)

GET  /v1/system/status                 Service health (both systemd units)
POST /v1/system/restart                Restart a service by name
GET  /v1/system/resources              CPU %, memory MB, disk usage (uses psutil)
GET  /v1/system/discord                Discord bot stats parsed from journald logs
GET  /v1/system/openrouter-check       Test OpenRouter key validity (makes minimal API call)

GET  /v1/alerts/rules                  List alert rules
POST /v1/alerts/rules                  Create/update alert rule
DELETE /v1/alerts/rules/{id}           Delete rule
```

---

## 7. Frontend Architecture

Single-page React app (no JSX, same build pipeline as current).

**File structure:**
```
web/dashboard/
  app.js              Main App component + routing
  styles.css          Full design system
  components/
    StatusBar.js       Persistent top status bar
    TabNav.js          Tab navigation
    Overview.js        Overview tab
    Agents.js          Agents tab + AgentDetailPanel
    OrgChart.js        Org chart tab (Tree + Network)
    Workflows.js       Workflows tab (Kanban + Detail)
    History.js         History tab + analytics
    System.js          System tab
    Settings.js        Settings/Alerts tab
    shared/
      KpiCard.js
      SwarmCard.js
      GanttTimeline.js
      AgentChatFeed.js
      MiniChart.js
  app.bundle.js       Built output
```

State management: React `useState` + `useReducer` for shared state. WebSocket hook unchanged from current implementation. No external state library needed.

---

## 8. Scope Boundaries

**In scope:**
- Full frontend rebuild (all 7 tabs)
- New backend API endpoints listed above
- WebSocket data already sufficient for most real-time features

**Out of scope:**
- Mobile-native app
- User authentication / multi-user access control
- Agent config changes do not hot-reload running workflows (takes effect on next workflow start)
- Email notifications (Discord only)
- Historical data beyond what runtime already stores in memory

---

## 9. Success Criteria

- [ ] All 35 agents visible on the Agents tab with correct swarm grouping and colour coding
- [ ] Org Chart renders both Tree and Network views, active agents pulse
- [ ] Workflow detail shows Gantt timeline + agent chat feed for any selected run
- [ ] System tab shows live CPU/memory and both service statuses with restart capability
- [ ] Top status bar always shows Gateway, Discord, Agent Service, and OpenRouter state
- [ ] Alert rules can be created, toggled, and trigger a Discord message when threshold crossed
- [ ] All existing dashboard functionality (KPIs, board, history) preserved
- [ ] Page loads in < 2s, WebSocket reconnects automatically
