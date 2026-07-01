# PRD: Helm concludes "none are ready to run" from one page of scenarios — SAF-32210

## 1. Overview

| Field | Value |
|-------|-------|
| **Title** | Steer the agent to `ready_to_run_filter` so it stops concluding "no scenarios are ready" from a single page |
| **JIRA** | SAF-32210 |
| **Task Type** | Bug |
| **Component** | `safebreach_mcp_config` (Config Server) |
| **Purpose** | Asked to "run any scenario", Helm calls `get_scenarios`, sees page 0 (10 of N) with no ready-to-run scenarios, and concludes none are ready — instead of paging or filtering for the ready ones that exist on other pages. |

## 1.5. Document Status

| Field | Value |
|-------|-------|
| **PRD Status** | Implemented |
| **Last Updated** | 2026-06-29 |
| **Branch** | `feature/SAF-32210` |

## 2. Solution Description

### Root cause

`get_scenarios` returns 10 scenarios per page ordered by name. The `ready_to_run_filter` parameter already exists and works (`config_types.filter_scenarios_by_criteria`), but nothing steered the agent toward it, and the only `hint_to_agent` was "scan next page". When the first page happens to contain no ready-to-run scenarios (common — ready ones are scattered across pages by name order), the agent generalizes "page 0 has none" to "the catalog has none" and gives up.

### Chosen Solution

Make the response *tell the agent the truth about the whole result set*: when `ready_to_run_filter` was not applied and ready-to-run scenarios exist beyond the current page, `paginate_scenarios` adds a deterministic hint — e.g. *"86 of 547 scenarios are ready to run as-is (simulators already assigned). You can run the others too — for a scenario that is not ready, run_scenario returns a diagnostic and you supply per-step simulator selection (step_overrides) to run it. To list only the ready-to-run ones, call get_scenarios with ready_to_run_filter=True."* The `get_scenarios` tool description warns against concluding readiness from one page and clarifies that ready-to-run is a **convenience, not a prerequisite** — non-ready scenarios remain runnable via `step_overrides`.

**Deliberately balanced** (per review): the hint must not discourage the agent from running non-ready scenarios. Running a non-ready scenario is a first-class, supported flow (`run_scenario`'s two-turn diagnostic → `step_overrides` path), so the guidance surfaces the ready count without framing ready-to-run as the only runnable set.

Computed from `is_ready_to_run` (already present on every reduced scenario), so no extra API calls. Fires only when `ready_total > ready_shown` (there are ready scenarios the agent can't see on this page) and the filter wasn't already applied.

### Alternatives Considered

| Option | Why not chosen |
|--------|----------------|
| Generic "you can filter by ready_to_run_filter" hint | Weaker — doesn't tell the agent ready scenarios actually exist, so it may still give up. The count is the decisive signal. |
| Tool-description change only | The agent already had the param documented and ignored it; a per-response hint with a concrete count is what changes behavior. |
| Re-order results to put ready-to-run first | Larger behavior change affecting all callers/ordering; the hint is targeted and preserves existing ordering semantics. |

## 3. Core Feature Components

- **`config_types.py`** — `paginate_scenarios` gains `ready_to_run_filter_applied: bool`; emits the ready-to-run hint when not applied and ready scenarios exist beyond the current page.
- **`config_functions.py`** — `sb_get_scenarios` passes `ready_to_run_filter_applied=(ready_to_run_filter is not None)`.
- **`config_server.py`** — `get_scenarios` description steers to `ready_to_run_filter` and warns against single-page conclusions.

## 4. API Endpoints and Integration

No new endpoints. Uses the existing `is_ready_to_run` field already computed on each scenario.

## 5. Tests

`test_config_types.py::TestPaginateScenarios` — hint fires when ready scenarios exist beyond the page; no hint when the filter was applied, when all ready scenarios are already shown, or when none are ready.

## 6. Verification

- **Function-level (pentest01):** no-filter page 0 returns the hint "86 of 547 scenarios are ready to run as-is … you can run the others too (step_overrides) … ready_to_run_filter=True"; `ready_to_run_filter=True` returns no nudge.
- **Agent E2E (Claude Desktop):** on `flat-carp` (page 0 has 0 ready, 14 ready total — the original-bug shape), Helm now finds the 14 ready scenarios and runs one instead of concluding "none are ready". pentest01 confirms no regression.

## 7. Definition of Done

- `get_scenarios` surfaces ready-to-run availability so the agent runs a ready scenario instead of giving up. ✅
- No extra API calls; ordering/filter semantics unchanged. ✅
- Config suite green. ✅
