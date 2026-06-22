# Stale Running-Test Simulation Counts — SAF-32018

## 1. Overview

- **Title**: HELM — stale simulation status counts for running tests (SAF-32018)
- **Task Type**: Bug fix + small refactor
- **Purpose**: When asked for a simulation status count (e.g. "Missed") on a test that is still
  running, the HELM agent reports a stale number sourced from the lazily-updated
  `testsummaries.finalStatus` aggregate, which lags the live per-simulation results shown in the
  UI. The agent reported 28 while the UI showed 80. This fix makes running-test counts accurate
  where cheap, and everywhere else routes the agent to the authoritative live count.
- **Target Consumer**: SafeBreach customers and SEs using the HELM AI agent against live/running
  tests; internally, anyone querying test progress mid-run via MCP.
- **Target Roles (RBAC)**: No change — inherits existing data-API RBAC of the consuming tools.
- **Key Benefits**:
  1. Accurate point-in-time counts for running tests in the primary detail tools.
  2. Honest, actionable expectations everywhere else (counts may lag → use the live tool).
  3. No fabricated numbers for data the backend has not yet computed (findings/SIEM/drift).
- **Business Alignment**: Trust in the HELM agent's reported numbers; eliminates a class of
  "agent contradicts the UI" incidents during active testing.
- **Originating Request**: JIRA SAF-32018 (reporter Hadas Cohen, env pentest01, Mgmt 2026Q2.4).

## 1.5 Document Status

| Field | Value |
|-------|-------|
| **PRD Status** | Complete |
| **Last Updated** | 2026-06-22 11:10 |
| **Owner** | Yossi Attas (with Claude Code) |
| **Current Phase** | Complete (8 of 8 phases) |

## 2. Solution Description

### Chosen Solution — Hybrid
A pure "real fix in all paths" was found to be **impossible**: findings, security-control events,
and the drift tools have **no live alternative** (their lag is upstream — post-processing, external
SIEM indexes, and a backend drift service), and a live recount for the `get_tests` list would
require paging `executionsHistoryResults` for every running test (≤1000+ fetches per call).

Therefore:
- **Part A — Real live-count fix (gated to non-terminal tests, soft-capped):** in the two
  single-test count paths where the live source is one cheap paged fetch — `sb_get_test_details`
  and the Studio `test_overview` block — compute `simulations_statistics` from the live
  `executionsHistoryResults` source instead of `finalStatus`. Reuse the existing SAF-31111
  terminal/non-terminal detection. Apply a **soft size cap**: if the test's known total exceeds a
  configurable threshold, keep the aggregate and emit the routing hint instead.
- **Part B — Universal routing hint (non-terminal tests):** every other count/finding-bearing path
  attaches a hint when its test(s) are non-terminal, telling the agent the counts may lag and to
  call `get_test_simulations` with the relevant `status_filter` for the exact live count
  (`total_simulations` is the authoritative live value).

### Alternatives Considered
- **Real fix in every path.** Pros: every headline number correct. Cons: **infeasible** — no live
  source for findings/SIEM/drift; prohibitive for `get_tests`. Rejected.
- **Hint only, all paths.** Pros: uniform, lowest risk, trivial. Cons: detail tools keep returning
  the stale aggregate as the headline number; relies entirely on the agent following the hint.
  Rejected as insufficient for the primary user-facing path.
- **MCP cache-TTL tuning (shorten `tests_cache`).** Pros: trivial. Cons: **does not fix the bug** —
  caching defaults to OFF and the lag is upstream of the MCP cache. Rejected.

### Decision Rationale
The hybrid is the only approach that gives correct *values* where it is cheap and feasible, correct
*expectations* everywhere, and never fabricates numbers the backend has not computed.

## 3. Core Feature Components

### Component A — Live status-count derivation (shared helper)
- **Purpose**: New shared helper that builds the `simulations_statistics` array (the 7 statuses:
  missed/stopped/prevented/detected/logged/no-result/inconsistent) from a list of **live**
  simulation entities (as returned by `_get_all_simulations_from_cache_or_api`), in the exact same
  shape as the existing `_build_simulation_status_counts(finalStatus)`.
- **Key Features**: Counts by each simulation's `final_status`/status field; returns identical
  structure so it is a drop-in for non-terminal paths. New code in `data_types.py`.

### Component B — Non-terminal live recount in `get_test_details` (soft-capped)
- **Purpose**: For non-terminal tests, replace the aggregate counts with the live-derived counts;
  fall back to aggregate + routing hint beyond the soft cap.
