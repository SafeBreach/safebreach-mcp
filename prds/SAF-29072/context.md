# SAF-29072 Context

**Ticket ID**: SAF-29072
**Title**: [safebreach-mcp] Add ability to filter simulations by the tracking id
**Branch**: `SAF-29072-filter-simulation-by-tracking-id`
**Status**: Phase 3: Create Working Branch and PRD Context

---

## Ticket Summary

**Type**: Task
**Status**: To Do
**Assignee**: Yossi Attas
**Reporter**: Yossi Attas
**Priority**: Medium
**Created**: Mar 12, 2026

### Description

The MCP Data Server exposes a `drift_tracking_code` field (mapped from `originalExecutionId`) on every
simulation record. This identifies a simulation lineage — same attack configuration across test runs.
However, agents cannot query simulations by this tracking code, making it impossible to trace the full
execution history of a drifting simulation.

### Gaps Identified

1. `get_test_simulations` has no `tracking_code` filter parameter
2. No cross-test-run lineage query — `get_simulation_details` only finds one previous version
3. `drift_tracking_code` is response-only, not documented as a first-class concept

### Acceptance Criteria

- `get_test_simulations` accepts an optional `tracking_code` filter parameter
- A new tool or mode enables cross-test-run lineage tracing by tracking code
- `drift_tracking_code` documented in tool docstrings as a first-class concept
- Unit tests cover the new filter path
- E2E tests verify lineage tracing against a real console

### Related Tickets

- SAF-28331 — Security Control Drift API (introduced `drift_tracking_code` in SC drift context)
- SAF-28330 — Simulation Result/Status Drift tools (use `trackingId` in drill-down responses)

---

## User Requirements (from conversation)

1. **Continuous drift analysis flow** — agent should seamlessly go from drift discovery to simulation
   lineage tracing without manual correlation
2. **Consistent terminology** — `drift_tracking_code` must be named and described consistently across
   all tool docstrings
3. **Agent-friendly descriptions** — tool docs should explain what the tracking code means, when to
   use it, and how it connects to the drift analysis workflow
