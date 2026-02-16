# Performance and Resiliency Improvements — SAF-28298

## 1. Overview

- **Task Type**: Performance optimization + feature enhancement
- **Purpose**: Improve Agent experience in SafeBreach console by reducing latency, memory usage, and preventing
  resource contention across concurrent tool invocations
- **Target Consumer**: AI Agents (Claude, other LLM agents) operating via MCP protocol against SafeBreach consoles
- **Key Benefits**:
  1. Eliminate unnecessary API calls — `finalStatus` counts always inline, Propagate findings included automatically
  2. Reduce memory from O(all_simulations) to O(page_size) for drift counting
  3. Prevent resource exhaustion from concurrent agent tool invocations via per-session concurrency limiting
- **Originating Request**: SAF-28298 — Sprint 83, Priority High, Estimate 4h

## 1.5. Document Status

| Field | Value |
|-------|-------|
| **PRD Status** | Draft |
| **Last Updated** | 2026-02-15 |
| **Owner** | Yossi Attas |
| **Current Phase** | N/A |

## 2. Solution Description

### Chosen Solution

Three targeted changes to the Data Server and shared core:

1. **Hybrid drift count** — Always inline `finalStatus` counts (free from API). Rename parameter to
   `include_drift_count`. When True, stream page-by-page to count drifts without buffering all simulations.
2. **Propagate findings extraction** — For ALM tests, extract `findingsCount` and `compromisedHosts` from the
   existing test summary API response and include them in `get_test_details` output.
3. **SSE connection-scoped concurrency limiter** — Per-SSE-connection semaphore via `contextvars` in ASGI middleware.
   Default limit 2, configurable via `SAFEBREACH_MCP_CONCURRENCY_LIMIT`. HTTP 429 when exceeded.

### Alternatives Considered

**Item 1 (Drift Count):**
- *Drop drift from statistics entirely* — Simplest but loses functionality agents occasionally need
- *Stream-only (always count drifts)* — Still makes N API calls even when drift not requested

**Item 3 (Concurrency):**
- *Client IP-based limiting* — NAT/proxy may share IPs, causing false throttling across agents
- *Custom header (X-Agent-ID)* — Requires client cooperation, not transparent

### Decision Rationale

- Hybrid approach for drift count eliminates the common-case penalty (agents rarely need drift count but always want
  status counts) while still providing drift when explicitly requested
- SSE connection scoping is the most reliable per-agent identity without requiring client changes — each agent
  maintains exactly one SSE connection, providing natural session isolation

## 3. Core Feature Components

### Component A: Inline `finalStatus` Counts + Streaming Drift Count

- **Purpose**: Modify existing `get_test_details` tool to always return simulation status breakdown (free from API)
  and optionally count drifts via streaming pagination
- **Key Features**:
  - Always include `finalStatus` counts (missed/stopped/prevented/reported/logged/no-result) in test details — no
    parameter needed, zero extra API cost
  - Rename `include_simulations_statistics` parameter to `include_drift_count` (default `False`)
  - When `include_drift_count=True`, iterate simulation pages (100/page), count `is_drifted=True` entries per page,
    discard page before fetching next — memory stays at O(page_size)
  - Backward-compatible: old parameter name still works (mapped internally), new parameter name is clearer about cost

### Component B: Propagate Findings in Test Summary

- **Purpose**: Modify existing `get_test_details` to include findings counts for Propagate (ALM) tests, eliminating
  a separate `get_test_findings_counts` call
- **Key Features**:
  - Detect Propagate tests via `systemTags` containing "ALM" (existing logic in `data_types.py:83-84`)
  - Extract `findingsCount` and `compromisedHosts` from the test summary API response (`/testsummaries/{test_id}`)
  - Include these fields in the returned entity only when test is Propagate type
  - No new API calls — data already present in the response, currently dropped by the mapping

### Component C: Per-Agent Concurrency Limiter

- **Purpose**: New ASGI middleware in shared core that limits concurrent tool invocations per SSE connection
- **Key Features**:
  - Assign unique session ID to each SSE connection via `contextvars.ContextVar`
  - ASGI middleware intercepts tool requests, looks up per-session `asyncio.Semaphore(limit)`
  - Default limit: 2 concurrent tool invocations per agent session
  - Configurable via `SAFEBREACH_MCP_CONCURRENCY_LIMIT` environment variable
  - When semaphore full: return HTTP 429 (Too Many Requests) with `Retry-After` header
  - Automatic cleanup: semaphore removed when SSE connection drops
  - Applied to all servers via `SafeBreachMCPBase` (shared core)

## 4. API Endpoints and Integration

**Existing APIs consumed (no changes):**