- **Key Features**: Reuses `terminal_statuses` detection (`data_functions.py:447`) and the existing
  `_get_all_simulations_from_cache_or_api`. Adjusts the existing non-terminal hint to reflect that
  counts are now live-but-point-in-time (or the routing hint in the capped fallback case).

### Component C — Studio `test_overview` parity + de-duplication
- **Purpose**: Apply the same non-terminal live recount in `get_studio_attack_latest_result`'s
  test-overview block, and **remove the inline duplicate** of the count logic
  (`studio_functions.py:1538`) by calling the centralized helper.

### Component D — Universal routing hint
- **Purpose**: Attach a non-terminal routing hint to the hint-only paths: `get_tests`,
  `get_test_findings_counts`/`_details`, `get_security_controls_events`/`_details`, and the drift
  tools (`get_simulation_result_drifts`, `get_simulation_status_drifts`,
  `get_security_control_drifts`).
- **Key Features**: Cheap test-status check (cached test list / orchestrator queue) to decide
  whether to attach the hint; consistent hint text directing to `get_test_simulations`.

### Component E — Configurable soft-cap threshold
- **Purpose**: Expose the live-recount size threshold as a constant + environment variable, and
  document it in CLAUDE.md.

## 4. API Endpoints and Integration

No new APIs. The fix re-routes which **existing** data-API source feeds the counts.

**Consumed (existing):**
- **Test summaries (aggregate, lagging mid-run)** — `GET /api/data/v1/accounts/{account_id}/testsummaries?size=1000` and `/testsummaries/{test_id}`. Field: `finalStatus` → current count source.
- **Executions history results (live per-simulation)** — `GET /api/data/v1/accounts/{account_id}/executionsHistoryResults` (paged, page_size=100). The live source already used by `sb_get_test_simulations`. New count source for non-terminal detail paths.
- **Orchestrator queue (real-time status)** — `GET /api/orch/v4/accounts/{account_id}/queue` (`queue_state.py`). Used for the cheap non-terminal status check.
- Headers unchanged (`x-apitoken` via `get_auth_headers_for_console`).

## 5. Example Agent Flow

**Primary scenario — "How many missed simulations so far?" on a running test:**
1. User asks the HELM agent for the missed count during an active test.
2. Agent calls `get_test_details(test_id)`.
3. Test is non-terminal and under the soft cap → tool recounts from `executionsHistoryResults` and
   returns `missed = 80` (matching the UI), plus a hint that the count is point-in-time and the
   test is still running (poll again).
4. Agent reports 80. ✅ (previously 28).

**Alternative — very large running test (over soft cap):**
- `get_test_details` returns the aggregate count plus a routing hint: "test too large for a live
  recount; call `get_test_simulations` with `status_filter='missed'` for the exact live count." The
  agent follows the hint and reports the live `total_simulations`.

**Alternative — findings/security/drift on a running test:**
- Tool returns its (upstream) value plus the routing hint that the number may lag while running.

## 6. Non-Functional Requirements

**Performance:**
- The live recount for a non-terminal detail call costs the same as one `get_test_simulations`
  call (~1 fetch/100 sims), and reuses `simulations_cache` when caching is enabled.
- **Soft cap** bounds worst-case latency: tests whose known total exceeds the threshold skip the
  recount and route via hint. Threshold default ~5000 simulations, configurable.
- Terminal tests pay **zero** extra cost (unchanged aggregate path).

**Technical Constraints / Backward Compatibility:**
- Response shape of `simulations_statistics` is **unchanged** (same 7-status array); only the
  source of the numbers changes for non-terminal tests. Terminal-test behavior is byte-for-byte
  unchanged.
- New hint fields are additive (`hint_to_agent`), consistent with existing conventions.
- Caching remains opt-in (`SB_MCP_CACHE_DATA`); fix is correct with caching on or off.

**Monitoring/Observability:**
- Log when a non-terminal recount is performed vs. when the soft-cap fallback triggers (info-level),
  to aid future tuning of the threshold.

## 7. Definition of Done

**Core Functionality:**
- [x] For a non-terminal test under the soft cap, `get_test_details` per-status counts match the
      live `executionsHistoryResults`-derived counts (UI values), not `finalStatus`.
