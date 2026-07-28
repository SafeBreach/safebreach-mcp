# PRD: get_tests Returns Orchestrator-Queued Tests — SAF-33511

## 1. Overview

- **Title**: get_tests returns orchestrator-queued tests — SAF-33511
- **Task Type**: Bug fix
- **Purpose**: The MCP `get_tests` tool under-reports test activity: tests waiting in the
  orchestrator queue (beyond the 5 concurrent validate execution slots) are invisible because the
  tool's sole data source — the `testsummaries` data API — only reflects tests in a terminal state
  or occupying an active execution slot. Agents that queue tests via `run_scenario` / `quick_run` /
  `run_studio_attack` receive a planRunId with status `queued` and then cannot find that test in
  `get_tests`, breaking queue-then-monitor workflows.
- **Target Consumer**: AI agents consuming the SafeBreach MCP data server (and their end users —
  security engineers orchestrating tests).
- **Target Roles (RBAC)**: Any role permitted to read test summaries (read-only data access).
- **Key Benefits**:
  - `get_tests` presents the complete picture of test activity: queued → running → terminal.
  - Queue-then-monitor agent workflows work end-to-end without knowledge of internal platform APIs.
  - New `queued` status filter and `queue_position` field enable pending-work triage.
- **Business Alignment**: Reliability of the MCP tool suite as the agent-facing surface of the
  SafeBreach platform.
