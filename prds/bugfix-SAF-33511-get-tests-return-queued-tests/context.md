# Ticket Context: SAF-33511

## Status
Phase 3: Create Working Branch and PRD Context (planning-dev-task)

## Planning Inputs (planning-dev-task)

### Related Tickets (finding-related-tickets verdict: PROCEED)
No duplicates found. Related-context only:
- SAF-32366 (Sanity, open) — backend/orchestrator: queued tests slow to appear in testsummaries
  under queue backlog (server-side ingestion lag). Same theme, different root cause.
- SAF-29965 (Done) — original ticket adding the running-tests listing to get_tests.
- SAF-33323 (In Progress) — same get_tests tool, different bug (500 when status_filter=running).
- SAF-33124 (Done) — same repo area, different tool (get_test_drifts).

### User Decisions
- Queued tests placement: **top of first page** under default ordering (end_time desc) — queued
  tests are the newest pending work and must be visible.
- Backward compatibility of MCP tool responses: explicitly NOT a concern.
- Live-console research required against **pentest01** (pentest01.safebreach.com, account
  3471166703; token via `pentest01_apitoken` in ~/Public/safebreach-mcp/.env) to document the
  orchestrator /queue pending-entry shape and testsummaries behavior for queued tests.
- No additional data sources beyond ticket + preparing-ticket investigation + live research.

## Mode
Improving

## Original Ticket
- **Summary**: safebreach-mcp: "get test summaries" tool should also return queued tests in the response
- **Description**: The SafeBreach MCP `get test summaries` tool does not include queued tests in its response. The tool currently only returns tests that are already running or completed, so consumers of the tool lack visibility into pending tests that have been queued for execution. Expected behavior: queued tests should be included in the response to provide a complete picture of all pending and active tests.
- **Acceptance Criteria**: (none specified in ticket)
- **Status**: To Do
- **Type**: Bug
- **Priority**: High
- **Reporter**: Niv Samama
- **Assignee**: Sebastian Altheim

## Task Scope
Derived from ticket description: investigate why the tests-listing tool (`get_tests`, backed by the testsummaries API) does not surface queued tests, identify where queued tests live in the SafeBreach API surface, and determine what changes are needed for the MCP data server to include queued tests in its response.

## Repositories Under Investigation
- /Users/yossiattas/projects/safebreach-mcp

## Investigation Findings

### safebreach-mcp (/Users/yossiattas/projects/safebreach-mcp)

**Tool implementation:**
- Tool `get_tests` registered in `safebreach_mcp_data/data_server.py:55-96`; the tool description
  (line 63) advertises `status_filter` values as only `'completed'/'canceled'/'failed'/'running'/None`
  — `'queued'` is not advertised.
- Business logic `sb_get_tests` in `safebreach_mcp_data/data_functions.py:81-228`. There is NO
  validation/enum for `status_filter` (unlike `order_by`), so `'queued'` passes through unvalidated.
- API call (`_get_all_tests_from_cache_or_api`, `data_functions.py:231-294`):
  `GET {data}/api/data/v1/accounts/{account_id}/testsummaries?size=1000&includeArchived=false`,
  with `&status={STATUS}` appended only when a status filter is provided (line 263-264).
- Cache: `tests_cache` TTL=1800s, maxsize=5 (`data_functions.py:36`). Only `status_filter='running'`
  bypasses the cache (line 138); the default no-filter call is cached up to 30 min.

**Why queued tests are missing — two mechanisms:**
- **Mechanism A (confirmed in code): ordering buries queued tests.** Queued tests have no
  `endTime`/`startTime`; the transform (`data_types.py:19-20`, `map_reduced_entity` skips missing
  keys) leaves both fields absent. Default ordering `end_time desc` uses
  `_get_timestamp_from_keys(..., default=float('-inf'))` (`data_functions.py:388`), so queued tests
  sort to the very BOTTOM. With PAGE_SIZE=10 and up to 1000 tests fetched, queued tests are
  effectively invisible on page 0.
- **Mechanism B (needs live-API confirmation): the default `testsummaries` list may not include
  queued rows at all.** `QUEUED` is a real testsummaries status value
  (`studio_functions.py:1552-1554` documents running/completed/canceled/failed/queued for the
  single-test endpoint), but whether the LIST endpoint returns queued rows without an explicit
  `&status=QUEUED` is unconfirmed. Also, `queue_state.py:4-6` documents a 10-15s
  eventual-consistency lag between the orchestrator queue and the testsummaries data API.

**Not a factor:** `get_reduced_test_summary_mapping` (`data_types.py:153-180`) copies `status`
verbatim and does not drop entries lacking timestamps — queued rows survive the transform.