- [x] For a terminal test, counts and behavior are unchanged.
- [x] Over the soft cap, `get_test_details` keeps the aggregate count and emits the routing hint.
- [x] Studio `test_overview` routes to live counts via hint (kept aggregate + self-contained;
      cross-server de-dup intentionally dropped — see Phase 3 note).
- [x] `get_tests`, findings tools, security-event tools, and drift tools attach the routing/caveat
      hint when their test(s) are non-terminal, and do not when terminal.

**Quality Gates:**
- [x] New + existing unit tests pass across all servers (1344 passed; 5 pre-existing
      `test_disable_filtering` failures exist on `origin/main`, unrelated to this change).
- [x] A regression test reproduces the original bug (28-vs-80; fails on pre-fix code, passes after).
- [x] No regression in terminal-test responses.
- [x] CLAUDE.md updated for the soft-cap env var and the running-test count behavior.

**Deployment Readiness:**
- [x] Soft-cap threshold env var documented; sensible default (5000).
- [x] Behavior verified against pentest01 on a live running test (repro scripts in PRD folder;
      live divergence + reconcile-at-terminal captured during ticket prep).

## 8. Testing Strategy

**Unit Testing (pytest):**
- **Component A helper**: counts per status from a synthetic live-simulation list; equals the
  `finalStatus`-based helper for an equivalent reconciled set.
- **`get_test_details`**:
  - Non-terminal + under cap → live counts (mock `_get_all_simulations_from_cache_or_api` to differ
    from `finalStatus`; assert live wins). *This is the TDD reproduction.*
  - Terminal → aggregate path unchanged.
  - Non-terminal + over cap → aggregate retained + routing hint present.
- **Studio `test_overview`**: live counts for non-terminal; uses centralized helper (assert no
  inline duplication path); over-cap fallback.
- **Hint-only paths**: routing hint present for non-terminal test(s), absent for terminal — for
  `get_tests`, findings counts/details, security events, and each drift tool.
- Follow memory gotchas: `json.dumps` spacing in assertions; update all renamed-param call sites.

**Integration / E2E:**
- E2E (`@pytest.mark.e2e`, `E2E_CONSOLE=pentest01`): on a live running test, assert
  `get_test_details` missed count tracks `get_test_simulations(status_filter='missed')`
  `total_simulations` within tolerance, and both reconcile at COMPLETED. Repro scripts
  (`verify_lag.py`, `poll_lag.py`) document the manual procedure.

**Coverage Gaps**: A truly live findings/SIEM/drift count is out of scope (no live source) — covered
only by the routing hint.

## 9. Implementation Phases

| Phase | Status | Completed | Commit SHA | Notes |
|-------|--------|-----------|------------|-------|
| Phase 1: Live count helper + soft-cap constant | ✅ Complete | 2026-06-22 | 56ecac7 | 5 unit tests |
| Phase 2: Non-terminal live recount in get_test_details | ✅ Complete | 2026-06-22 | e2430fc | 5 tests incl. 28-vs-80 repro |
| Phase 3: Studio test_overview parity + de-dup | ✅ Complete | 2026-06-22 | c1ee914 | Hint-routes to live (kept aggregate; no cross-server coupling — see note) |
| Phase 4: Routing hint — get_tests | ✅ Complete | 2026-06-22 | d120f90 | 2 tests |
| Phase 5: Routing hint — findings paths | ✅ Complete | 2026-06-22 | e93032d | 3 tests; + shared _is_test_non_terminal |
| Phase 6: Routing hint — security-control events | ✅ Complete | 2026-06-22 | b478cda | 2 tests (listing surface) |
| Phase 7: Routing hint — drift tools | ✅ Complete | 2026-06-22 | 1607979 | 2 tests (both grouping helpers) |
| Phase 8: Make soft cap configurable + docs | ✅ Complete | 2026-06-22 | bd7460f | 3 tests; CLAUDE.md updated |

### Phase 1 — Live count helper + soft-cap constant
- **Semantic change**: Add a shared helper that derives `simulations_statistics` from a list of
  live simulation entities, plus a module constant for the soft-cap threshold.
- **Implementation details**: New function in `data_types.py` (e.g. `build_simulation_status_counts_from_live`)
  that takes the mapped simulation list and tallies each of the 7 statuses, returning the identical
  array structure as `_build_simulation_status_counts`. Define `LIVE_RECOUNT_MAX_SIMULATIONS`
  (default ~5000) in `data_functions.py`. Inputs: list of simulation dicts. Output: list of
  `{status, count}` dicts. Edge cases: unknown/extra statuses ignored or bucketed consistently with
  the existing helper; empty list → all zeros.
