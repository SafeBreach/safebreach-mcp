# Ticket Context: SAF-33511

## Status
Phase 5: Brainstorm (planning-dev-task)

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

## Live Console Research (pentest01, 2026-07-28)

Method: saturated the validate slots with tiny quick-run tests (attack 11653), captured
`GET /api/orch/v4/accounts/3471166703/queue` and `GET /api/data/v1/accounts/3471166703/testsummaries`
while one test was waiting in the queue, then canceled all probe tests. Console restored to prior
state (only the pre-existing scheduled scenario running).

### Orchestrator /queue response shape (confirmed live)
`data` top-level keys: `isPause` (bool), `slotState[]`, `queue[]`, `testRunState{}`.
- **`slotState[]`** — 6 slots on pentest01: `validate-0..4` and `propagate-0` (slots are per
  test type; "5 slots" refers to validate). Slot entry keys: `id`, `status` (e.g. "Idle",
  "Waiting for execution", "Generating jobs"), `slotStatus` (e.g. "Idle", "Running Step"),
  `planRunId` (null when idle), `runId`, `stepRunId`, `name`, `description`, `startTime` (ISO),
  `isPaused`, `pauseDuration`, `pausedDate`, `jobsLeft`, `jobsDispatched`, `totalJobs`,
  `maxRemainingSimulations`.
- **`queue[]`** — pending tests waiting for a slot. Entry top-level keys (confirmed):
  `planRunId`, `name`, `steps[]`, `actions[]`, `edges[]`, `systemTags[]`, `ranBy` (numeric user id),
  `ranFrom` ("API"), `retryPolicy`, `retrySimulations`, `priority` ("low"), `flowControl`,
  `originalPlan` (full plan payload — large). **No queued-at timestamp field**, but the planRunId
  prefix IS the submission epoch-ms (`"1785224437040.28"` → 1785224437040), usable as a derived
  submit time.
- **`testRunState{}`** — dict keyed by planRunId (covers both slot-active and queue-pending tests)
  with full plan details (id, name, accountId, description, originalScenarioId, actions, ...).

### testsummaries behavior while a test waits in the queue (confirmed live)
- A test waiting in `data.queue[]` is **completely ABSENT from the testsummaries list** (no row at
  all) — confirming the RCA. It materializes in testsummaries only after leaving the queue
  (e.g., as CANCELED after cancellation, or RUNNING once slotted).
- A test that has taken a slot but is still preparing ("Generating jobs", no startTime yet)
  appears in testsummaries with **status `PENDING`** (`startTime: null`, `endTime: null`).
  `PENDING` is a real testsummaries list status that the MCP layer currently neither advertises
  nor handles specially. Observed status population: CANCELED / COMPLETED / RUNNING / PENDING.
- `testsummaries?status=QUEUED` returned **0 rows even while a test was queued** — `QUEUED` is not
  a functioning server-side list filter value; the queue-waiting state simply doesn't exist in the
  data API.
- testsummaries rows use `planName` (not `name`); row keys confirmed: planRunId, runId, planName,
  status, startTime, endTime, duration, pauseDuration, blocked, notBlocked, internalFail,
  finalStatus, draft, ranBy, tags, systemTags, simulatorCount, simulatorExecutions,
  totalNumberOfSimulators, plannedSimulationsAmount, constraintsSkipped, securityActionPerControl.

### Design implications
1. Queue-waiting tests can ONLY come from orchestrator `data.queue[]` — merge is mandatory (RCA
   confirmed end-to-end).
2. Dedupe by planRunId across queue[] and testsummaries (a test can transition mid-merge).
3. `PENDING` (slot taken, generating jobs) should be considered: either surfaced as-is or grouped
   with queued/running semantics — decision for brainstorming.
4. Queued entries have no timestamps; derive submit time from the planRunId epoch-ms prefix for
   ordering/display. Placement decision: top of first page (user-approved).
5. `slotState[]` also provides progress fields (jobsLeft/totalJobs) — potential enrichment for
   running tests, out of scope unless cheap.
6. Probe artifacts left on console: 11 canceled + 1 completed test named `SAF-33511-queue-probe-*`
   (harmless; can be deleted later).

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

## Brainstorming Results (planning-dev-task Phase 5)

### Chosen Approach: A — Fresh queue merge inside sb_get_tests
- New core function `get_orchestrator_queue_snapshot(console)` in `safebreach_mcp_core/queue_state.py`
  returning pending `queue[]` entries + busy `slotState[]`. Fetched FRESH on every relevant
  `get_tests` call — never cached (single cheap HTTP call). testsummaries 30-min cache untouched.
- Skip the queue call when `status_filter` is terminal (completed/canceled/failed) — queued tests
  cannot match.
- Map `queue[]` entries to the reduced test shape: `test_id`=planRunId, `name`, `status='queued'`,
  submit time derived from planRunId epoch-ms prefix, `priority`, `ran_from`,
  `queue_position` (1-based index in queue[] — user-approved enrichment; no slot-progress
  enrichment).
- Normalize testsummaries `PENDING` rows → `status='queued'` (user decision: group PENDING under
  queued).
- Dedupe merged results by planRunId; fresh queue data wins on status.
- Placement: queued entries pinned at the TOP of page 1 (sorted among themselves by derived submit
  time desc); remaining tests follow the requested ordering (user-approved).
- `status_filter='queued'` returns only queued entries; add missing status_filter validation
  (valid: completed/canceled/failed/running/queued).
- Backward compatibility: not a constraint (user directive).

### Rejected Alternatives
- B — merge inside `_get_all_tests_from_cache_or_api` with short-TTL merged cache: cache-semantics
  complexity (interplay with existing 'running' bypass), staleness risk.
- C — separate `get_queued_tests` tool: does not satisfy the ticket (queued tests must appear in
  the `get_tests` response); requires agents to know a second tool.

## Proposed Improvements
(see summary.md — Proposed Ticket Content; posted to JIRA as comment on 2026-07-28)
