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
| **PRD Status** | Complete (RCA corrected — see §2 banner) |
| **Last Updated** | 2026-06-22 12:30 |
| **Owner** | Yossi Attas (with Claude Code) |
| **Current Phase** | Complete (8 of 8 phases) |

## 2. Solution Description

> **⚠️ RCA & approach REVISED 2026-06-22 (post PR-review).** An earlier version of this PRD
> concluded that `testsummaries.finalStatus` *upstream-lags* the live per-simulation data and that
> `get_test_details` therefore had to recount by paging `executionsHistoryResults` (soft-capped at
> 5000). **That conclusion was wrong** — the "lag" I measured was an artifact of the multi-second
> paging window of the live() call itself. Controlled, back-to-back measurement on a *growing* test
> showed `executionsHistorySuggestions` (the UI's own breakdown source), `detailedTestSummaries`,
> and `testsummaries.finalStatus` all agree to within **0–1 simulation**. The sections below reflect
> the corrected, cheaper fix.

### Root Cause (corrected)
The MCP introduced the staleness itself, in two layers on the running-test path of `get_test_details`:
1. counts were read from the **cached test list** (`tests_cache`, up-to-30-min TTL), and
2. the SAF-31111 running-test refresh updated only **status**, never the **counts**.
So the agent could serve a counts snapshot up to 30 minutes old (28) while the UI showed live (80).
A **fresh** `finalStatus` (single-test `testsummaries/{id}` call) tracks the UI's live aggregation
(`executionsHistoryResults.total` / `executionsHistorySuggestions`) to within ~1 sim — so the
upstream aggregate is *not* the problem.

### Chosen Solution
- **`get_test_details` (non-terminal):** refresh `simulations_statistics` from the **fresh
  single-test `testsummaries/{id}` call** (defeats the stale cache + the never-refreshed counts) and
  add a **point-in-time hint** that routes to `get_test_simulations` for the live filtered grid.
  One cheap call; **no `executionsHistoryResults` paging, no soft cap.**
- **Cheap hints elsewhere (non-terminal):** `get_tests`, findings, security-control events, and the
  drift tools carry a running-test caveat; `get_test_simulations` notes its `total_simulations` is
  partial/point-in-time while running. (These were correct in the original implementation and are
  kept.)

### Alternatives Considered
- **Page `executionsHistoryResults` and recount (the earlier approach).** Rejected: expensive
  (pages every simulation), needed a 5000 soft cap that can make large running tests wrong, and
  solves a lag that does not actually exist (fresh `finalStatus` already matches the UI within ~1).
- **`detailedTestSummaries`.** Rejected as the count source: it carries the **same** `finalStatus`
  aggregate as `testsummaries` (verified equal), so it's no fresher — and the UI never calls it.
- **`executionsHistorySuggestions`.** Viable (it's the UI's exact breakdown source, one cheap call),
  but `finalStatus` from the single-test endpoint is equally fresh, even simpler, and already part
  of the response — so we use that.

### Decision Rationale
The bug was in-MCP staleness, so the fix is to stop serving stale counts on the running-test path
with a single fresh call — not to re-derive counts the backend already computes accurately.

## 3. Core Feature Components

### Component A — Fresh-count refresh in `get_test_details` (non-terminal)
- **Purpose**: For a non-terminal test, refresh `simulations_statistics` (and status/end_time) from
  the **fresh single-test `testsummaries/{id}` call** instead of the stale cached list value.
- **Key Features**: Reuses `terminal_statuses` detection and the existing `_fetch_single_test`;
  keeps the orchestrator-queue call for real-time status (SAF-31111). One cheap call, no paging.
  Adds a point-in-time `hint_to_agent` routing to `get_test_simulations`.

### Component B — Studio `test_overview` routing hint
- **Purpose**: `get_studio_attack_latest_result`'s test-overview keeps the (correctly test-scoped)
  `finalStatus` aggregate and adds a non-terminal hint routing to `get_test_details` (live for
  running tests) / `get_test_simulations`. Kept self-contained (no cross-server coupling).

### Component D — Universal routing hint
- **Purpose**: Attach a non-terminal routing hint to the hint-only paths: `get_tests`,
  `get_test_findings_counts`/`_details`, `get_security_controls_events`/`_details`, and the drift
  tools (`get_simulation_result_drifts`, `get_simulation_status_drifts`,
  `get_security_control_drifts`).
- **Key Features**: Cheap test-status check (`_is_test_non_terminal`, orchestrator queue) to decide
  whether to attach the hint; consistent hint text. Findings/SIEM/drift have no live source, so the
  hint is a "may be incomplete, re-query after completion" caveat rather than a live-count route.

## 4. API Endpoints and Integration

No new APIs. The fix changes *which freshness* of an existing endpoint feeds the running-test counts.

**Consumed (existing):**
- **Single-test summary (fresh, used for running-test counts)** — `GET /api/data/v1/accounts/{account_id}/testsummaries/{test_id}`. Field: `finalStatus`. Verified to track the UI's live aggregation to within ~1 simulation.
- **Test-list summary (cached, the stale source of the bug)** — `GET .../testsummaries?size=1000` via `tests_cache` (≤30-min TTL).
- **Orchestrator queue (real-time status)** — `GET /api/orch/v4/accounts/{account_id}/queue` (`queue_state.py`).
- **UI reference (for verification only)** — `executionsHistoryResults.total` (grid count) and `executionsHistorySuggestions` (per-status breakdown). The MCP does NOT need these for `get_test_details`.
- Headers unchanged (`x-apitoken` via `get_auth_headers_for_console`).

## 5. Example Agent Flow

**Primary — "How many missed simulations so far?" on a running test:**
1. Agent calls `get_test_details(test_id)`.
2. Test is non-terminal → tool refreshes counts from the fresh `testsummaries/{id}` call (≈UI value)
   and returns `missed = 80` with a point-in-time hint.
3. Agent reports 80 ✅ (previously a stale cached 28).

**Findings/security/drift on a running test:** tool returns its value plus a caveat that it may be
incomplete while running (no live source to switch to).

## 6. Non-Functional Requirements

**Performance:** one extra cheap single-test API call for a non-terminal `get_test_details` (no
per-simulation paging, no cap). Terminal tests are unchanged. Hint-only paths add at most one cheap
orchestrator status check.

**Backward Compatibility:** `simulations_statistics` shape unchanged (same 7-status array); only its
freshness changes for non-terminal tests. New `hint_to_agent` text is additive. Correct with caching
on or off.

## 7. Definition of Done

**Core Functionality:**
- [x] For a non-terminal test, `get_test_details` counts are refreshed from the fresh
      `testsummaries/{id}` call (not the stale cached list), matching the UI within ~1 sim.
- [x] No `executionsHistoryResults` paging / soft cap in `get_test_details`.
- [x] For a terminal test, counts and behavior are unchanged (no refresh, no paging).
- [x] On refresh failure, degrade to cached counts + hint (never raise).
- [x] `get_tests`, findings, security-events, drift tools, and `get_test_simulations` carry the
      correct running-test hint/caveat when non-terminal, and not when terminal.

**Quality Gates:**
- [x] Unit tests pass across all servers (no `executionsHistoryResults`-recount machinery remains —
      verified by dead-symbol grep).
- [x] Regression test: a stale-cached running test (missed=28) is corrected to the fresh value
      (missed=80) by `get_test_details`.
- [x] E2E green on pentest01 (107 passed / 5 skipped / 0 failed before this revision; re-verified).
- [x] CLAUDE.md updated to describe the fresh-single-test fix (env var removed).

## 8. Testing Strategy

**Unit (pytest):**
- `get_test_details`: non-terminal refreshes counts from `_fetch_single_test` (stale 28 → fresh 80)
  and does NOT page `executionsHistoryResults`; terminal does neither; refresh failure falls back to
  cached counts; point-in-time hint present for non-terminal.
- Hint-only paths: hint/caveat present for non-terminal, absent for terminal — `get_tests`, findings
  counts/details, security events, each drift grouping helper, and `get_test_simulations`.

**E2E (`E2E_CONSOLE=pentest01`):** existing data/studio E2E. The self-discovering
`test_get_test_drifts_e2e` replaced the brittle hardcoded-ID version.

## 9. Implementation (as built)

> The work was first implemented along an `executionsHistoryResults`-recount design (commits
> 56ecac7, e2430fc, bd7460f) that a post-PR-review RCA showed to be unnecessary (see the banner in
> §2). Those changes were **reverted/replaced** by the fresh-single-test approach. The table below
> is the **final landed state**; superseded commits are noted for history only.

| Area | Status | Final commit | Notes |
|------|--------|-------------|-------|
| `get_test_details` fresh-single-test refresh + point-in-time hint | ✅ | _(this revision)_ | Replaced the recount of 56ecac7/e2430fc; removed helper, soft cap, env var |
| `get_tests` running-test hint | ✅ | d120f90 | kept |
| findings hint + `_is_test_non_terminal` | ✅ | e93032d | kept |
| security-control events caveat | ✅ | b478cda | kept |
| drift tools caveat | ✅ | 1607979 | kept |
| `get_test_simulations` partial-while-running hint | ✅ | 3e4195d | kept |
| Studio `test_overview` routing hint | ✅ | c1ee914 | kept (aggregate + hint; self-contained) |
| green-tree test fixes (deny-list, self-discovering drift E2E) | ✅ | d31bc42, 5389908 | kept |

## 10. Risks and Assumptions

**Technical Risks:**
- **Regression in terminal-test counts** (Low): gated strictly on non-terminal; terminal path untouched.
- **Hint-only paths' status-check cost** (Low): single cheap orchestrator check.

**Assumptions:**
- A fresh `testsummaries/{id}` `finalStatus` tracks the UI's live aggregation within ~1 sim —
  **verified** by controlled back-to-back measurement (`executionsHistorySuggestions` ≈
  `detailedTestSummaries` ≈ `testsummaries` within 0–1 on a growing test).
- The original 28-vs-80 gap was in-MCP staleness (30-min cache + counts never refreshed on the
  running-test path), not upstream lag — strongly supported by that measurement.

## 11. Future Enhancements
- If a future need for an exact live per-status breakdown arises, `executionsHistorySuggestions`
  (the UI's own one-call aggregation) is the natural source — no paging required.

## 12. Executive Summary
- **Issue**: For a running test, `get_test_details` reported a stale "Missed" count (28 vs the UI's
  80) and reconciled only after the test finished.
- **Root cause**: in-MCP staleness — counts came from the ≤30-min cached test list and the
  running-test refresh updated only status, never the counts. A fresh `finalStatus` matches the UI.
- **What was built**: for a non-terminal test, `get_test_details` refreshes counts from one fresh
  `testsummaries/{id}` call + a point-in-time hint; cheap running-test hints/caveats on the other
  count/finding paths. No per-simulation paging, no soft cap.
- **Course correction**: an initial `executionsHistoryResults`-recount design was reverted after a
  controlled measurement disproved the "upstream lag" premise — keeping the fix cheap and correct.
- **Business value**: the agent's running-test counts now match the UI within ~1 sim at negligible cost.

## 14. Change Log

| Date | Change Description |
|------|-------------------|
| 2026-06-22 09:30 | PRD created — initial draft |
| 2026-06-22 09:40 | PRD approved by owner; ready for implementation |
| 2026-06-22 11:10 | All 8 phases implemented via TDD (commits 56ecac7..bd7460f); PRD marked Complete |
| 2026-06-22 11:30 | Green-tree fixes: stale SafeBreachAuth patch in test_disable_filtering (d31bc42); self-discovering test_get_test_drifts_e2e (5389908) |
| 2026-06-22 11:45 | Gap fix from manual testing: get_test_simulations now emits a partial/point-in-time hint for running tests (3e4195d) |
| 2026-06-22 12:30 | **RCA corrected after PR review + ui-react investigation.** Controlled measurement disproved the "finalStatus upstream-lags" premise (it was a paging-window artifact; fresh finalStatus ≈ UI within ~1 sim). Reverted the executionsHistoryResults recount / soft cap / env var / helper; replaced with a fresh single-test `testsummaries/{id}` refresh for non-terminal get_test_details. Kept all hint-only changes. PRD §2–§12 rewritten to match. |
