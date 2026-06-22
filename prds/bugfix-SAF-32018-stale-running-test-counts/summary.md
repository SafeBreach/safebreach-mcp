# Summary: SAF-32018 (refined)

**Mode:** Improve existing ticket (Bug, High)
**Branch:** `bugfix/SAF-32018-stale-running-test-counts`
**Repo:** safebreach-mcp

## Proposed Title
HELM | `get_test_details` reports stale simulation status counts for a RUNNING test (sources the lagging `testsummaries.finalStatus` aggregate instead of live per-simulation data)

## Problem (refined)
When the agent is asked for a simulation status count (e.g. "Missed") on a test that is **still
running**, `get_test_details` returns a count that **lags the live UI** (reported 28 vs UI's 80).
The gap disappears once the test completes.

## Root Cause (empirically confirmed)
`get_test_details.simulations_statistics` is built from the SafeBreach **`testsummaries.finalStatus`
aggregate** (`data_types.py:82` ← `data_functions.py:235`). That aggregate is recomputed
lazily/periodically on the backend and **lags the live per-simulation results during an active
run**. The UI counts **live simulation rows** (the `executionsHistoryResults` source). The MCP
faithfully relays the lagging aggregate. The agent's "backend caching" remark is essentially
correct — it is genuine upstream aggregate lag.

**It is NOT the MCP's own cache:** `SB_MCP_CACHE_DATA` defaults to `false`, so the bug reproduces
with MCP caching off (every call hits `testsummaries` fresh and still returns the lagging number).
The `tests_cache` 1800s TTL only aggravates it when caching is explicitly enabled.

**It is NOT fixable by the existing SAF-31111 refresh at `data_functions.py:456`:** the orchestrator
queue (`queue_state.py:25`) carries only status (`RUNNING`/`PAUSED`), no counts; and the single-test
fallback endpoint shares the *same* lagging `finalStatus` aggregate.

## Empirical Evidence (TDD reproduction)
Live test `1782107855457.2` on pentest01, sampled every 5s across the full run:
- During RUNNING, live (`executionsHistoryResults`) consistently led the aggregate
  (`finalStatus`) — e.g. agg_missed=55 vs live=57; agg_total=64 vs live=68.
- At COMPLETED, both reconciled exactly (125/125 total, 94/94 missed).
- Validation on completed tests: aggregate == live (67 == 67) — confirms `executionsHistoryResults`
  counting is the correct live source.
- Scripts retained: `verify_lag.py`, `poll_lag.py` (PRD folder).

## Affected Areas
- **Primary:** `sb_get_test_details` / `_build_simulation_status_counts` count path for non-terminal
  tests (`data_functions.py:416`, `data_types.py:82`).
- **Secondary (same lag class, only when caching enabled):** `get_test_simulations` counts,
  findings counts, security-control events.

## Candidate Direction (for implementation, not finalized here)
For **non-terminal** tests, derive `simulations_statistics` from the **live** source
(`executionsHistoryResults`, already used by `sb_get_test_simulations`) instead of the lagging
`finalStatus` aggregate. Keep the cheap aggregate for **terminal** tests (where it has reconciled).
Surface that a running count is point-in-time (existing "poll again" hint).

## Acceptance Criteria (proposed)
1. For a **RUNNING** test, `get_test_details` returns per-status counts (missed/stopped/prevented/
   detected/logged/no-result/inconsistent) that match the live `executionsHistoryResults`-derived
   counts (the values shown in the UI filter), not the lagging `finalStatus` aggregate.
2. For a **terminal** test (completed/canceled/failed), behavior and counts are unchanged.
3. A regression test reproduces the bug: asserts running-test counts match the live source
   (fails on current code, passes after fix). Uses the SAF-31111 terminal/non-terminal detection.
4. Cost is only paid for non-terminal tests; terminal tests keep using the cheap aggregate.
5. The "test still running — poll again" hint is retained so the count is understood as
   point-in-time.
6. (Decision to confirm) Whether the secondary stale-prone paths (`get_test_simulations`,
   findings, security-control events) are addressed here or split into a follow-up.

## Open Questions for the team
- Should the secondary read paths be in scope, or a follow-up ticket?
- Performance ceiling: large running tests require paging all `executionsHistoryResults`; acceptable,
  or cap/short-circuit beyond a size threshold?
