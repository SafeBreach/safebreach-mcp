# SAF-29072 Context

**Ticket ID**: SAF-29072
**Title**: [safebreach-mcp] Add ability to filter simulations by the tracking id
**Branch**: `SAF-29072-filter-simulation-by-tracking-id`
**Status**: Phase 5: Brainstorm

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

---

## Investigation Findings

### 1. drift_tracking_code Field Mapping

- **API field**: `originalExecutionId` → **MCP field**: `drift_tracking_code`
- Defined in `data_types.py:32` via `reduced_simulation_results_mapping`
- Included in every reduced simulation entity via `get_reduced_simulation_result_entity()`
- **Not always present**: `map_reduced_entity()` (line 62) skips missing fields — simulations
  without `originalExecutionId` won't have `drift_tracking_code` in the response
- Identifies **simulation lineage** — same attack configuration across test runs

### 2. Current Filtering Architecture

**All filtering is client-side, post-fetch.** The pipeline:
```
API fetch (all sims for test) → transform → cache → filter → paginate → return
```

- `_get_all_simulations_from_cache_or_api()` fetches ALL simulations for a test_id
- `_apply_simulation_filters()` applies filters in-memory (lines 731-786)
- Existing filter patterns:
  - **Exact match**: `playbook_attack_id_filter` → `s.get('playbook_attack_id') == filter`
  - **Partial match**: `playbook_attack_name_filter` → case-insensitive `in` check
  - **Boolean**: `drifted_only` → checks `is_drifted` field
  - **Range**: `start_time`/`end_time` → numeric comparison

Adding `tracking_code` follows the **exact match** pattern (like `playbook_attack_id_filter`).

### 3. get_simulation_details Internal Lineage Query

In `data_functions.py:863-890`, when `include_drift_info=True`:
```python
drift_code = return_details['drift_info']['drift_tracking_code']
query = f'originalExecutionId:("{drift_code}") AND !id:{simulation_id}'
# Uses runId: "*" — searches across ALL test runs
```

- The SafeBreach API **does support** server-side ES queries by `originalExecutionId`
- Currently only used to find the single most recent previous simulation
- Returns `previous_simulation_id` and `previous_test_id`

### 4. Tool Docstring Terminology Audit

| Tool | Mentions drift_tracking_code? | Mentions lineage? |
|------|-------------------------------|-------------------|
| `get_test_simulations` | No | No |
| `get_simulation_details` | Indirectly ("drift analysis") | No |
| `get_test_drifts` | Yes (line 256-263) | No |
| `get_simulation_result_drifts` | No | No |
| `get_simulation_status_drifts` | No | No |
| `get_security_control_drifts` | No | No |

The concept is poorly formalized — agents don't know they can use it for correlation.

### 5. Key Implementation Considerations

- **Field presence**: Must handle simulations without `drift_tracking_code` (skip, no match)
- **Match semantics**: Exact match (tracking codes are opaque identifiers)
- **Scope**: Filter within a single test run (consistent with `get_test_simulations` scope)
- **Cross-test lineage**: Out of scope for this approach — would need a separate tool/mode
- **Performance**: Client-side filtering on cached data, negligible overhead
- **Docstring updates**: All drift-related tools should mention `drift_tracking_code` as a
  correlation field and explain the investigation workflow

---

## Brainstorm: Chosen Approach

### Scope Pivot

Original scope was filtering within a single test (`get_test_simulations`). After analysis, within-test
filtering provides limited value for drift investigation because drifts commonly occur **across** test
runs. The real need is **cross-test lineage tracing**.

### Approaches Considered

| Approach | Description | Verdict |
|----------|-------------|---------|
| A: New `get_simulation_lineage` tool | Dedicated tool, server-side ES query by tracking code | **Selected** |
| B: Extend `get_test_simulations` with `test_id=*` | Overload existing tool with wildcard | Rejected — muddies tool semantics |
| C: Enhance `get_simulation_details` drift info | Return full lineage in details response | Rejected — mixes single/multi entity patterns |

### Selected: Approach A — `get_simulation_lineage`

**Why this is best for the calling LLM:**
1. **Discoverable**: Agent sees `drift_tracking_code` → naturally searches for a tool that accepts it
2. **Single-purpose**: Each drift tool has clear scope — lineage tool follows this pattern
3. **No conditional rules**: No "use test_id=* only when tracking_code_filter is set"
4. **Response shape matches intent**: Chronological list of executions, not overloaded details

**Implementation approach:**
- Uses existing API: `POST /executionsHistoryResults` with `runId: "*"` and
  `query: originalExecutionId:("{code}")`
- Paginated response ordered by execution time (oldest first for chronological timeline)
- Each record includes: simulation_id, test_id, test_name, status, execution_time,
  security control info
- Docstring cross-references from all drift tools to complete the workflow loop

**Docstring updates (all 6 drift tools):**
- Formalize `drift_tracking_code` as a first-class concept
- Add workflow hints: "Use drift_tracking_code to trace full lineage via get_simulation_lineage"
- Consistent terminology across all tools
