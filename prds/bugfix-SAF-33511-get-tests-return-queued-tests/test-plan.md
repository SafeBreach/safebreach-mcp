# Test Plan — get_tests Returns Orchestrator-Queued Tests (SAF-33511)

> PRD: ./prd.md  |  Branch: bugfix/SAF-33511-get-tests-return-queued-tests  |  Status: Draft  |  Updated: 2026-07-28 11:08

## Status & Review

| Field | Value |
|-------|-------|
| Status | Draft (In Sync with PRD v1) |
| Offering / surface | Validate (MCP data server reading console orchestrator + data APIs) |
| Dev review | — |
| QA review | — |

## Requirements Traceability

Sources: JIRA acceptance criteria (SAF-33511 investigation comment) ∪ PRD §7 Definition of Done
(user-confirmed at the authoring gate).

| Req | Requirement (from SAF-33511 ∪ PRD §7) | Covered by | Status |
|-----|----------------------------------------|------------|--------|
| R1 | `get_tests` (no filter) merges queued tests — each with `status='queued'`, `test_id`=planRunId, `queued_time`, `queue_position` | T-6, T-16, T-18 | Covered |
| R2 | `status_filter='queued'` returns only queue-waiting tests + normalized-PENDING rows | T-8, T-16 | Covered |
| R3 | A freshly queued test is visible immediately (queue snapshot never cached) | T-14, T-16 | Covered |
| R4 | A test in both sources during the consistency lag appears exactly once (planRunId dedupe) | T-7 | Covered |
| R5 | Queued tests occupy the top of page 1 under default ordering | T-12, T-16 | Covered |
| R6 | testsummaries `PENDING` rows are presented as `queued` | T-5 | Covered |
| R7 | Invalid `status_filter` raises a clear validation error listing allowed values | T-9 | Covered |
| R8 | Queue-API failure degrades gracefully to today's behavior (logged warning) | T-11 | Covered |
| R9 | Tool description + README + CLAUDE.md document the `queued` filter and semantics | T-15 | Covered |

## Change Coverage

| File | Covered by | Justification (if no unit test) |
|------|------------|---------------------------------|
| safebreach_mcp_core/queue_state.py | T-1, T-2 | — |
| safebreach_mcp_core/tests/test_queue_state.py | — | test code (new file hosting T-1, T-2) |
| safebreach_mcp_data/data_types.py | T-3, T-4, T-5 | — |
| safebreach_mcp_data/tests/test_data_types.py | — | test code (hosts T-3, T-4, T-5) |
| safebreach_mcp_data/data_functions.py | T-6, T-7, T-8, T-9, T-10, T-11, T-12, T-13, T-14 | — |
| safebreach_mcp_data/tests/test_data_functions.py | — | test code (hosts T-6..T-14) |
| safebreach_mcp_data/data_server.py | T-15 | — |
| safebreach_mcp_data/tests/test_data_server.py | — | test code (hosts T-15) |
| safebreach_mcp_data/tests/test_e2e.py | — | test code (hosts T-16) |
| README.md | — | docs-only, no runtime surface (contract text asserted by T-15 at the tool layer) |
| CLAUDE.md | — | docs-only, no runtime surface |

## Risk Landscape

- Known risk areas (PRD §10 + gate input): stale cached `PENDING` rows presented as `queued` after
  the test moved on (30-min tests cache); orchestrator `/queue` shape differences on older
  consoles; planRunId prefix not an epoch timestamp on some platform versions; shared-console e2e
  flakiness (pentest01 slots occupied by other users; exact `queue_position` assertions fragile);
  the validate slot count (5 on pentest01) is console-configurable — saturation logic must read the
  actual slot state, never hardcode 5.
- Existing coverage (investigated): `sb_get_tests` filter/order/pagination →
  `safebreach_mcp_data/tests/test_data_functions.py` (e.g. `test_apply_filters_running_status`,
  `test_apply_ordering_handles_missing_timestamps`, `test_sb_get_tests_with_pagination`);
  testsummaries mapping → `safebreach_mcp_data/tests/test_data_types.py::TestTestSummaryMapping`;
  read-only data e2e → `safebreach_mcp_data/tests/test_e2e.py`; submit-and-cancel e2e precedent →
  `safebreach_mcp_studio/tests/test_e2e_quick_run.py::test_queue_and_cancel`.
  `safebreach_mcp_core/queue_state.py` has ZERO direct unit coverage today — this plan closes that
  gap. This plan targets the gaps; it does not duplicate the existing assertions.
