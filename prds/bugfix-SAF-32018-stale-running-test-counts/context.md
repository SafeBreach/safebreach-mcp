# Context: SAF-32018

**Status:** Phase 3: Context Created
**Mode:** Improve existing ticket
**Branch:** `bugfix/SAF-32018-stale-running-test-counts`
**Repo:** `/Users/yossiattas/Public/safebreach-mcp`

## Ticket Summary

| Field | Value |
|-------|-------|
| Key | SAF-32018 |
| Type | Bug (High) |
| Status | To Do — Saf sprint 91 |
| Assignee | Yossi Attas |
| Reporter | Hadas Cohen |
| Labels | CTEM-dev, HELM-AI-Agent |
| Env | pentest01.safebreach.com, Mgmt/Sim 2026Q2.4 |

**Title:** HELM | Data Discrepancy - Agent reports incorrect count of "Missed" simulations due to stale background API cache

**Reported behavior:** While a test execution is actively running, the HELM agent (this MCP
server) reports a stale "Missed" simulation count (e.g. 28) while the live UI filter shows the
updated value (e.g. 80). The agent rationalizes this as "an API caching issue on the backend
side." Workaround: wait for the test to finish so the cache reconciles.

**Steps to reproduce (from ticket):**
1. Navigate to Analysis → Simulation Results for an ongoing active test run.
2. Apply the left-sidebar filter to show Result: Missed.
3. Verify the header shows Filter Simulations (80) matching the grid.
4. Ask the HELM agent to verify/check the count of missed simulations for that running test.
5. Note HELM's stated count → it reports 28 (stale), not 80.

**Expected:** HELM returns the accurate, real-time count (80) matching the UI.
**Actual:** HELM returns a stale count (28) and blames backend caching.

## Task Scope

- Repo: safebreach-mcp (this repo) — confirmed by user.
- Focus: Caching staleness for **running (non-terminal) tests** — root-cause why running-test
  status counts are served stale, and whether non-terminal tests should bypass / short-TTL the
  client-side cache.

## Investigation Findings

### Where the count comes from (call chain)
- `get_test_details` tool → `sb_get_test_details()` — `data_functions.py:416`
- → `_find_test_in_cached_list()` → `_get_all_tests_from_cache_or_api()` — `data_functions.py:204`
  - Calls `GET /api/data/v1/accounts/{account_id}/testsummaries?size=1000` (`data_functions.py:235`)
- → `get_reduced_test_summary_mapping()` — `data_types.py:142`
- → `_build_simulation_status_counts(finalStatus)` — `data_types.py:82` — extracts the 7 status
  counts (missed/stopped/prevented/detected/logged/no-result/inconsistent) **from the API's
  `finalStatus` aggregate object**. This becomes `simulations_statistics`.
- The single-test fallback endpoint `/testsummaries/{test_id}` (`_fetch_single_test`,
  `data_functions.py:531`) derives counts from the **same** `finalStatus` aggregate.

### Existing running-test handling (SAF-31111)
- `sb_get_test_details` already detects non-terminal status (`terminal_statuses =
  {'completed','canceled','failed'}`, `data_functions.py:447-449`) and refreshes:
  - Phase 1 — orchestrator queue `get_orchestrator_test_state()` (`queue_state.py:25`): returns
    only `"RUNNING"` / `"PAUSED"` / `None`. **No counts.** Updates only `status` (`:456`).
  - Phase 2 (only if orchestrator returns None) — single-test endpoint refresh of
    `simulations_statistics` (`:466`), but from the **same lagging `finalStatus` aggregate**.

### THE ROOT CAUSE (corrects the "line 456" framing)
For a **running** test the count is sourced from `testsummaries.finalStatus`, a backend aggregate
that is computed lazily/periodically and **lags the live per-simulation results** during an active
run. The UI's "Filter Simulations (80)" counts **live simulation rows**. The MCP faithfully relays
the lagging aggregate → reports 28. The agent's "backend caching" is a real upstream lag, not the
MCP's own cache.

- **MCP's own cache is NOT the primary cause.** `SB_MCP_CACHE_DATA` defaults to **false**
  (`cache_config.py`), so each call hits `testsummaries` fresh and *still* returns 28. The
  `tests_cache` 1800s TTL (`data_functions.py:36`) is only an **aggravating** factor when caching
  is explicitly enabled.
- Fixing `:456` to "also refresh counts" is **not viable**: the orchestrator has no counts, and
  the single-test endpoint shares the same lagging aggregate.