**Queued-test producers (the gap's consumers):** `run_scenario`, `quick_run`, `run_studio_attack`
all submit via `POST /api/orch/v4/accounts/{account_id}/queue` (`_submit_to_queue`,
`studio_functions.py:146-198`) and return `test_id`=planRunId with literal `status: 'queued'`.
That planRunId is exactly what `get_tests` currently cannot surface.

**Reusable queue-read surface:** `safebreach_mcp_core/queue_state.py` —
`get_orchestrator_test_state()` reads `GET /api/orch/v4/accounts/{account_id}/queue` but only scans
active `slotState[]` (returns RUNNING/PAUSED/None); it does not surface pending/queued entries.
Consumed by `sb_get_test_details` for non-terminal refresh (`data_functions.py:483-498`).

**Tests/docs needing updates:**
- `safebreach_mcp_data/tests/test_data_functions.py`: `test_apply_filters_running_status` (297-310)
  as precedent; `test_apply_ordering*` (324-352); missing-end_time handling (355-368); API URL
  assertions (194-225).
- `safebreach_mcp_data/tests/test_data_server.py`: tool-description assertions (status enum string).
- `safebreach_mcp_data/tests/test_data_types.py:809-811`: status-verbatim assertions; extend for queued.
- `safebreach_mcp_data/tests/test_e2e.py`: `get_tests` e2e at lines 52, 121, 164, 649.
- Docs: `README.md:873`, `CLAUDE.md:486` enumerate status_filter values.

**Risks/complexity:**
- Ordering fix required for visibility, not just inclusion (queued → `-inf` under both
  end_time and start_time ordering).
- Cache TTL 30 min means newly queued tests would be stale unless queued (like running) bypasses cache.
- Server-side `&status=QUEUED` behavior untested against real API; may require orchestrator /queue merge.
- Backward compatibility: adding queued rows changes total_tests/total_pages/page contents for
  existing default calls; queued rows have null timestamps and all-zero simulations_statistics
  (`finalStatus={}` → zeros via `_build_simulation_status_counts`, `data_types.py:82-139`); the
  SAF-32018 non-terminal hint (`data_functions.py:202-215`) would fire for queued tests too.

**Precedent:** SAF-30863 (`prds/SAF-30863-get_tests_history-add-running-filter/summary.md`) added
`running` as a status_filter — same shape of change, but SAF-33511 additionally needs the
ordering/visibility fix and possibly an orchestrator-queue data source.

## Problem Analysis

### Confirmed RCA (from reporter/user context)
The SafeBreach platform has **five slots** for simultaneous test execution. Tests submitted beyond
the five available slots are queued, waiting for a free execution slot. The `testsummaries` data
API — the sole data source of `sb_get_tests` — only reflects tests in a **terminal state** or tests
associated with an **active execution slot**. Tests waiting in the queue are invisible to it.
Therefore `sb_get_tests` is structurally unaware of queued tests; **the fix requires merging
results from the orchestrator `queue` API** (`GET /api/orch/v4/accounts/{account_id}/queue`).

This supersedes "Mechanism B" uncertainty from Phase 4: the list API does NOT return queued rows;
a pure client-side fix (ordering/filter enum) is insufficient.

### Problem Scope
- `sb_get_tests` (`safebreach_mcp_data/data_functions.py:81-228`) returns an incomplete picture of
  test activity: an agent that queues tests via `run_scenario`/`quick_run`/`run_studio_attack`
  (which return planRunId + status 'queued') cannot subsequently see those tests in `get_tests`
  until they occupy an execution slot.
- The gap is a missing data source, not a filter/transform bug: queued tests must be read from the
  orchestrator queue API and merged into the `get_tests` response.

### Affected Areas
- `safebreach_mcp_data/data_functions.py` — `sb_get_tests`, `_get_all_tests_from_cache_or_api`,
  `_apply_filters`, `_apply_ordering` (merge point, 'queued' status filter, ordering for
  timestamp-less queued entries, cache-freshness handling)
- `safebreach_mcp_core/queue_state.py` — existing orchestrator queue reader; currently only scans
  active `slotState[]`; natural place to extend for pending/queued queue entries
- `safebreach_mcp_data/data_server.py:55-96` — `get_tests` tool description (advertise 'queued')
- `safebreach_mcp_data/data_types.py` — mapping for queue-API entries into the reduced test shape
- Tests: `test_data_functions.py`, `test_data_server.py`, `test_data_types.py`, `test_e2e.py`
- Docs: `README.md`, `CLAUDE.md` status_filter enumerations

### Dependencies
- Orchestrator queue API response shape (`data.slotState[]` for active slots; pending entries'
  exact shape to be confirmed during implementation)
- Eventual-consistency lag (10-15s) between orchestrator queue and testsummaries
  (`queue_state.py:4-6`)

### Risks & Edge Cases
- **Freshness**: tests cache TTL=1800s; queued state is the most volatile — queue API results
  should not be cached long (or at all), mirroring the `running` cache bypass.
- **Ordering/visibility**: queued tests have no start/end time; under default `end_time desc` they
  sort to `-inf` (bottom). Merged queued entries need deliberate placement (e.g., top of the list)
  or a sort-key fallback so inclusion actually yields visibility.
- **Shape consistency**: queue entries won't have testsummaries fields (finalStatus counts,
  end_time, duration); the merged entries need a sensible reduced representation.
- **Double counting**: a test transitioning queue→slot around the merge moment could appear in
  both sources (consistency lag); merge must dedupe by planRunId.
- **Status filter semantics**: `status_filter='queued'` should return only queue entries;
  no-filter calls should include them merged.
- Backward compatibility of tool responses is explicitly NOT a concern (per user).

### Open Questions
- Exact shape of pending (non-slot) entries in the orchestrator `/queue` response — confirm
  against a live console during implementation.

## Proposed Improvements
(Phase 6)