- `GET /api/data/v1/accounts/{account_id}/testsummaries/{test_id}` — Test summary (already returns `finalStatus`,
  `findingsCount`, `compromisedHosts`)
- `POST /api/data/v1/accounts/{account_id}/executionsHistoryResults` — Simulation results (paginated, 100/page)

**MCP tool interface changes:**

- `get_test_details`: Parameter rename `include_simulations_statistics` → `include_drift_count`. Response always
  includes `simulations_statistics` (status counts). When `include_drift_count=True`, also includes `drifted_count`.
  For Propagate tests, includes `findings_count` and `compromised_hosts`.

## 6. Non-Functional Requirements

### Performance Requirements

- **Drift count**: Memory usage O(page_size) regardless of total simulations. For a test with 10,000 simulations,
  still makes ~100 API calls when drift requested, but never buffers more than 100 simulations at a time.
- **Propagate findings**: Zero additional API calls — extracted from existing response.
- **Concurrency limiter**: Negligible overhead per request (semaphore acquire/release).

### Technical Constraints

- **Backward Compatibility**: Old parameter name `include_simulations_statistics` must continue to work (mapped to
  `include_drift_count` internally). Response structure changes — `simulations_statistics` now always present.
- **Environment Variable**: `SAFEBREACH_MCP_CONCURRENCY_LIMIT` follows established `SAFEBREACH_MCP_*` pattern.
- **Framework**: Concurrency limiter uses `contextvars` (Python stdlib) + `asyncio.Semaphore`. No new dependencies.

## 7. Definition of Done

- [ ] `get_test_details` always returns `finalStatus` counts without requiring `include_simulations_statistics=True`
- [ ] `include_drift_count` parameter controls only drift counting (streaming, page-by-page)
- [ ] Old parameter name `include_simulations_statistics` still works (backward compat)
- [ ] Propagate (ALM) tests include `findings_count` and `compromised_hosts` in test details
- [ ] Validate (BAS) tests do not include findings fields
- [ ] Concurrency limiter middleware applies to all servers via `SafeBreachMCPBase`
- [ ] Default limit of 2 concurrent tool invocations per SSE session
- [ ] `SAFEBREACH_MCP_CONCURRENCY_LIMIT` env var overrides default
- [ ] HTTP 429 returned when limit exceeded, with `Retry-After` header
- [ ] Semaphore cleanup when SSE connection drops
- [ ] All existing unit tests pass (updated for new structure)
- [ ] New unit tests for all three components
- [ ] E2E tests pass with updated assertions

## 8. Testing Strategy

### Unit Testing

- **Item 1**: Test that `finalStatus` counts always appear in test details. Test streaming drift count returns
  correct integer without buffering (mock paginated API responses). Test backward compat with old parameter name.
- **Item 2**: Test that Propagate tests include `findings_count` and `compromised_hosts`. Test that Validate tests
  do not include these fields. Test with missing/null values in API response.
- **Item 3**: Test semaphore acquisition and release. Test HTTP 429 when limit exceeded. Test cleanup on disconnect.
  Test env var override.

### E2E Testing

- Update existing `test_get_test_details_e2e` to verify `simulations_statistics` always present.
- Add E2E test for Propagate test with findings fields.
- Concurrency limiter E2E: positive test (single request, no throttle) and negative test (concurrent requests
  exceeding limit, verify HTTP 429).

## 9. Implementation Phases

| Phase | Status | Completed | Commit SHA | Notes |
|-------|--------|-----------|------------|-------|
| Phase 1: Inline finalStatus counts | ⏳ Pending | - | - | |
| Phase 2: Streaming drift count | ⏳ Pending | - | - | |
| Phase 3: Propagate findings | ⏳ Pending | - | - | |
| Phase 4: Concurrency limiter | ⏳ Pending | - | - | |
| Phase 5: E2E verification | ⏳ Pending | - | - | |

### Phase 1: Inline `finalStatus` Counts

**Semantic Change**: Always include simulation status breakdown in `get_test_details` output.

**Deliverables**: `finalStatus` counts (missed/stopped/prevented/reported/logged/no-result) returned for every
`get_test_details` call regardless of parameters.

**Implementation Details**:

1. **`data_types.py`** — In `get_reduced_test_summary_mapping()`, extract `finalStatus` dict from the test summary
   entity. Build a `simulations_statistics` list with the 6 status entries (same structure as current
   `_get_simulation_statistics` but without the drift entry). Add this list to the returned entity.

2. **`data_functions.py`** — In `sb_get_test_details()`, remove the conditional `if include_simulations_statistics`
   block that calls `_get_simulation_statistics()`. The status counts now come from the mapping layer. Keep
   `_get_simulation_statistics()` but refactor it to only handle drift counting (Phase 2).

