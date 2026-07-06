# SAF-33124 — get_test_drifts: compare any two test runs with join options

## Proposed Title
[safebreach-mcp] get_test_drifts: support comparing any two test run IDs with configurable join options

## Problem
`get_test_drifts` can only compare a test against its **auto-selected** most-recent prior run
with the same name (`data_functions.py:1774–1815`). It cannot compare two **arbitrary /
non-consecutive** runs. It also always emits exclusive (outer) simulation lists and never filters
no-result simulations, so callers can't scope the comparison down to a clean signal. In a Travelers
support case this forced the agent to manually traverse all simulation results to build a custom
two-run comparison, burning significant tokens.

## Goal
Extend `get_test_drifts` (backward-compatible signature) so an agent can compare two specific test
runs and control the breadth of the join in one call.

## Solution Approach
Add four optional parameters to `get_test_drifts_tool` (`data_server.py`) and thread them into
`sb_get_test_drifts` (`data_functions.py`):

1. **`second_test_id`** (optional) — the run to compare against.
   - Omitted → current auto-baseline behavior unchanged (most-recent prior same-name run).
   - Provided → **skip auto-selection entirely**; compare exactly the two ids. `test_id` = left
     (first/baseline), `second_test_id` = right (second/current), regardless of names or dates.
2. **`include_outer_left`** (default `False`) — include sims only in the first run.
3. **`include_outer_right`** (default `False`) — include sims only in the second run.
4. **`include_no_results`** (default `False`) — include sims with no-result (`internal_fail`) status.

**Default = inner join, no-results excluded** (adopts the ticket's stated defaults). This is a
deliberate response-content change for existing single-arg callers (outer lists + no-result
transitions no longer appear by default).

**`hint_to_agent` must state the applied filtering** — which joins/statuses were excluded — so the
calling agent can re-invoke with the flags enabled to widen the investigation.

Implementation lands in the existing join block (`data_functions.py:1836–1890`): gate the
already-computed `baseline_only` / `current_only` emission behind the outer flags, and filter
no-result sims (by normalized `internal_fail`/`no_result` status) from both inner and outer sets
unless `include_no_results=True`.

## Acceptance Criteria
1. `get_test_drifts(test_id)` with no new args behaves as today **except** default output is now
   inner-join-only with no-results excluded, and `hint_to_agent` documents the applied filtering.
2. `get_test_drifts(test_id, second_test_id=X)` compares exactly those two runs with no
   auto-baseline selection, name matching, or time-ordering assumptions.
3. `include_outer_left=True` adds first-run-only sims; `include_outer_right=True` adds
   second-run-only sims; both default off.
4. `include_no_results=True` includes `internal_fail`/no-result sims in the comparison; default off.
5. `hint_to_agent` reflects exactly which filters were applied and how to widen them.
6. Degenerate/edge cases handled: same id twice, second id older than first, differing test names,
   nonexistent second id — no crash, clear behavior.
7. `readOnlyHint=True` preserved; no rate-limiting gate needed.
8. Unit tests cover: explicit second id, each join flag independently and combined, no-result
   filtering, and backward-compatible auto-baseline path. Docstring + `CLAUDE.md` updated.

## Out of Scope
- Changes to the time-window drift tools (`get_simulation_result_drifts`, `get_simulation_status_drifts`).
- Caching the join result (raw per-test sim lists remain cached as today).
- Cross-console comparison semantics beyond passing a single `console`.
