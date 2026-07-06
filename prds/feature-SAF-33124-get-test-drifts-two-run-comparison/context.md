# Context: SAF-33124 — get_test_drifts two-run comparison + join options

**Status:** Phase 5: Problem Analysis Complete
**Mode:** Improve existing ticket
**Ticket:** [SAF-33124](https://safebreach.atlassian.net/browse/SAF-33124) — Task, Medium, Reporter: Yossi Attas
**Branch:** `feature/SAF-33124-get-test-drifts-two-run-comparison`
**Repo:** `/Users/yossiattas/Public/safebreach-mcp` (Data Server)
**Scope decision (user):** Extend the existing `get_test_drifts` tool (backward-compatible), not a new tool.

## Ticket Ask

`get_test_drifts` should support comparing **any two arbitrary test run IDs** with comparison
(join) options. Motivated by a Travelers support case where the agent burned tokens manually
traversing simulation results to compare two non-consecutive runs.

Proposed options:
1. `include_outer_left` (default False) — simulations only in the first test run
2. `include_outer_right` (default False) — simulations only in the second test run
3. `include_no_results` (default False) — simulations with internal_fail (no-result) status

Default = inner join (only matching `original_tracking_id` across both runs), excluding no-results.

## Investigation Findings (Data Server)

### Tool definition
- `safebreach_mcp_data/data_server.py:297–316` — `@self.mcp.tool`, `readOnlyHint=True`.
  Handler `get_test_drifts_tool(test_id, console="default")` → calls `sb_get_test_drifts`.
  **No second test-id param, no join params today.**

### Business logic — `sb_get_test_drifts` (`data_functions.py:1738–1923`)
- Baseline is **auto-selected**: fetch current test details (`sb_get_test_details`) for
  `test_name` + `current_start_time`, then `sb_get_tests(name_filter, end_date=current_start_time,
  order desc)` → take `[0]`; fallback `_find_previous_test_by_name` linear scan (`:405–440`).
- **No explicit second-test-id path exists** — always most-recent prior run with same name.
- Simulations fetched via `_get_all_simulations_from_cache_or_api` → `POST
  /api/data/v1/accounts/{account_id}/executionsHistoryResults` (`:807–827`), called twice.

### Join / matching logic (`data_functions.py:1836–1890`)
- Correlation key = `drift_tracking_code` (mapped from raw `originalExecutionId`,
  `data_types.py:36`).
- Sims **without** a `drift_tracking_code` are silently dropped (`if drift_code:` gate `:1840,1845`).
- Set ops: `baseline_only`, `current_only` (outer), `shared` (inner). **Today outer sims are
  ALWAYS collected** into `_metadata.simulations_exclusive_to_baseline/current` — no opt-in.
- Status comparison only on `shared` codes; differing statuses → `drift_key` grouped via
  `drifts_metadata.drift_types_mapping`.
- **No-result / internal_fail: no filtering today** — passes through like any status;
  `drifts_metadata.py` has explicit `*-no_result` / `no_result-*` transition entries.

### Data transforms (`data_types.py`)
- `reduced_simulation_results_mapping:27–37`: `status`←`finalStatus`, `drift_tracking_code`←`originalExecutionId`.
- `group_and_enrich_drift_records:820–910` used by the **time-window** tools, not by `sb_get_test_drifts`
  (which does its own inline grouping).

### Related tools (different mechanism — not reusable directly)
- `sb_get_simulation_result_drifts` (`:2763`) and `sb_get_simulation_status_drifts` (`:2849`) are
  **time-window** based (`POST .../drift/simulationStatus`), not test-id based. No two-test/join semantics.

### Tests (`tests/test_data_functions.py:2295–2592+`)
- 8 tests for `sb_get_test_drifts`, all auto-baseline. Mock `sb_get_test_details`, `sb_get_tests`,
  `_find_previous_test_by_name`, `_get_all_simulations_from_cache_or_api`.
- None exercise explicit second test id, join options, or no-result scenarios.
- `test_drift_tools.py` covers only the time-window tools.

### Caching
- `simulations_cache` (maxsize=3, ttl=600), key `simulations_{console}_{test_id}{user_suffix}`
  (`:793`). Raw per-test sim lists cached; the drift join result is not cached.

## Problem Analysis

### Problem scope
Two coupled gaps: (a) **no way to pick the second run** — baseline is always auto-derived as the
most-recent prior same-name run, so comparing two *specific* / non-consecutive runs is impossible
via the tool; (b) **no control over join breadth** — outer (exclusive) sims are always emitted and
no-result sims are never filtered, so callers can't scope noise down to a clean inner join.

### Affected areas
- `data_server.py` tool signature + docstring (new optional params).
- `data_functions.py` `sb_get_test_drifts` — baseline resolution branch + join-emission gates.
- Tests in `test_data_functions.py`.
- `CLAUDE.md` tool docs (§ Drift Analysis / Data Server tool list).

### Key design tensions / risks
1. **Default behavior change.** Ticket wants default = inner join, exclude outer + no-results.
   Today the tool *always* includes outer sims and never filters no-results. Honoring the ticket
   defaults **changes existing output** for current single-arg callers (outer lists disappear,
   no-result transitions drop). Backward-compat call *signature* is preserved, but *response
   content* shifts. Needs explicit decision: adopt ticket defaults (behavior change) vs. keep
   current always-include behavior as default and treat flags purely additively.
2. **Param naming: first/second vs. baseline/current.** New second-test-id param name and
   which is "left"/"right" (outer_left = first, outer_right = second) must map cleanly onto the
   existing baseline(=left/first) vs current(=right/second) mental model. Ticket says "first" =
   the earlier/baseline, "second" = current.
3. **Optional second id + backward compat.** When second id omitted → keep auto-baseline
   behavior. When provided → skip auto-selection entirely (no name match, no time ordering
   assumptions — arbitrary runs may have different names).
4. **`include_no_results` semantics.** Confirm "no-result" = `internal_fail` status
   (ticket says so) and how it maps to normalized statuses (`no_result`/`internal_fail`). Decide
   whether it filters outer sims, inner sims, or both.
5. **Sims dropped for missing tracking code** — already silent; document, don't regress.

### Edge cases
- Two runs with different test names (allowed once id is explicit).
- Same id passed twice (degenerate — all shared, no drift).
- Second id older than first (which is "left"? define left=first-arg regardless of time).
- Second id nonexistent / different console.
- No-result-only differences vanishing when `include_no_results=False`.

### Dependencies
- None external; self-contained in Data Server. Reuses existing sim-fetch + cache path.