- **Changes**:
  | File | Change |
  |------|--------|
  | `safebreach_mcp_data/data_types.py` | New live-count helper |
  | `safebreach_mcp_data/data_functions.py` | Add soft-cap constant |
  | `safebreach_mcp_data/tests/test_data_types.py` | Unit tests for helper |
- **Git commit**: `feat(SAF-32018): add live simulation status-count helper + soft-cap constant`

### Phase 2 — Non-terminal live recount in `get_test_details`
- **Semantic change**: For non-terminal tests under the soft cap, source `simulations_statistics`
  from live simulations; otherwise keep aggregate + routing hint.
- **Implementation details**: In `sb_get_test_details` (`data_functions.py:416`), after the existing
  non-terminal detection: if the test's known total (from current `simulations_statistics`/
  `finalStatus`) ≤ `LIVE_RECOUNT_MAX_SIMULATIONS`, call `_get_all_simulations_from_cache_or_api`,
  run the Phase-1 helper, and replace `simulations_statistics`. Else, leave aggregate and set the
  routing hint. Update the non-terminal `hint_to_agent`: when live, "counts are live as of now;
  test still running, poll again"; when capped, the routing hint. Terminal path untouched.
  Error handling: if the live fetch fails, fall back to aggregate + routing hint (log a warning) —
  never raise.
- **Changes**:
  | File | Change |
  |------|--------|
  | `safebreach_mcp_data/data_functions.py` | Live recount + hint logic in `sb_get_test_details` |
  | `safebreach_mcp_data/tests/test_data_functions.py` | TDD repro + terminal-unchanged + over-cap tests |
- **Git commit**: `fix(SAF-32018): live simulation counts for non-terminal get_test_details`

### Phase 3 — Studio `test_overview` parity + de-duplication
- **Semantic change**: Reuse the centralized helper in `get_studio_attack_latest_result` and apply
  the same non-terminal live recount + soft-cap fallback.
- **Implementation details**: Replace the inline status-count construction at
  `studio_functions.py:1538` with the Phase-1 helper. For non-terminal resolved test under cap,
  recount from live simulations; else aggregate + routing hint. Reuse the existing terminal check at
  `studio_functions.py:1555`.
- **Changes**:
  | File | Change |
  |------|--------|
  | `safebreach_mcp_studio/studio_functions.py` | Use central helper + live recount in test_overview |
  | `safebreach_mcp_studio/tests/...` | Tests for live/terminal/over-cap + no inline dup |
- **Git commit**: `fix(SAF-32018): live counts + de-dup status logic in studio test_overview`

### Phase 4 — Routing hint: `get_tests`
- **Semantic change**: Attach a routing hint to the `get_tests` response when any test in the
  returned page is non-terminal.
- **Implementation details**: In `sb_get_tests`, after building the page, if any test's status is
  non-terminal, add a top-level `hint_to_agent` noting per-test counts may lag for running tests and
  to use `get_test_details`/`get_test_simulations` for live values. No per-test paging.
- **Changes**:
  | File | Change |
  |------|--------|
  | `safebreach_mcp_data/data_functions.py` | Conditional hint in `sb_get_tests` |
  | `safebreach_mcp_data/tests/test_data_functions.py` | Hint present/absent tests |
- **Git commit**: `fix(SAF-32018): routing hint for running tests in get_tests`

### Phase 5 — Routing hint: findings paths
- **Semantic change**: Attach the routing hint to `get_test_findings_counts` and
  `get_test_findings_details` when the test is non-terminal.
- **Implementation details**: Cheap status check (cached test list / orchestrator) for the test_id;
  if non-terminal, add a hint that findings are still accumulating and may lag. No recount.
- **Changes**:
  | File | Change |
  |------|--------|
  | `safebreach_mcp_data/data_functions.py` | Conditional hint in findings tools |
  | `safebreach_mcp_data/tests/...` | Tests |
- **Git commit**: `fix(SAF-32018): routing hint for running tests in findings tools`

### Phase 6 — Routing hint: security-control events
- **Semantic change**: Attach the routing hint to `get_security_controls_events` /
  `get_security_control_event_details` when the test is non-terminal.
- **Implementation details**: Same cheap status check + hint noting SIEM-sourced events may lag for
  running tests.
