# Mission Control Dashboard Design

**Date:** 2026-06-17

**Goal:** Redesign the existing `/dashboard` surface into a live mission board that makes active workflows, agent presence, and agent-to-agent communication immediately visible.

## Problem

The current dashboard has the right raw data, but the visual hierarchy is weak:

- The hero area dominates the page even when no useful activity is shown.
- Active work is spread across multiple panels, so it is not obvious what is happening now.
- Agent coordination is implicit in traces and events rather than visible in the main surface.
- The empty-state experience feels inert instead of like a waiting command center.

## Design Direction

The dashboard should feel like a live operations board, not a generic analytics page.

The chosen direction is:

- `Live mission board` as the primary mental model
- `Conversation ribbons` as the inter-agent communication model
- Dense but readable information layout
- Visual motion used to signal activity, handoff, and recency

## User Experience

When the user opens the dashboard, they should immediately be able to answer:

1. Is the system live?
2. Which workflows are active right now?
3. Which agents are currently working?
4. Which agent handed work to which other agent?
5. Where is the bottleneck or approval gate?

The page should reward scanning in under five seconds and deeper inspection in under thirty seconds.

## Layout

The redesign keeps a three-zone shell but changes hierarchy.

### Left Rail

Purpose: compact system context and controls.

Content:

- stream health
- launch demo action
- queue/load summary
- compact alert list
- compact “recent signal” counters

This rail should feel like a control strip, not a content column.

### Center Surface

Purpose: the main mission board.

Content:

- a condensed command header instead of a large editorial hero
- one primary workflow board showing active cards first
- lane groupings by workflow stage
- active card emphasis through glow, pulse, and recency treatment
- visible handoff links between agents within the selected workflow

This is the core of the redesign. Most of the screen should belong to active work.

### Right Rail

Purpose: live diagnostics for the selected workflow.

Content:

- selected workflow summary
- conversation ribbon ledger
- agent trace feed
- model pressure and alert stack

This rail should explain why the center board is changing, not compete with it.

## Communication Model

Agent coordination should be visible through `conversation ribbons`.

### What a Ribbon Represents

A ribbon is a lightweight handoff between two agents in the same workflow. It represents:

- `plan`
- `handoff`
- `review`
- `verify`
- `block`

### How It Is Derived

The existing runtime already has:

- `active_agents`
- `recent_events`
- `recent_traces`

The dashboard layer should derive communication edges from ordered workflow activity:

- sequential agent starts after another agent’s finish
- explicit trace or event adjacency inside a workflow
- latest active agent context for a selected workflow

The first version should be derived client-side or in the dashboard snapshot with no schema migration.

### How It Appears

- thin animated connectors between visible active cards
- compact label on the connector
- short-lived pulse animation for very recent handoffs
- mirrored text list in the right rail for readability and mobile fallback

## Component Model

The redesign should keep the current plain React bundle approach, but split the screen into clearer display units inside `web/dashboard/app.js`.

Recommended logical units:

- `CommandHeader`
- `SystemRail`
- `MissionBoard`
- `WorkflowCard`
- `ConversationRibbonLayer`
- `ConversationLedger`
- `WorkflowDetails`
- `LiveTracePanel`
- `ModelPressurePanel`

This can remain in one file for now if needed, but responsibilities should be made explicit through helper functions and localized render blocks.

## Data Requirements

The redesign should not require a backend rewrite, but the runtime snapshot should expose a derived dashboard-specific section for communication if it simplifies the client.

Preferred additions to the dashboard payload:

- `task_board`
- `workflow_connections`
- `selected_workflow_summary` only if it reduces repeated client computation

If `workflow_connections` is added, each item should include:

- `workflow_id`
- `from_agent`
- `to_agent`
- `signal`
- `timestamp`
- `status`

## Motion

Motion should communicate state rather than decorate it.

Use:

- gentle page-load stagger
- pulse on currently active cards
- quick connector sweep on recent handoffs
- shimmer or recency edge on cards updated in the last few seconds

Avoid:

- constant unrelated animation
- excessive floating or parallax
- motion that obscures readability

## Empty State

The empty state should still feel operational.

Instead of a large dead block, show:

- dormant board lanes
- a waiting signal line
- a concise explanation of what will appear when the first workflow starts
- a visible demo-launch action

The user should feel the system is armed, not blank.

## Error Handling

If websocket updates degrade:

- preserve the last good snapshot
- downgrade the stream indicator clearly
- keep the board visible
- show a compact reconnect banner rather than replacing the page

If communication edges cannot be derived:

- render the board normally
- hide connectors
- keep the right-rail conversation ledger in a degraded informational state

## Testing

The redesign should be covered at two levels.

### Runtime/API Tests

- dashboard snapshot includes any new connection payload
- empty-state snapshots still serialize correctly
- demo workflow produces at least one derived communication edge

### Frontend Verification

- bundle builds cleanly
- page renders with empty and active states
- mobile layout remains readable
- selection of workflows and agents still works

## Scope Boundaries

In scope:

- visual hierarchy redesign
- mission-board-first layout
- visible agent handoffs
- improved empty state
- stronger live activity cues

Out of scope:

- replacing the React bundle system
- adding a new frontend framework
- real chat between agents beyond derived runtime visibility
- Discord-native dashboard rendering

## Acceptance Criteria

The redesign is complete when:

1. The dashboard shows active workflows as the dominant content.
2. Active agents are visually distinguishable from idle or completed work.
3. Agent-to-agent handoffs are visible in the UI.
4. The empty state feels intentional and operational.
5. The page builds cleanly and the dashboard tests continue to pass.
