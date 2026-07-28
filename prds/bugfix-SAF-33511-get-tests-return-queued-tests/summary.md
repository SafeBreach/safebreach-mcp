# Ticket Summary: SAF-33511

## Overview
**Mode**: Improving existing
**Project**: SAF
**Repositories**: /Users/yossiattas/projects/safebreach-mcp

---

## Current State
**Summary**: safebreach-mcp: "get test summaries" tool should also return queued tests in the response
**Issues Identified**: The original description states the symptom (queued tests missing from the
response) but not the root cause, affected code, or acceptance criteria. Investigation established
the RCA and the required fix shape (orchestrator queue API merge).

---

## Investigation Summary

### safebreach-mcp
- `get_tests` (tool: `safebreach_mcp_data/data_server.py:55-96`; logic: `sb_get_tests` in
  `safebreach_mcp_data/data_functions.py:81-228`) is backed exclusively by
  `GET /api/data/v1/accounts/{account_id}/testsummaries?size=1000&includeArchived=false`.
- **RCA (confirmed)**: the platform has 5 concurrent test-execution slots; tests submitted beyond
  that wait in the orchestrator queue. The `testsummaries` API only reflects tests in a terminal
  state or associated with an active execution slot — queued tests are structurally invisible to
  it. `sb_get_tests` therefore cannot see them; it must merge results from the orchestrator queue
  API (`GET /api/orch/v4/accounts/{account_id}/queue`).
- `safebreach_mcp_core/queue_state.py` already calls the orchestrator queue API but only scans
  active `slotState[]` (returns RUNNING/PAUSED/None) — the natural extension point for reading
  pending queue entries.
- The write tools (`run_scenario`, `quick_run`, `run_studio_attack`) return planRunId with
  `status: 'queued'` — those are exactly the tests `get_tests` currently cannot show, breaking
  the queue-then-monitor agent workflow.
- Secondary gaps: `'queued'` is absent from the advertised `status_filter` values
  (`data_server.py:63`); the tests cache (TTL=1800s) would stale queued state (only `'running'`
  bypasses cache today); default ordering by `end_time desc` sends timestamp-less entries to the
  bottom (`data_functions.py:388`), so inclusion alone wouldn't yield visibility.
- Relevant files: `safebreach_mcp_data/data_functions.py`, `safebreach_mcp_data/data_server.py`,
  `safebreach_mcp_data/data_types.py`, `safebreach_mcp_core/queue_state.py`, tests under
  `safebreach_mcp_data/tests/`, docs `README.md` / `CLAUDE.md`.
- Precedent: SAF-30863 added `'running'` as a status_filter (enum + docs + unit test); SAF-33511
  is broader because it adds a second data source.

---

## Problem Analysis

### Problem Description
An AI agent that queues a test via the MCP write tools receives a planRunId with status 'queued',
but a follow-up `get_tests` call cannot show that test until it occupies one of the 5 execution
slots. The tool's single data source (`testsummaries`) only covers slot-active and terminal tests,
so the agent loses track of pending work — `get_tests` presents an incomplete picture of test
activity. The fix is to merge pending entries from the orchestrator queue API into the `get_tests`
response, dedupe by planRunId, expose `'queued'` as a first-class status filter, and place queued
entries visibly (they have no start/end timestamps).

### Impact Assessment
- Test orchestration/monitoring workflows: agents cannot enumerate or monitor pending tests,
  breaking queue-then-poll patterns after `run_scenario`/`quick_run`/`run_studio_attack`.
- Tool correctness: `get_tests` silently under-reports; there is no hint that queued tests exist.

### Risks & Edge Cases
- Freshness: queue state is volatile — queued results must bypass (or barely use) the 30-min tests
  cache, mirroring the existing `'running'` bypass.
- Visibility: queued entries lack timestamps; under default `end_time desc` ordering they sink to
  the bottom — merged entries need deliberate placement (e.g., first) or a sort-key fallback.
- Double counting: queue→slot transition during the documented 10-15s orchestrator/data-API
  consistency lag could surface a test in both sources — merge must dedupe by planRunId.
- Shape: queue entries lack testsummaries fields (finalStatus counts, end_time, duration) and need
  a sensible reduced representation with `status: 'queued'`.
- Open item: exact shape of pending (non-slot) entries in the `/queue` response — confirm against
  a live console during implementation.

---

## Proposed Ticket Content

### Summary (Title)
safebreach-mcp: get_tests should merge orchestrator-queued tests into its response

### Description

**Description (Markdown for JIRA):**
```markdown
### Background
The SafeBreach platform executes at most 5 tests concurrently. Tests submitted beyond the 5
available slots wait in the orchestrator queue for a free execution slot. AI agents that queue
tests via the MCP write tools (`run_scenario`, `quick_run`, `run_studio_attack`) receive a
planRunId with status 'queued', but cannot subsequently see those tests via `get_tests` — the tool
under-reports pending work and breaks queue-then-monitor workflows.

### Root Cause
`sb_get_tests` is backed exclusively by the data API
(`GET /api/data/v1/accounts/{account_id}/testsummaries`), which only reflects tests in a terminal
state or tests associated with an active execution slot. Tests waiting in the orchestrator queue
are structurally invisible to this endpoint. To surface them, the tool must merge results from the
orchestrator queue API (`GET /api/orch/v4/accounts/{account_id}/queue`).

### Expected Behavior
* `get_tests` includes queued tests (pending in the orchestrator queue) in its response, merged
  with the testsummaries results and deduplicated by planRunId.
* Queued entries carry `status: 'queued'` and a sensible reduced shape (no timestamps or
  simulation statistics are available yet).
* `'queued'` is a supported and documented `status_filter` value (returns only queued tests).
* Queued entries are visible on the first page by default (they must not sink to the bottom of
  the default `end_time desc` ordering due to missing timestamps).
* Queued state is fresh: queue-API results are not subject to the 30-minute tests cache
  (mirroring the existing cache bypass for `status_filter='running'`).

### Affected Areas
* safebreach-mcp: `safebreach_mcp_data/data_functions.py` (`sb_get_tests`, filtering/ordering/
  cache), `safebreach_mcp_core/queue_state.py` (extend to read pending queue entries),
  `safebreach_mcp_data/data_server.py` (tool description), `safebreach_mcp_data/data_types.py`
  (queue-entry mapping), tests under `safebreach_mcp_data/tests/`, docs (README.md, CLAUDE.md).
```

### Acceptance Criteria

```markdown
* Calling `get_tests` with no status filter returns queued tests merged with running/terminal
  tests; each queued entry has `status: 'queued'` and its planRunId as `test_id`.
* Calling `get_tests` with `status_filter='queued'` returns only tests waiting in the
  orchestrator queue.
* A test queued via `run_scenario`/`quick_run`/`run_studio_attack` is visible in `get_tests`
  immediately after submission (not delayed by the tests cache).
* A test appearing in both the orchestrator queue and testsummaries during the consistency-lag
  window is returned once (deduplicated by planRunId).
* Queued tests appear on the first page under default ordering despite having no start/end time.
* Tool description and docs (README.md, CLAUDE.md) list 'queued' among the valid status_filter
  values.
* Unit tests cover: queue merge, dedupe, 'queued' filter, ordering placement, and cache-bypass
  behavior; e2e test exercises the queued flow where feasible.
```

### Suggested Labels/Components
- Component: safebreach-mcp / data server
- Labels: mcp

---