### The live, accurate count source already exists
- `sb_get_test_simulations()` (`data_functions.py:619`) fetches `executionsHistoryResults`
  (paginated, `data_functions.py:739`) and counts client-side. With `status_filter='missed'`,
  `total_simulations` is the **live** count — the same source/value the UI shows (80). This is the
  candidate accurate source for running-test counts.

### Other stale-prone paths during a running test (secondary)
- `sb_get_test_simulations` → `simulations_cache` 600s TTL (only when caching enabled)
- findings: `findings_cache` 600s; security events: `security_control_events_cache` 600s
- All only bite when `SB_MCP_CACHE_DATA=true`.

### Tests (where new coverage goes)
- `safebreach_mcp_data/tests/test_data_functions.py` — `test_sb_get_test_details_*` (uses a
  *completed* test today; no running-test-count case), cache tests at `:196`, `:219`
- `safebreach_mcp_data/tests/test_data_types.py` — `_build_simulation_status_counts` /
  `get_reduced_test_summary_mapping` tests (`:656+`)
- `safebreach_mcp_core/tests/test_safebreach_cache.py`, `test_cache_config.py`

### Empirical verification (against pentest01, 2026-06-22)
Ran `verify_lag.py` (in this PRD folder) using the repo's own functions:
- **Completed tests:** aggregate `finalStatus.missed` == live `executionsHistoryResults` missed
  count, exactly (67 == 67 across 3 recent completed tests). → counting `executionsHistoryResults`
  is the correct live source, AND the two sources **converge at terminal** (matches the ticket's
  "wait for completion and it reconciles" workaround).
- **No running test** existed at that instant, so live divergence was not personally captured;
  the divergence (28 vs 80 during an active run) is documented by the reporter's screen recording
  on the ticket.
- Conclusion: root cause confirmed to the extent possible without a live running test —
  consistent with field evidence + method validation + architecture.

### LIVE REPRODUCTION CONFIRMED (running test 1782107855457.2, 2026-06-22)
User manually triggered a live test; `poll_lag.py` (this PRD folder) sampled aggregate vs live
every 5s across the full run (~200s, 125 sims):
- During **RUNNING**, live (`executionsHistoryResults`) consistently led the aggregate
  (`finalStatus`) at almost every sample. Examples:
  - t=0:  agg_total=10 / live=13 ; agg_missed=6  / live=8
  - t=75: agg_total=64 / live=68 ; agg_missed=43 / live=46
  - t=85: agg_total=80 / live=82 ; agg_missed=55 / live=57
- At **t=200 the test hit COMPLETED and both reconciled exactly** (125/125 total, 94/94 missed)
  — reproduces the ticket's "wait for completion to reconcile" workaround.
- Observed gap was small (±1..4) because this was a fast 125-sim test; the field report's
  28-vs-80 reflects a larger/slower run where `finalStatus` lagged much further — **same
  mechanism**.
- **TDD reproduction basis:** for a non-terminal test, `get_test_details` counts (from
  `finalStatus`) lag the `executionsHistoryResults`-derived counts; a regression test can assert
  they match (fails today, passes after fix). Verification scripts kept in this PRD folder
  (`verify_lag.py`, `poll_lag.py`).

**Status:** Phase 8 Complete — investigation comment posted to SAF-32018 (comment 191903)

---

## planning-dev-task — Phase 4: Full inventory of stale count-bearing read paths

Goal: decide between (A) real live-count code path in every affected read path vs. (B) a
non-terminal "counts may lag" hint. Decision hinges on real-fix feasibility per path.

| Path | Source | Stale while running? | Live alternative? | Real-fix cost | Terminal-aware? | Shares `_build_simulation_status_counts`? |
|------|--------|----------------------|-------------------|---------------|-----------------|-------------------------------------------|
| `get_test_details` | testsummaries.finalStatus | YES | YES (executionsHistoryResults) | Moderate (page 1 test) | YES (`:447`) | YES |
| `get_tests` (list) | finalStatus per test | YES | YES per test | **Prohibitive** (≤1000 tests → 1000+ paged fetches) | NO | YES |
| `get_studio_attack_latest_result` (test_overview) | finalStatus (inline @ `studio_functions.py:1538`) | YES | YES | Moderate (page 1 test) | YES (`:1555`) | NO — **duplicated inline logic** |
| `get_test_simulations` | executionsHistoryResults (direct) | **No — already LIVE** | n/a (is the source) | n/a | implicit | NO (`get_reduced_simulation_result_entity`) |
| `get_test_findings_counts` / `_details` | propagateSummary findings | YES (post-processing) | **NO live per-finding source** | **Infeasible** | NO | independent |
| `get_security_controls_events` / `_details` | SIEM eventLogs | YES (external SIEM lag) | **NO (external)** | **Infeasible** | NO | independent |
| `get_simulation_result_drifts` / `_status_drifts` / `get_security_control_drifts` | backend drift API | YES | only by re-implementing backend logic | **Infeasible** | NO | independent |
| `get_test_drifts` | executionsHistoryResults | already live (incomplete mid-run) | n/a | n/a | implicit | independent |