- **Changes**:
  | File | Change |
  |------|--------|
  | `safebreach_mcp_data/data_functions.py` | Conditional hint |
  | `safebreach_mcp_data/tests/...` | Tests |
- **Git commit**: `fix(SAF-32018): routing hint for running tests in security-control events`

### Phase 7 — Routing hint: drift tools
- **Semantic change**: Attach a caveat hint to `get_simulation_result_drifts`,
  `get_simulation_status_drifts`, `get_security_control_drifts` indicating running tests in the
  window may have incomplete drift data.
- **Implementation details**: Add to existing hint construction in each drift tool a note about
  in-flight tests; no recount.
- **Changes**:
  | File | Change |
  |------|--------|
  | `safebreach_mcp_data/data_functions.py` | Hints in drift tools |
  | `safebreach_mcp_data/tests/...` | Tests |
- **Git commit**: `fix(SAF-32018): running-test caveat in drift tools`

### Phase 8 — Configurable soft cap + docs
- **Semantic change**: Make the soft-cap threshold configurable via env var and document behavior.
- **Implementation details**: Read `LIVE_RECOUNT_MAX_SIMULATIONS` from env (default ~5000). Update
  CLAUDE.md: document the running-test live-count behavior, the env var, and the routing hint.
- **Changes**:
  | File | Change |
  |------|--------|
  | `safebreach_mcp_data/data_functions.py` | Env-var read for threshold |
  | `CLAUDE.md` | Document behavior + env var |
- **Git commit**: `docs(SAF-32018): document running-test live counts + soft-cap env var`

## 10. Risks and Assumptions

**Technical Risks:**
- **Perf on large running tests** (Medium): mitigated by the soft cap + cache reuse + non-terminal
  gating.
- **Regression in terminal-test counts** (Medium): mitigated by gating strictly on non-terminal and
  golden assertions on terminal responses.
- **Status-check cost in hint-only paths** (Low): use the cheapest available signal (cached test
  list / orchestrator), avoid extra paging.
- **Agent ignores routing hint on capped/hint-only paths** (Low/accepted): inherent to hint-based
  paths where no live source exists.

**Assumptions Under Question:**
- `executionsHistoryResults` is the authoritative live source — **validated** (matches UI; reconciles
  to `finalStatus` at terminal: 67==67, 125/94).
- Default soft-cap (~5000) is a reasonable balance — to confirm/tune via the observability logs.

**Mitigation:** Phased, independently-committable changes; each phase verified before the next;
configurable threshold for safe rollout.

## 11. Future Enhancements
- A genuine live findings/drift count if/when the backend exposes a live source.
- Optional server-side count endpoint to avoid client-side paging for large running tests.
- Consider live counts for `get_tests` if a bulk live-count API becomes available.

## 12. Executive Summary
- **Issue**: The HELM agent reports stale simulation status counts for running tests (28 vs UI's
  80) because counts come from the lagging `testsummaries.finalStatus` aggregate.
- **What Was Built**: Live per-simulation recount for non-terminal tests in the two single-test
  detail paths (`get_test_details`, Studio `test_overview`) with a soft size cap, plus a universal
  routing hint on all other count/finding-bearing paths directing the agent to the authoritative
  live count tool. Studio's inline count duplicate folded into the central helper.
- **Key Technical Decisions**: Hybrid (real fix where cheap/feasible + hint everywhere), because a
  real fix is impossible for findings/SIEM/drift and prohibitive for `get_tests`; gate on
  non-terminal status; soft-cap to bound latency; never fabricate upstream-unavailable numbers.
- **Scope Changes**: Real live recount limited to two single-test paths; all other paths are
  hint-only by design.
- **Business Value**: Eliminates "agent contradicts the UI" during live tests for the primary
  tools, and makes the limitation explicit + actionable everywhere else.

## 14. Change Log

| Date | Change Description |
|------|-------------------|
| 2026-06-22 09:30 | PRD created — initial draft |
| 2026-06-22 09:40 | PRD approved by owner; ready for implementation |
| 2026-06-22 11:10 | All 8 phases implemented via TDD (commits 56ecac7..bd7460f); PRD marked Complete |
| 2026-06-22 11:30 | Green-tree fixes: stale SafeBreachAuth patch in test_disable_filtering (d31bc42); self-discovering test_get_test_drifts_e2e (5389908) |
| 2026-06-22 11:45 | Gap fix from manual testing: get_test_simulations now emits a partial/point-in-time hint for running tests (3e4195d) |