- What we protect: existing `get_tests` behavior for terminal/running tests (filters, ordering,
  pagination, cache semantics incl. the `running` bypass); the graceful-degradation guarantee that
  a queue-API outage never breaks `get_tests`.
- Intentionally out of scope: queued-test support in `get_test_details` and slot-progress
  enrichment (PRD §11 future enhancements); exact `queue_position` value assertions on a shared
  console beyond "≥ 1" (other users' queue entries make absolute positions non-deterministic);
  automated verification of README/CLAUDE prose (docs-only, no runtime surface — the tool-layer
  contract is asserted by T-15).

## Coverage Summary (generated)

| Execution | unit | integration | system | e2e | Total |
|-----------|------|-------------|--------|-----|-------|
| Automatic | 15 | 0 | 0 | 1 | 16 |
| Manual | 0 | 0 | 1 | 1 | 2 |

## Environment Requirements (aggregated)

- Environment classes: none (all unit tests); console environment (Validate) — the existing live
  pentest01 console (T-16, T-17, T-18); no new provisioning required.

Capability checklist — answered from the plan's system/e2e tests only:

- [x] Simulators required? — Yes: the queue-saturating quick-run submissions (T-16, T-18) need ≥1
  connected+enabled simulator on the console so the submitted test predicts >0 simulations.
- [x] Running simulations / attacks required? — Yes: a queued orchestrator entry is live, ephemeral
  state that cannot be pre-seeded; tests must submit (and cancel) real validate test runs.
- [x] Mockulators sufficient? — No for the plan of record: pentest01's real simulators are used;
  mockulators are a documented fallback (queue placement doesn't need attack fidelity) with a
  timing caveat — tests must hold slots long enough for the queued snapshot.
- [x] Console-specific configuration required? — Yes, minimal: a valid API token
  (`pentest01_apitoken` env var + `E2E_CONSOLE=pentest01`) with permission to submit and cancel
  tests; no RBAC roles, flags, connectors, or seeded data.
- [x] Lateral-movement topology required? — No: pure Validate flow (despite the console's name).
- Required additions (beyond class defaults): none.
- Artifacts under test: the repo working tree (e2e runs the MCP functions in-process against the
  live console; no feature-branch image or installer track).

## Regression

- CI that must pass: **ACCEPTED GAP (user-approved 2026-07-28)** — this repo has no hosted pytest
  CI (GitHub Actions runs only security-scan and release), and no `Automation-Pen-Testing-*` suite
  maps to this surface (the `automation` repo carries no MCP coverage; this repo's own
  `test_e2e*.py` files are the system/e2e layer). The regression mechanism of record is the local
  unit gate — `uv run pytest` over all server-module test dirs with `-m "not e2e"` — run before
  merge and recorded as evidence by the executor. Adding a hosted pytest workflow was offered and
  declined as out of scope for SAF-33511.
- Regression tests in this plan: T-17 (Manual regression), plus the Automatic suite T-1..T-15
  which re-runs cumulatively each phase.

## Tests

**Unit** — all Automatic; environment: none

| Test | Description | Aspect | Passes after | Repo |
|------|-------------|--------|--------------|------|
| T-1 | Queue snapshot parses pending entries (trimmed), busy slots, and pause flag in queue order | API-contract | Phase 1 | safebreach_mcp_core |
| T-2 | Queue snapshot degrades to an empty snapshot on any API/parse failure | regression | Phase 1 | safebreach_mcp_core |
| T-3 | Queued queue-entry maps to the reduced test shape with all queued-specific fields | API-contract | Phase 2 | safebreach_mcp_data |
| T-4 | A malformed planRunId prefix omits queued_time without breaking the mapping | — | Phase 2 | safebreach_mcp_data |
| T-5 | testsummaries PENDING normalizes to 'queued' while all other statuses stay verbatim | regression | Phase 2 | safebreach_mcp_data |
| T-6 | get_tests merges queued entries into the response with count metadata and agent hint | — | Phase 3 | safebreach_mcp_data |
| T-7 | A planRunId present in both sources yields exactly one row with status 'queued' | — | Phase 3 | safebreach_mcp_data |
| T-8 | status_filter='queued' selects only queued entries client-side (no server status param) | API-contract | Phase 3 | safebreach_mcp_data |
| T-9 | An invalid status_filter fails fast with the allowed-values list | — | Phase 3 | safebreach_mcp_data |
| T-10 | Terminal status filters never trigger the queue snapshot call | — | Phase 3 | safebreach_mcp_data |
| T-11 | Queue snapshot failure leaves the get_tests response identical to today's | regression | Phase 3 | safebreach_mcp_data |
| T-12 | Queued entries are pinned above all other tests, newest submission first | — | Phase 3 | safebreach_mcp_data |
| T-13 | Pagination counts include queued entries and overflow preserves order | regression | Phase 3 | safebreach_mcp_data |
| T-14 | The queue snapshot is fetched fresh even when testsummaries is served from cache | — | Phase 3 | safebreach_mcp_data |
| T-15 | The get_tests tool contract advertises 'queued' and delegates the filter to the business layer | API-contract | Phase 4 | safebreach_mcp_data |

**System**

| Test | Description | Exec | Aspect | Passes after | Repo | Environment |
|------|-------------|------|--------|--------------|------|-------------|
| T-17 | Existing get_tests behaviors still work through a real MCP client session after the change | Manual | regression | Final | — | console environment (Validate) |

**E2E**

| Test | Description | Exec | Aspect | Passes after | Repo | Environment |
|------|-------------|------|--------|--------------|------|-------------|
| T-16 | A really-queued test on a saturated console appears in get_tests as 'queued' and disappears after cancel | Automatic | regression, API-contract | Phase 5 | safebreach_mcp_data | console environment (Validate) |
| T-18 | The full new queue-then-monitor workflow walked through a real MCP client session | Manual | progression | Final | — | console environment (Validate) |

### T-1 — Queue snapshot parsing

- Description: Proves the new core snapshot reader exposes exactly what the merge needs — ordered
  pending entries (without the heavy originalPlan payload), busy-slot planRunIds, and the pause flag.
- Status: Active
- Passes after: Phase 1
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: Older-console `/queue` shape differences; a mis-parse silently empties the merge.
- Risk source: PRD §10
- Verify: Mock `safebreach_mcp_core.queue_state.requests.get` to return a payload modeled on the
  live pentest01 capture (`data.{isPause, slotState[], queue[], testRunState{}}`, ≥2 pending
  entries with `originalPlan` bodies, mixed idle/busy slots). Call
  `get_orchestrator_queue_snapshot(console)`.
- Expected: Pending list preserves `queue[]` order; each pending item carries planRunId, name,
  priority, ranBy, ranFrom and NO originalPlan/steps bodies/actions/edges/flowControl; busy set
  equals the non-idle slots' planRunIds; is_paused mirrors `isPause`.
- Evidence required: pytest run output (command log) for `safebreach_mcp_core/tests/test_queue_state.py`.
- Automation lives in: planned: safebreach_mcp_core/tests/test_queue_state.py
- Environment needs: none

### T-2 — Queue snapshot graceful degradation

- Description: Proves any snapshot failure (HTTP error, malformed body, RBAC rejection) yields an
  empty snapshot rather than an exception, so `get_tests` can never be broken by the queue API.
- Status: Active
- Passes after: Phase 1
- Level: unit
- Execution: Automatic
- Aspect: regression
- Risk: A queue-API outage or old console taking down the primary test-listing tool.
- Risk source: PRD §10
- Verify: Mock `requests.get` to (a) raise a connection error, (b) return HTTP 404, (c) return a
  body missing `data`/`queue` keys. Call the snapshot function for each case.
- Expected: Every case returns the empty snapshot (no pending, empty busy set, is_paused False) and
  logs a warning; no exception propagates.
- Evidence required: pytest run output (command log).
- Automation lives in: planned: safebreach_mcp_core/tests/test_queue_state.py
- Environment needs: none

### T-3 — Queued-entry reduced mapping

- Description: Proves a pending queue entry becomes a well-formed reduced test row — the shape
  agents receive for a queued test.
- Status: Active
- Passes after: Phase 2
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: A malformed queued row would poison every merged `get_tests` page.
- Risk source: PRD §10
- Verify: Call the new queued-entry transform with a trimmed pending entry
  (planRunId `"1785224437040.28"`, name, priority, ranBy, ranFrom) at 0-based index 1.
- Expected: Row has `test_id="1785224437040.28"`, the name, `status='queued'`,
  `queued_time=1785224437` (epoch seconds from the prefix), `queue_position=2`, priority and
  ran_from; `start_time`/`end_time`/`duration` are absent.
- Evidence required: pytest run output (command log).
- Automation lives in: planned: safebreach_mcp_data/tests/test_data_types.py (TestTestSummaryMapping area)
- Environment needs: none

### T-4 — Defensive planRunId prefix parse

- Description: Proves a non-numeric planRunId prefix degrades to a row without `queued_time`
  instead of raising, keeping the merge alive on unexpected platform versions.
- Status: Active
- Passes after: Phase 2
- Level: unit
- Execution: Automatic
- Risk: planRunId format is an undocumented platform detail; a change must not break `get_tests`.
- Risk source: PRD §10
- Verify: Call the queued-entry transform with planRunId values lacking a numeric epoch prefix
  (e.g. `"abc.5"`, `""`).
- Expected: The row is still produced with `status='queued'` and `queue_position`; `queued_time` is
  omitted; no exception.
- Evidence required: pytest run output (command log).
- Automation lives in: planned: safebreach_mcp_data/tests/test_data_types.py
- Environment needs: none

### T-5 — PENDING normalization, other statuses verbatim

- Description: Proves the two-state model decision — a slotted-but-preparing test (`PENDING`)
  presents as `queued` — while every other status continues to pass through unchanged.
- Status: Active
- Passes after: Phase 2
- Level: unit
- Execution: Automatic
- Aspect: regression
- Risk: Blanket normalization accidentally rewriting RUNNING/terminal statuses.
- Risk source: reviewer input (gate)
- Verify: Call `get_reduced_test_summary_mapping` with raw entities whose `status` is `PENDING`,
  `pending`, `RUNNING`, `COMPLETED`, `CANCELED`, `FAILED`.
- Expected: Both PENDING spellings yield `status='queued'`; all other statuses appear verbatim
  (existing status-verbatim tests stay green).
- Evidence required: pytest run output (command log).
- Automation lives in: planned: safebreach_mcp_data/tests/test_data_types.py
- Environment needs: none

### T-6 — Merge produces queued rows + metadata (bug repro at unit level)

- Description: Proves the reported bug is fixed at the merge layer: queued tests appear in the
  `get_tests` result with the count metadata and agent hint — red before the fix, green after.
- Status: Active
- Passes after: Phase 3
- Level: unit
- Execution: Automatic
- Risk: The headline defect (SAF-33511 RCA): queue-waiting tests invisible to agents.
- Risk source: PRD §10
- Verify: Patch `_get_all_tests_from_cache_or_api` to return terminal/running rows and patch the
  snapshot function to return 2 pending entries; call `sb_get_tests` with no status filter.
- Expected: Page 0 contains both queued rows (`status='queued'`) alongside the others;
  `queued_tests_count=2`; `hint_to_agent` marks queued state as point-in-time and routes to
  `manage_test`/`get_test_details`.
- Evidence required: pytest run output (command log).
- Automation lives in: planned: safebreach_mcp_data/tests/test_data_functions.py
- Environment needs: none

### T-7 — planRunId dedupe across sources

- Description: Proves a test transitioning queue→slot during the 10–15 s consistency window is
  returned exactly once, with the fresh queue status winning.
- Status: Active
- Passes after: Phase 3
- Level: unit
- Execution: Automatic
- Risk: Duplicate rows double-counting tests and corrupting pagination totals.
- Risk source: PRD §10
- Verify: Arrange the same planRunId in both the mocked testsummaries rows (as PENDING/RUNNING) and
  the mocked snapshot pending list; call `sb_get_tests`.
- Expected: Exactly one row for that planRunId with `status='queued'`; totals count it once.
- Evidence required: pytest run output (command log).
- Automation lives in: planned: safebreach_mcp_data/tests/test_data_functions.py
- Environment needs: none

### T-8 — status_filter='queued' selects client-side

- Description: Proves the new filter returns only queued entries (queue rows + normalized-PENDING
  rows) and never sends a server-side status param (confirmed non-functional for QUEUED).
- Status: Active
- Passes after: Phase 3
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: A server-side `&status=QUEUED` param silently returns 0 rows (verified live on pentest01).
- Risk source: risk-analysis (live-console research in context.md)
- Verify: Mock testsummaries HTTP (inspect the requested URL) with a mix of PENDING/RUNNING/
  COMPLETED rows and a snapshot with 1 pending entry; call `sb_get_tests(status_filter='queued')`.
- Expected: Result contains only the queue entry + the normalized-PENDING row; the testsummaries
  request URL contains NO `status=` query param; case-insensitive input (`'Queued'`) accepted.
- Evidence required: pytest run output (command log).
- Automation lives in: planned: safebreach_mcp_data/tests/test_data_functions.py
- Environment needs: none

### T-9 — status_filter validation

- Description: Proves unknown status values fail fast with an actionable message instead of
  silently returning unfiltered data (a today-bug this feature fixes in passing).
- Status: Active
- Passes after: Phase 3
- Level: unit
- Execution: Automatic
- Verify: Call `sb_get_tests(status_filter='bogus')`.
- Expected: ValueError (or tool-level error envelope, matching the repo's validation pattern for
  `order_by`) listing allowed values completed/canceled/failed/running/queued.
- Evidence required: pytest run output (command log).
- Automation lives in: planned: safebreach_mcp_data/tests/test_data_functions.py
- Environment needs: none

### T-10 — Terminal filters skip the snapshot

- Description: Proves calls that cannot match queued tests (completed/canceled/failed) never pay
  the queue-API round-trip.
- Status: Active
- Passes after: Phase 3
- Level: unit
- Execution: Automatic
- Aspect: perf
- Risk: Unnecessary latency added to the most common historical queries.
- Risk source: PRD §6 (performance)
- Verify: Patch the snapshot function with a spy; call `sb_get_tests` with each terminal
  status_filter, then with None/'queued'/'running'.
- Expected: The spy is NOT called for the three terminal filters; it IS called for None, 'queued',
  and 'running'.
- Evidence required: pytest run output (command log).
- Automation lives in: planned: safebreach_mcp_data/tests/test_data_functions.py
- Environment needs: none

### T-11 — Degradation leaves today's response intact

- Description: Proves that when the queue snapshot is empty-on-error, the `get_tests` response is
  byte-for-byte today's behavior — the feature can never regress the existing tool.
- Status: Active
- Passes after: Phase 3
- Level: unit
- Execution: Automatic
- Aspect: regression
- Risk: Queue-API outage breaking the primary listing tool.
- Risk source: PRD §10
- Verify: Patch the snapshot function to return the empty snapshot; call `sb_get_tests` with no
  filter over mocked testsummaries rows; compare against the pre-feature expected envelope.
- Expected: Identical rows/totals to current behavior; no queued fields; `queued_tests_count=0`
  (or absent per implementation contract); no exception.
- Evidence required: pytest run output (command log).
- Automation lives in: planned: safebreach_mcp_data/tests/test_data_functions.py
- Environment needs: none

### T-12 — Queued pinned to top, newest first

- Description: Proves placement — queued entries always precede running/terminal rows and are
  internally ordered by derived submission time descending, regardless of requested ordering.
- Status: Active
- Passes after: Phase 3
- Level: unit
- Execution: Automatic
- Risk: Timestamp-less queued rows sinking to the bottom (the original visibility bug mechanism).
- Risk source: PRD §10
- Verify: Merge 3 pending entries (distinct planRunId epoch prefixes) with terminal rows; call
  `sb_get_tests` under default ordering AND under `order_by=name asc`.
- Expected: In both cases page 0 starts with the 3 queued rows sorted newest-submission-first,
  followed by the remaining rows sorted per the requested ordering.
- Evidence required: pytest run output (command log).
- Automation lives in: planned: safebreach_mcp_data/tests/test_data_functions.py
- Environment needs: none

### T-13 — Pagination includes queued entries

- Description: Proves totals and page boundaries account for merged queued rows without breaking
  existing pagination semantics.
- Status: Active
- Passes after: Phase 3
- Level: unit
- Execution: Automatic
- Aspect: regression
- Risk: Off-by-page errors corrupting agents' iteration over test history.
- Risk source: reviewer input (gate)
- Verify: Merge 12 pending entries (more than PAGE_SIZE=10) with 5 terminal rows; request pages 0
  and 1.
- Expected: `total_tests=17`, `total_pages=2`; page 0 = 10 newest queued rows; page 1 = remaining 2
  queued rows then the 5 terminal rows in requested order.
- Evidence required: pytest run output (command log).
- Automation lives in: planned: safebreach_mcp_data/tests/test_data_functions.py
- Environment needs: none

### T-14 — Snapshot is fresh despite testsummaries cache

- Description: Proves the freshness guarantee behind R3 — a `get_tests` call served from the
  30-minute testsummaries cache still fetches the queue snapshot live.
- Status: Active
- Passes after: Phase 3
- Level: unit
- Execution: Automatic
- Risk: A cached merge would hide newly queued tests for up to 30 minutes — the bug reborn.
- Risk source: PRD §10
- Verify: Call `sb_get_tests` twice (first call populates the tests cache); patch the snapshot
  function with a spy returning different pending sets per call.
- Expected: The snapshot spy is invoked on BOTH calls; the second response reflects the second
  (changed) pending set while testsummaries came from cache.
- Evidence required: pytest run output (command log).
- Automation lives in: planned: safebreach_mcp_data/tests/test_data_functions.py
- Environment needs: none

### T-15 — Tool contract advertises and delegates 'queued'

- Description: Proves the agent-facing contract: the registered `get_tests` tool documents the
  `queued` filter value and forwards it unchanged to the business layer.
- Status: Active
- Passes after: Phase 4
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: Agents can only discover the feature through the tool description — an undocumented value
  is an invisible feature.
- Risk source: reviewer input (gate)
- Verify: Assert `get_tests` remains registered with `readOnlyHint=True`; read the registered
  tool's description text; patch `sb_get_tests` and invoke the tool wrapper with
  `status_filter='queued'`.
- Expected: Description contains `'queued'` in the status_filter enumeration; the wrapper delegates
  `status_filter='queued'` to `sb_get_tests` unchanged.
- Evidence required: pytest run output (command log).
- Automation lives in: planned: safebreach_mcp_data/tests/test_data_server.py
- Environment needs: none

### T-16 — Live queued-flow e2e (bug repro-regression on the real console)

- Description: Proves SAF-33511 end-to-end on a real console: a genuinely queued test (slots
  saturated) is visible in `get_tests` as `queued` — cross-checking the same planRunId through the
  orchestrator layer and the MCP layer — and leaves the listing after cancel. Red before the fix,
  green after.
- Status: Active
- Passes after: Phase 5
- Level: e2e
- Execution: Automatic
- Aspect: regression, API-contract
- Risk: Shared-console flakiness (other users' runs); slot-count assumption; live API drift vs the
  mocked shapes.
- Risk source: PRD §10
- Verify: On pentest01: read the live snapshot to count free validate slots; submit free+1 tiny
  quick-run tests (attack 11653, `evaluate=False`), registering each planRunId via
  `register_e2e_test`; poll `sb_get_tests()` (no filter) briefly; then call
  `sb_get_tests(status_filter='queued')`; finally cancel all submitted tests (finally block) and
  re-poll. Skip (pytest.skip) if the console queue is paused or saturation isn't reached within a
  bounded submission count.
- Expected: While saturated, page 0 leads with a row whose `test_id` equals the overflow
  submission's planRunId (the same ID the orchestrator queue reports), `status='queued'`,
  `queue_position ≥ 1`; the 'queued' filter returns it; after cancellation the queued row is gone
  and every submitted test reaches a terminal state (console restored).
- Evidence required: pytest run output (command log) for
  `uv run pytest safebreach_mcp_data/tests/test_e2e.py -m e2e -k queued` including the asserted
  planRunIds.
- Automation lives in: planned: safebreach_mcp_data/tests/test_e2e.py
- Environment needs: console environment (Validate) — existing pentest01; `pentest01_apitoken` +
  `E2E_CONSOLE=pentest01` in env; ≥1 connected simulator.

### T-17 — Manual regression: existing get_tests behaviors through a real MCP client

- Description: Proves the change broke nothing for today's users — the existing `get_tests`
  behaviors (terminal filters, pagination, running listing) still work when exercised through a
  real served MCP session like a genuine agent consumer.
- Status: Active
- Passes after: Final
- Level: system
- Execution: Manual
- Aspect: regression
- Risk: In-process unit tests bypass the served MCP layer (transport, auth context, wrapper
  normalization); a wiring regression would be invisible to them.
- Risk source: reviewer input (gate)
- Verify: Start the data server locally (`uv run -m safebreach_mcp_data.data_server` with pentest01
  env); connect as a real MCP client; call `get_tests` with no filter,
  `status_filter='completed'`, `status_filter='running'`, and `page_number=1`; compare against the
  console UI's test-history page for the same account.
- Expected: Responses match pre-change semantics (completed rows with timestamps and statistics,
  correct page sizes/totals) and agree with the console UI's history; no errors or shape breakage
  in any call.
- Evidence required: AI-executed session transcript (commands + tool responses) + observed-vs-
  expected notes; BLOCKED reported if the session cannot complete — never an improvised pass.
- Manual because: exercises the served MCP protocol end-to-end (transport + auth + tool wrapper);
  the repo has no automated MCP-client harness — its automated tests call functions in-process
  (genuinely unavailable infra).
- Environment needs: console environment (Validate) — existing pentest01.

### T-18 — Manual progression: queue-then-monitor walkthrough

- Description: Sign-off evidence that the new capability delivers the reporter's workflow: an agent
  queues work, immediately sees it as queued with its position, and tracks it to termination —
  entirely through real MCP tool calls.
- Status: Active
- Passes after: Final
- Level: e2e
- Execution: Manual
- Aspect: progression
- Risk: The end-to-end agent experience (hint quality, field usefulness, placement) can look right
  in units yet feel broken in a real session.
- Risk source: reviewer input (gate)
- Verify: Through a real MCP client session against pentest01: saturate validate slots via repeated
  `quick_run` (attack 11653, evaluate=False) exactly as T-16 does; call `get_tests` and
  `get_tests(status_filter='queued')`; read `queue_position`/`queued_time`/`hint_to_agent`; cancel
  everything via `manage_test`; call `get_tests` again to confirm the queue drained. Judge whether
  the queued rows and hint give an agent enough to act (cancel/wait/monitor) without extra tools.
- Expected: The just-queued planRunId is visible at the top with `status='queued'` and a sensible
  `queue_position`; the hint correctly routes follow-up actions; after cancel the entries show
  terminal statuses; the console is left with no leftover probe tests.
- Evidence required: AI-executed session transcript + tool call/response log + a judgment note on
  agent-usability; BLOCKED reported if the flow cannot complete.
- Manual because: the core assertion includes non-deterministic judgment (is the queued
  presentation actionable for an agent?) on top of the served-MCP flow, and no automated
  MCP-client harness exists in-repo.
- Environment needs: console environment (Validate) — existing pentest01; permission to submit and
  cancel tests.

## Tests by Phase (readiness view — generated)

Cumulative: at the end of phase N, EVERY test with "Passes after" <= N must be green.

| After phase | Newly green | Cumulative green |
|-------------|-------------|------------------|
| Phase 1 | T-1, T-2 | T-1, T-2 |
| Phase 2 | T-3, T-4, T-5 | T-1..T-5 |
| Phase 3 | T-6, T-7, T-8, T-9, T-10, T-11, T-12, T-13, T-14 | T-1..T-14 |
| Phase 4 | T-15 | T-1..T-15 |
| Phase 5 | T-16 | T-1..T-16 |
| Final / E2E | T-17, T-18 | all |

## Sign-off

- [ ] Requirements traceability complete — every R# covered or explicitly out-of-scope
- [ ] Change Coverage complete — every changed file tested or justified
- [ ] Regression complete — >=1 Manual regression test (or justification) + post-ship CI builds named
- [ ] Progression evidence — >=1 Manual progression test walking the new feature (or justification)
- [ ] validating-test-plan: RESULT: clean
- [ ] All tests green (cumulative through Final) — evidence: test-results/<phase-or-date>.md
- [ ] Accepted gaps listed and approved: no hosted pytest CI / no Automation-Pen-Testing suite for
  this surface — local `uv run pytest -m "not e2e"` gate is the regression mechanism of record
  (user-approved 2026-07-28, see Regression section)
- [ ] Dev + QA review recorded in Status & Review

## Change Log

| Date | Change |
|------|--------|
| 2026-07-28 11:08 | Test plan created from PRD v1 |
| 2026-07-28 11:15 | Validator run: 1 finding — no hosted CI regression gate; recorded as user-accepted gap |