### Decisive facts
1. **The "real fix" is NOT achievable in all paths.** Findings, security-control events, and the
   drift tools have **no live alternative** — the lag is genuinely upstream (post-processing / SIEM
   / backend drift service). A "real fix" there would mean re-implementing backend aggregation in
   the MCP — infeasible and wrong.
2. **`get_tests` real fix is prohibitive** — live counts for a list would require paging
   `executionsHistoryResults` for every running test (up to 1000+ fetches per call).
3. **Only 2 single-test paths can take a cheap real fix:** `get_test_details` and the Studio
   `test_overview` block (which also has a **duplicated inline** copy of the count logic at
   `studio_functions.py:1538` that bypasses the centralized helper).
4. **The authoritative live count already exists** as a tool: `get_test_simulations` with a
   `status_filter` returns `total_simulations` straight from `executionsHistoryResults` (proven to
   reconcile with finalStatus at terminal: 67==67, 125/94).

## planning-dev-task — Phase 5: Chosen approach (HYBRID)

Decision: **Hybrid** — real-fix where cheap/feasible, routing-hint everywhere else.
Rationale: a pure real-fix cannot cover all paths (findings/SIEM/drift have NO live source;
`get_tests` is prohibitive). A bare hint is uniform but leaves headline numbers aggregate-sourced.
Hybrid gives correct values where cheap + honest, actionable expectations everywhere.

### Part A — Real live-count fix (gated to NON-TERMINAL tests)
Applies to the two single-test count paths:
- `sb_get_test_details` (`data_functions.py:416`)
- Studio `test_overview` block (`studio_functions.py:1538`) — also fold its inline duplicate into
  the centralized helper.

Mechanism: when the test is non-terminal (reuse SAF-31111 `terminal_statuses` detection), compute
`simulations_statistics` from the live `executionsHistoryResults` source (via
`_get_all_simulations_from_cache_or_api` → count by status) instead of `finalStatus`.
Terminal tests are unchanged (cheap aggregate, already reconciled).

**Perf guardrail: SOFT CAP + FALLBACK.** Recount live only when the test's known total
(from `finalStatus`) is ≤ a configurable threshold (default ~5000 sims). Beyond it, keep the
aggregate count and attach the routing hint ("test too large for live recount; use
get_test_simulations with a status filter for an exact live count"). Threshold via constant/env.

### Part B — Universal routing hint (NON-TERMINAL tests)
Attach a hint on every count/finding-bearing path when its test(s) are non-terminal:
- Hint-only paths (counts stay aggregate-sourced): `get_tests` (if any test in page is running),
  `get_test_findings_counts`/`_details`, `get_security_controls_events`/`_details`, the drift tools.
  Text: "Test still running — these counts/findings may lag live results; for an exact live
  simulation count call `get_test_simulations` with the relevant `status_filter`."
- Real-fix paths (`get_test_details`, Studio test_overview): counts are now LIVE, so the hint
  instead clarifies the count is point-in-time and will keep changing while running (retain the
  existing 'poll again' guidance); fallback case (over soft cap) uses the routing-hint text.

### Out of scope / follow-up notes
- We do NOT re-implement backend aggregation for findings/SIEM/drift (no live source).
- `get_tests` is intentionally hint-only (per-test live recount across a list is prohibitive).

### Test strategy (TDD)
- Reproduce: assert non-terminal `get_test_details` counts == live `executionsHistoryResults`
  counts (fails today). Reuse repro scripts in this folder.
- Terminal tests: counts unchanged (aggregate path).
- Soft-cap fallback: over-threshold non-terminal test keeps aggregate + emits routing hint.
- Hint presence on each hint-only path for a non-terminal test; absent for terminal.
- Studio test_overview: live counts for non-terminal + uses centralized helper (no inline dup).

**Status:** Phase 7 complete — PRD approved; JIRA RCA field populated; SAF-32018 "is caused by"
SAF-28298 link created. Ready for implementation (tdd-implementing-prd).

## Problem Analysis

_(to be populated in Phase 5)_