- **Originating Request**: [SAF-33511](https://safebreach.atlassian.net/browse/SAF-33511)
  (reporter: Niv Samama, High priority Bug).

## 1.5. Document Status

| Field | Value |
|-------|-------|
| **PRD Status** | Draft |
| **Last Updated** | 2026-07-28 10:56 |
| **Owner** | Yossi Attas (planning via AI Agent) |
| **Current Phase** | N/A |

## 2. Solution Description

### Chosen Solution — Approach A: fresh orchestrator-queue merge inside `sb_get_tests`

On every `get_tests` call whose `status_filter` could match a non-terminal test
(`None`, `queued`, `running`), fetch a **fresh** snapshot of the orchestrator queue
(`GET /api/orch/v4/accounts/{account_id}/queue`) — never cached — and merge its pending `queue[]`
entries into the (cached) `testsummaries` result set. Queued entries are mapped to the reduced
test shape with `status='queued'`, deduplicated against testsummaries rows by planRunId, and
pinned to the top of the first page. `testsummaries` `PENDING` rows (slotted, still generating
jobs) are normalized to `status='queued'` (user decision: two-state model — not started vs
running). The testsummaries 30-minute cache and the existing `running` cache bypass are untouched.

### Alternatives Considered

- **B — Merge inside `_get_all_tests_from_cache_or_api` with a short-TTL merged cache.**
  Pros: single merge point; downstream filter/order/pagination untouched.
  Cons: mixed-freshness cache entries (30-min testsummaries + seconds-fresh queue) invite subtle
  staleness bugs; complicates the existing `running` bypass logic.
- **C — Separate `get_queued_tests` tool.**
  Pros: zero merge complexity; could also expose slot occupancy.
  Cons: does not satisfy the ticket (queued tests must appear in the `get_tests` response);
  requires agents to discover a second tool.

### Decision Rationale

A fixes the tool where agents already look, guarantees queued state is always fresh (queued is
the most volatile state), keeps the cache semantics of the existing code untouched, and costs one
cheap HTTP call per relevant `get_tests` invocation.

## 3. Core Feature Components

### Component A: Orchestrator queue snapshot (core layer)

- **Purpose**: A reusable read of the orchestrator queue exposing pending tests and busy slots.
  Extends the existing `safebreach_mcp_core/queue_state.py` (currently only scans `slotState[]`
  for a single planRunId). Modification of existing module.
- **Key Features**:
  - `get_orchestrator_queue_snapshot(console)` returns the pending queue entries (trimmed — the
    large `originalPlan` payload is excluded), the busy-slot planRunIds, and the account-level
    `isPause` flag.
  - Confirmed live response shape (pentest01, 2026-07-28): `data.{isPause, slotState[], queue[],
    testRunState{}}`; pending entry keys: `planRunId`, `name`, `steps[]`, `actions[]`, `edges[]`,
    `systemTags[]`, `ranBy`, `ranFrom`, `retryPolicy`, `retrySimulations`, `priority`,
    `flowControl`, `originalPlan`. No queued-at timestamp exists; the planRunId prefix is the
    submission epoch-ms.
  - On API error: log a warning and return an empty snapshot (graceful degradation — `get_tests`
    then behaves exactly as today).

### Component B: Queued-test mapping (types layer)

- **Purpose**: Transform a pending queue entry into the reduced test shape returned by
  `get_tests`. New transform in `safebreach_mcp_data/data_types.py`.
- **Key Features**:
  - Fields: `test_id` (planRunId), `name`, `status='queued'`, `queued_time` (epoch seconds derived
    from the planRunId epoch-ms prefix), `queue_position` (1-based index in `queue[]`),
    `priority`, `ran_from`. `start_time`/`end_time`/`duration` absent (test has not started).
  - `PENDING` → `queued` status normalization for testsummaries rows (lifecycle: in queue →
    invisible to data API; slotted + generating jobs → `PENDING`; executing → `RUNNING`).

### Component C: Merge + filter + ordering in `sb_get_tests` (data layer)

- **Purpose**: Wire the snapshot into the tool response. Modification of
  `safebreach_mcp_data/data_functions.py`.
- **Key Features**:
  - Fetch the snapshot fresh when `status_filter` ∈ {None, `queued`, `running`}; skip it for
    terminal filters (completed/canceled/failed) where queued tests cannot match.
  - Dedupe by planRunId: a testsummaries row whose planRunId appears in `queue[]` is replaced by
    the queue entry (fresh queue data wins on status).
  - `status_filter='queued'` returns queue entries plus normalized-PENDING rows only. For
    `queued`, no server-side `&status=` param is sent (confirmed live: `status=QUEUED` returns 0
    rows even while tests are queued); filtering is client-side.
  - Add the missing `status_filter` validation: allowed values `completed`, `canceled`, `failed`,
    `running`, `queued` (case-insensitive), consistent with `order_by` validation.
  - Placement: queued entries are partitioned to the front of the result list (internally ordered
    by `queued_time` descending — newest submission first); the remaining tests follow the
    requested `order_by`/`order_direction`. Pagination applies to the partitioned list, so queued
    entries occupy the top of page 0.
  - Response metadata: `queued_tests_count` added; `hint_to_agent` notes that queued/pending
    states are point-in-time and routes to `manage_test` (cancel) and `get_test_details` (once
    running) for follow-up.

### Component D: Tool contract & docs

- **Purpose**: Advertise the new behavior. Modification of `safebreach_mcp_data/data_server.py`
  tool description plus `README.md` / `CLAUDE.md`.
- **Key Features**: `status_filter` documented as
  `'completed'/'canceled'/'failed'/'running'/'queued'/None`; queued placement, `queue_position`,
  and freshness semantics described.

## 4. API Endpoints and Integration

### Existing APIs to Consume

- **Orchestrator queue** (new consumer in `get_tests` path; already consumed by
  `get_orchestrator_test_state`):
  - **URL**: `GET {orch_base}/api/orch/v4/accounts/{account_id}/queue`
  - **Headers**: `accept: application/json`, `Authorization: Bearer {token}` (via
    `get_auth_headers_for_console`)
  - **Response Example** (trimmed, confirmed live):
    ```json
    {
      "data": {
        "isPause": false,
        "slotState": [
          {"id": "validate-0", "status": "Waiting for execution", "slotStatus": "Running Step",
           "planRunId": "1785200400269.2", "startTime": "2026-07-28T07:12:16.055Z",
           "isPaused": false, "jobsLeft": 1354034, "totalJobs": 8074240}
        ],
        "queue": [
          {"planRunId": "1785224437040.28", "name": "SAF-33511-queue-probe-4",
           "priority": "low", "ranBy": 347116670300007, "ranFrom": "API",
           "retryPolicy": "default", "retrySimulations": true,
           "steps": ["..."], "actions": ["..."], "edges": ["..."],
           "systemTags": [], "flowControl": {"pointer": 0, "conditionResults": {}},
           "originalPlan": {"...": "large - excluded from snapshot"}}
        ],
        "testRunState": {"<planRunId>": {"...": "full plan details"}}
      }
    }
    ```
- **Test summaries** (existing, unchanged):
  - **URL**: `GET {data_base}/api/data/v1/accounts/{account_id}/testsummaries?size=1000&includeArchived=false[&status=STATUS]`
  - Confirmed live: a queue-waiting test has **no row**; a slotted-but-preparing test appears with
    `status: "PENDING"` and null timestamps; `&status=QUEUED` returns 0 rows always.

### New APIs to Create

None — MCP-side change only.

## 6. Non-Functional Requirements

**Performance Requirements**:
- The queue snapshot adds one HTTP call (~100–300 ms observed) to `get_tests` invocations with
  `status_filter` ∈ {None, `queued`, `running`}. Terminal-status calls are unaffected.
- The snapshot is intentionally uncached: queued state is the most volatile and lowest-cardinality
  data in the system (bounded by queue depth).

**Technical Constraints**:
- Graceful degradation is mandatory: if the orchestrator queue API errors, `get_tests` must return
  the testsummaries-only result (today's behavior) — never fail the whole call.
- Backward compatibility of the tool response shape is explicitly NOT a constraint (user
  directive; consumers are AI agents reading tool descriptions at call time).
- Consistency lag: the orchestrator queue and testsummaries have a 10–15 s eventual-consistency
  window; dedupe by planRunId handles the transition overlap.

**Monitoring & Observability**:
- Warning-level log when the queue snapshot fetch fails (mirrors existing
  `get_orchestrator_test_state` behavior).

## 7. Definition of Done

- [ ] `get_tests` (no filter) returns queued tests merged with running/terminal tests; each queued
  entry has `status='queued'`, `test_id`=planRunId, `queued_time`, and `queue_position`.
- [ ] `get_tests(status_filter='queued')` returns only queue-waiting tests and normalized-PENDING
  rows.
- [ ] A test queued via `run_scenario`/`quick_run`/`run_studio_attack` is visible in `get_tests`
  immediately after submission (queue snapshot is never cached).
- [ ] A test present in both sources during the consistency-lag window appears exactly once
  (deduplicated by planRunId, queue status wins).
- [ ] Queued tests occupy the top of the first page under default ordering despite having no
  start/end time.
- [ ] testsummaries `PENDING` rows are presented as `queued`.
- [ ] Invalid `status_filter` values raise a clear validation error listing allowed values.
- [ ] Queue-API failure degrades gracefully to today's behavior (with a logged warning).
- [ ] Tool description, README.md, and CLAUDE.md document the new `queued` filter and semantics.
- [ ] Unit tests cover snapshot parsing, mapping, merge, dedupe, filter, ordering/placement, and
  degradation; e2e test exercises the queued flow on pentest01.

## 8. Testing Strategy

**Unit Testing** (pytest, existing suites):
- `safebreach_mcp_core/tests`: `get_orchestrator_queue_snapshot` — parses `queue[]` +
  `slotState[]` + `isPause`; excludes `originalPlan`; returns empty snapshot on HTTP error /
  malformed body (mock `requests`).
- `safebreach_mcp_data/tests/test_data_types.py`: queued-entry mapping (field set, epoch-ms prefix
  derivation, queue_position); `PENDING`→`queued` normalization; existing status-verbatim
  assertions extended.
- `safebreach_mcp_data/tests/test_data_functions.py`: merge (queued present in page 0 head);
  dedupe (same planRunId in both sources → one row, status `queued`); `status_filter='queued'`
  (client-side, no server `&status=` param); `status_filter` validation errors; terminal filters
  skip the snapshot call (assert no queue request); graceful degradation; ordering partition with
  each `order_by`; pagination totals include queued entries.
- `safebreach_mcp_data/tests/test_data_server.py`: tool description advertises `queued`.

**Integration / E2E Testing**:
- `safebreach_mcp_data/tests/test_e2e.py` (`@pytest.mark.e2e`, pentest01): submit
  slot-count+1 tiny quick-run tests, assert the queued one appears in `get_tests` page 0 with
  `status='queued'` and correct `queue_position`, then cancel all (mirrors the planning probe;
  cleanup in `finally`).
- **Test Environment**: pentest01 (`pentest01_apitoken` via env), guarded by existing e2e marker
  exclusion.

**Coverage Gaps**: Slot-progress enrichment and queued-test support in `get_test_details` are out
of scope (see Section 11).

## 9. Implementation Phases

| Phase | Status | Completed | Commit SHA | Notes |
|-------|--------|-----------|------------|-------|
| Phase 1: Queue snapshot (core) | ⏳ Pending | - | - | |
| Phase 2: Queued-test mapping (types) | ⏳ Pending | - | - | |
| Phase 3: Merge/filter/ordering (data) | ⏳ Pending | - | - | |
| Phase 4: Tool contract & docs | ⏳ Pending | - | - | |
| Phase 5: E2E queued-flow test | ⏳ Pending | - | - | |

### Phase 1: Queue snapshot (core)

- **Semantic Change**: Add a reusable orchestrator-queue snapshot reader to the core layer.
- **Deliverables**: `get_orchestrator_queue_snapshot(console)` in
  `safebreach_mcp_core/queue_state.py` + unit tests.
- **Implementation Details**:
  - New function alongside `get_orchestrator_test_state`, reusing the same URL construction,
    auth-header helper, RBAC check, and 30 s timeout.
  - Input: console name. Output: a snapshot object (dict or small dataclass) with three members —
    `pending`: the list of `queue[]` entries each trimmed to planRunId, name, priority, ranBy,
    ranFrom, systemTags, and the number of steps (drop `originalPlan`, `steps` bodies, `actions`,
    `edges`, `flowControl`); `busy_plan_run_ids`: planRunIds of non-idle `slotState[]` entries;
    `is_paused`: the account-level `isPause` flag.
  - Preserve `queue[]` order (it is the queue order; positions derive from list index downstream).
  - Error path: any exception (HTTP, JSON, RBAC) logs a warning and returns an empty snapshot
    (empty pending list, empty busy set, is_paused False). Callers need no try/except.
- **What can go wrong**: endpoint missing on old consoles (404 → empty snapshot); malformed body
  (missing `data`/`queue` keys → treat as empty).
- **Changes**:

  | File | Change |
  |------|--------|
  | `safebreach_mcp_core/queue_state.py` | Add `get_orchestrator_queue_snapshot` |
  | `safebreach_mcp_core/tests/test_queue_state.py` (or existing core test module) | Snapshot parsing, trimming, error-path tests |

- **Git Commit**: `feat(core): add orchestrator queue snapshot reader (SAF-33511)`

### Phase 2: Queued-test mapping (types)

- **Semantic Change**: Add the queued-entry → reduced-test transform and PENDING normalization.
- **Deliverables**: New mapping function + status normalization in
  `safebreach_mcp_data/data_types.py` + unit tests.
- **Implementation Details**:
  - New function taking a trimmed pending entry and its 0-based index; returns the reduced test
    dict: `test_id` = planRunId, `name`, `status` = `'queued'`, `queued_time` = int(planRunId
    prefix before the dot) / 1000 (epoch seconds, consistent with other time fields),
    `queue_position` = index + 1, `priority`, `ran_from`. Omit `start_time`/`end_time`/`duration`
    (consistent with `map_reduced_entity` skipping missing keys).
  - Defensive parsing of the planRunId prefix: on non-numeric prefix, omit `queued_time`.
  - In `get_reduced_test_summary_mapping`: normalize a raw `status` of `PENDING`
    (case-insensitive) to `queued` so slotted-but-preparing tests group with queued (user
    decision). All other statuses remain verbatim.
- **What can go wrong**: malformed planRunId (handled above); PENDING row with partial fields
  (mapping already tolerates missing keys).
- **Changes**:

  | File | Change |
  |------|--------|
  | `safebreach_mcp_data/data_types.py` | Add queued mapping fn; PENDING→queued normalization |
  | `safebreach_mcp_data/tests/test_data_types.py` | Mapping + normalization tests; extend status-verbatim tests |

- **Git Commit**: `feat(data): map orchestrator queue entries to reduced test shape (SAF-33511)`

### Phase 3: Merge/filter/ordering (data)

- **Semantic Change**: Merge fresh queue data into `sb_get_tests` with dedupe, `queued` filter,
  validation, and top-of-page placement.
- **Deliverables**: Updated `sb_get_tests` / `_apply_filters` / `_apply_ordering` flow + unit
  tests.
- **Implementation Details**:
  - Validate `status_filter` early (pattern of `valid_order_by`): allowed
    completed/canceled/failed/running/queued, case-insensitive; raise ValueError listing allowed
    values otherwise.
  - When normalized `status_filter` ∈ {None, `queued`, `running`}: call
    `get_orchestrator_queue_snapshot(console)`. For `queued`, do NOT pass a server-side `&status=`
    param to testsummaries (fetch the unfiltered, cached list and filter client-side — needed to
    catch PENDING rows). For terminal filters, skip the snapshot entirely (no behavior change).
  - Merge order: map pending entries via the Phase 2 transform → collect their planRunIds → drop
    any testsummaries row with a matching planRunId → concatenate.
  - Filtering: existing `_apply_filters` client-side status comparison works once PENDING is
    normalized and queued entries carry `status='queued'`; date-range filters skip entries without
    the timestamp keys (existing behavior — verify queued entries pass through name filters).
  - Ordering: partition into (queued, rest); sort queued by `queued_time` descending; sort rest
    with existing `_apply_ordering`; concatenate queued-first; paginate the concatenated list.
  - Response: add `queued_tests_count`; extend `hint_to_agent` (queued is point-in-time; cancel
    via `manage_test`; details available via `get_test_details` once the test starts).
  - Data flow: sb_get_tests → [cached testsummaries] + [fresh snapshot] → map/normalize → dedupe →
    filter → partition-order → paginate → envelope.
- **What can go wrong**: snapshot empty on error → response identical to today; test transitions
  queue→slot mid-merge → dedupe keeps one row; queue deeper than a page → queued entries spill
  onto page 1 (acceptable, ordered).
- **Changes**:

  | File | Change |
  |------|--------|
  | `safebreach_mcp_data/data_functions.py` | status_filter validation; snapshot fetch + merge + dedupe; partition ordering; response metadata |
  | `safebreach_mcp_data/tests/test_data_functions.py` | Merge, dedupe, filter, validation, skip-snapshot, degradation, ordering, pagination tests |

- **Git Commit**: `fix(data): merge orchestrator-queued tests into get_tests (SAF-33511)`

### Phase 4: Tool contract & docs

- **Semantic Change**: Advertise the new contract in the tool description and docs.
- **Deliverables**: Updated `get_tests` docstring/description, README.md, CLAUDE.md.
- **Implementation Details**: `status_filter` enum text gains `'queued'`; document queued
  semantics (fresh, top-of-page, `queue_position`, PENDING grouped under queued), and the
  `queued_tests_count` field. Update the two docs' status_filter enumerations and the tool
  feature bullets.
- **Changes**:

  | File | Change |
  |------|--------|
  | `safebreach_mcp_data/data_server.py` | Tool description update |
  | `safebreach_mcp_data/tests/test_data_server.py` | Description assertions |
  | `README.md`, `CLAUDE.md` | status_filter docs + tool notes |

- **Git Commit**: `docs(data): document queued status in get_tests contract (SAF-33511)`

### Phase 5: E2E queued-flow test

- **Semantic Change**: Live-console regression coverage for the queued flow.
- **Deliverables**: New `@pytest.mark.e2e` test in `safebreach_mcp_data/tests/test_e2e.py`.
- **Implementation Details**: Read the current busy validate-slot count from the snapshot; submit
  enough tiny quick-run tests (attack 11653, 1 attack each) to fill remaining slots plus one
  queued; poll `sb_get_tests` (no filter) and assert the queued planRunId appears on page 0 with
  `status='queued'` and a positive `queue_position`; also assert `status_filter='queued'` returns
  it; cancel all submitted tests in a `finally` block and verify the queue drains. Skip the test
  (pytest.skip) if the console queue is paused or slots cannot be saturated within a bounded
  number of submissions.
- **What can go wrong**: shared-console interference (another user's tests occupy slots — the
  fill-to-saturation approach handles it); leftover probe tests on failure (finally-block cancel
  by collected planRunIds).
- **Changes**:

  | File | Change |
  |------|--------|
  | `safebreach_mcp_data/tests/test_e2e.py` | Queued-flow e2e test with cleanup |

- **Git Commit**: `test(data): e2e coverage for queued tests in get_tests (SAF-33511)`

## 10. Risks and Assumptions

**Technical Risks**:

| Risk | Impact | Mitigation |
|------|--------|------------|
| Stale `PENDING` rows from the 30-min cache presented as `queued` after the test already started/finished | Medium | Fresh snapshot accompanies every non-terminal call — implementation may optionally reconcile cached PENDING rows against `busy_plan_run_ids`/`pending`; at minimum the `hint_to_agent` marks queued/pending as point-in-time. Flag for code review. |
| Orchestrator `/queue` endpoint shape differs on older consoles | Medium | Graceful degradation to empty snapshot (today's behavior); defensive key access |
| planRunId prefix not being a timestamp on some platform versions | Low | Defensive parse; omit `queued_time` when non-numeric (placement still works via partition) |
| Shared-console e2e flakiness (slots occupied by other users) | Low | Fill-to-saturation approach + skip guard + finally-block cleanup |

**Assumptions Under Question**:
- The `queue[]` array order is the authoritative queue order (used for `queue_position`). Verified
  plausible on pentest01 (single pending entry); re-verify with 2+ pending during implementation.
- `propagate` tests queue into the same `queue[]` (only validate slots were probed). The merge is
  type-agnostic either way.

## 11. Future Enhancements

- **Slot-progress enrichment for running tests**: `jobsLeft`/`totalJobs`/`maxRemainingSimulations`
  from `slotState[]` could give agents live progress percentages in `get_tests`/`get_test_details`.
- **Queued-test support in `get_test_details`**: today a queued planRunId 404s on
  `testsummaries/{id}`; the tool could fall back to the queue snapshot and return a queued
  envelope.
- **Queue-depth signal in write tools**: `run_scenario`/`quick_run` responses could include the
  current queue depth (`queue_position` of the just-submitted test) so agents can set polling
  expectations at submission time.

## 12. Executive Summary

- **Issue/Feature Description**: The MCP `get_tests` tool omits tests waiting in the orchestrator
  execution queue, so agents lose sight of tests they just queued (SAF-33511, High-priority bug).
- **What Was Built** *(planned)*: A fresh orchestrator-queue merge inside `sb_get_tests`: a new
  core snapshot reader, a queued-entry transform (`status='queued'`, derived `queued_time`,
  `queue_position`), planRunId dedupe, a validated `queued` status filter, PENDING→queued
  normalization, and top-of-first-page placement — with graceful degradation when the queue API is
  unavailable.
- **Key Technical Decisions**: Fresh (uncached) queue reads on every non-terminal `get_tests`
  call; PENDING grouped under `queued` (two-state model: not started vs running); queued entries
  pinned above the requested ordering; backward compatibility explicitly waived for MCP tool
  responses. RCA and API shapes confirmed live on pentest01 (queue-waiting tests have no
  testsummaries row; `&status=QUEUED` is non-functional).
- **Scope Changes**: None vs the ticket; slot-progress enrichment and `get_test_details` queued
  support deferred (Section 11).
- **Business Value Delivered**: Complete queued→running→terminal visibility in the agents' primary
  test-listing tool, unblocking queue-then-monitor automation.

## 14. Change Log

| Date | Change Description |
|------|-------------------|
| 2026-07-28 10:56 | PRD created — initial draft |