3. **`data_server.py`** — Update tool description to reflect that status counts are always included. Keep
   `include_simulations_statistics` parameter for backward compatibility but document it as deprecated in favor of
   `include_drift_count`. The tool description must explicitly warn that `include_drift_count=True` may take a
   significant amount of time to complete for large tests (proportional to simulation count), so the agent can
   make an informed decision about whether to request it.

**Changes:**

| File | Change |
|------|--------|
| `safebreach_mcp_data/data_types.py` | Extract `finalStatus` in `get_reduced_test_summary_mapping()` |
| `safebreach_mcp_data/data_functions.py` | Remove conditional statistics block, always return status counts |
| `safebreach_mcp_data/data_server.py` | Update tool description, add `include_drift_count` parameter |

**Test Plan**:
- Test `get_reduced_test_summary_mapping` returns `simulations_statistics` with all 6 status entries
- Test `sb_get_test_details` always returns stats without `include_simulations_statistics=True`
- Test stats counts match `finalStatus` values from API
- Test with missing `finalStatus` (defaults to 0 counts)

**Git Commit**: `perf: always inline finalStatus counts in get_test_details (SAF-28298)`

### Phase 2: Streaming Drift Count

**Semantic Change**: Replace bulk simulation fetch with streaming page-by-page drift counter.

**Deliverables**: `include_drift_count` parameter triggers streaming count. Memory stays at O(page_size).

**Implementation Details**:

1. **`data_functions.py`** — Create new function `_count_drifted_simulations_streaming(test_id, console)` that:
   - Uses the same paginated POST API as `_get_all_simulations_from_cache_or_api()` (endpoint:
     `/executionsHistoryResults`, page_size=100)
   - For each page: count entries where `driftType` field is present (truthy), then discard the page
   - Return the total drift count as an integer
   - Does NOT use or populate the simulations cache (no point caching for a count)

2. **`data_functions.py`** — In `sb_get_test_details()`, add `include_drift_count` parameter (default `False`).
   Map old `include_simulations_statistics` to this new parameter for backward compat. When True, call
   `_count_drifted_simulations_streaming()` and append the drift entry to `simulations_statistics`.

3. **`data_server.py`** — Add `include_drift_count` parameter to tool definition. Keep
   `include_simulations_statistics` as deprecated alias.

**Changes:**

| File | Change |
|------|--------|
| `safebreach_mcp_data/data_functions.py` | Add `_count_drifted_simulations_streaming()`, update `sb_get_test_details` |
| `safebreach_mcp_data/data_server.py` | Add `include_drift_count` parameter |

**Test Plan**:
- Mock paginated API responses (3 pages with known drift counts), verify streaming function returns correct total
- Test that pages are not accumulated (verify no large list buildup)
- Test backward compat: `include_simulations_statistics=True` triggers drift count
- Test `include_drift_count=False` does not make any simulation API calls
- Test with zero drifts, all drifts, mixed pages

**Git Commit**: `perf: streaming page-by-page drift count for get_test_details (SAF-28298)`

### Phase 3: Propagate Findings in Test Summary

**Semantic Change**: Include findings counts for Propagate tests in `get_test_details` output.

**Deliverables**: Propagate (ALM) tests return `findings_count` and `compromised_hosts` from the test summary API.

**Implementation Details**:

1. **`data_types.py`** — In `get_reduced_test_summary_mapping()`, after detecting test type via `systemTags`:
   - If test is Propagate (ALM): extract `findingsCount` and `compromisedHosts` from the test summary entity
   - Map to `findings_count` and `compromised_hosts` in the returned entity
   - If fields are missing/null in API response, omit them from output (don't include None values)

**Changes:**

| File | Change |
|------|--------|
| `safebreach_mcp_data/data_types.py` | Add findings extraction for ALM tests in `get_reduced_test_summary_mapping()` |

**Test Plan**:
- Test Propagate test includes `findings_count` and `compromised_hosts`
- Test Validate test does not include these fields
- Test with `findingsCount=0` and `compromisedHosts=0` (should still include)
- Test with missing `findingsCount`/`compromisedHosts` keys (should omit gracefully)
- Update existing E2E test assertions if Propagate tests are covered

**Git Commit**: `feat: include propagate findings in get_test_details for ALM tests (SAF-28298)`

### Phase 4: Per-Agent Concurrency Limiter

**Semantic Change**: Add ASGI middleware that limits concurrent tool invocations per SSE connection.

**Deliverables**: Per-session semaphore via `contextvars`, HTTP 429 when exceeded, configurable limit.

**Implementation Details**:

1. **`safebreach_base.py`** — Add concurrency limiter to the ASGI middleware pipeline:
   - Define module-level `ContextVar('mcp_session_id', default=None)` for session tracking
   - Define module-level dict `_session_semaphores: Dict[str, asyncio.Semaphore]` for per-session semaphores
   - Read `SAFEBREACH_MCP_CONCURRENCY_LIMIT` env var (default: 2) at startup
   - In the ASGI app, when an SSE connection is established (path matching SSE endpoint), generate a UUID session
     ID and set it in the `ContextVar`
   - For tool invocation requests (POST to message endpoint): read session ID from `ContextVar`, look up or create
     semaphore for that session, attempt non-blocking acquire
   - If semaphore acquired: proceed with request, release on completion
   - If semaphore full: return HTTP 429 with `Retry-After: 5` header and JSON body explaining the limit
   - On SSE connection close: clean up the semaphore entry from the dict

2. **Integration**: The middleware is added in `_create_authenticated_asgi_app()` (or as a separate wrapper applied
   alongside it), so it applies to all servers inheriting from `SafeBreachMCPBase`.

**Changes:**

| File | Change |
|------|--------|
| `safebreach_mcp_core/safebreach_base.py` | Add concurrency limiter middleware with ContextVar + Semaphore |

**Test Plan**:
- Test semaphore creation per unique session ID
- Test request proceeds when under limit
- Test HTTP 429 returned when limit exceeded (mock 3 concurrent requests with limit=2)
- Test `SAFEBREACH_MCP_CONCURRENCY_LIMIT` env var override
- Test semaphore cleanup on session removal
- Test that different sessions have independent limits

**Git Commit**: `feat: add per-agent concurrency limiter via SSE session semaphore (SAF-28298)`

### Phase 5: E2E Verification

**Semantic Change**: Verify all changes work against real SafeBreach consoles.

**Deliverables**: Updated E2E tests pass, cross-server regression clean.

**Implementation Details**:

1. Update `test_get_test_details_e2e` to verify `simulations_statistics` is always present in response
2. If a Propagate test exists in the E2E console, verify `findings_count` and `compromised_hosts` fields
3. Add concurrency limiter E2E tests:
   - **Positive test**: Single tool invocation completes without throttling (HTTP 200)
   - **Negative test**: Fire concurrent requests exceeding the limit against a running server, verify HTTP 429
     response with `Retry-After` header
4. Run full cross-server unit test suite to catch regressions
5. Update CLAUDE.md tool documentation if needed

**Changes:**

| File | Change |
|------|--------|
| `safebreach_mcp_data/tests/test_e2e.py` | Update test details E2E assertions |
| `CLAUDE.md` | Update tool documentation if needed |

**Test Plan**:
- Run: `uv run pytest safebreach_mcp_data/tests/ -v -m "not e2e"` (Data server unit tests)
- Run: `uv run pytest safebreach_mcp_config/tests/ safebreach_mcp_data/tests/ safebreach_mcp_utilities/tests/
  safebreach_mcp_playbook/tests/ safebreach_mcp_studio/tests/ -v -m "not e2e"` (cross-server regression)
- Run: `source .vscode/set_env.sh && uv run pytest safebreach_mcp_data/tests/test_e2e.py -v -m "e2e"` (E2E)

**Git Commit**: `test: update E2E tests and docs for performance improvements (SAF-28298)`

## 10. Risks and Assumptions

### Technical Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| `findingsCount`/`compromisedHosts` field names differ across API versions | Medium | Verify field names in E2E against real console. Graceful omission if missing. |
| SSE connection identity not propagated to tool handlers via `contextvars` | High | Investigate FastMCP SSE internals early in Phase 4. Fallback to client IP if needed. |
| Streaming drift count still slow for very large tests (100 API calls) | Low | Acceptable — explicit opt-in via `include_drift_count`, parameter name communicates cost. |

### Assumptions

- `findingsCount` and `compromisedHosts` are present in the `/testsummaries/{test_id}` API response for ALM tests
- `contextvars` propagate correctly within FastMCP's SSE connection handling (async context)
- Agents retry on HTTP 429 (standard behavior for LLM tool-calling frameworks)

## 12. Executive Summary

- **Issue**: Three performance bottlenecks in safebreach-mcp degrade Agent experience — unnecessary simulation
  fetches, redundant API calls for Propagate findings, and no protection against concurrent resource-heavy operations
- **What Will Be Built**: Inline status counts, streaming drift counter, Propagate findings extraction, and
  per-session concurrency limiter
- **Key Technical Decisions**: Hybrid approach for drift (always inline free data, opt-in for expensive drift count),
  SSE connection-scoped semaphore (no client cooperation needed), extract existing API fields rather than adding
  new endpoints
- **Business Value**: Faster Agent responses, reduced server memory usage, improved stability under concurrent load
