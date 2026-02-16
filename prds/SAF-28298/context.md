# SAF-28298: Context File

## Ticket Info

- **Key:** SAF-28298
- **Title:** [safebreach-mcp] Performance and resiliency improvements for better Agent results
- **Status:** To Do
- **Priority:** High
- **Sprint:** Saf sprint 83
- **Assignee:** Yossi Attas
- **Estimate:** 4h

## Scope

Three improvements for better in-console Agent results:

1. **Drift count performance** — `get_test_details(include_statistics=True)` fetches ALL simulations to count
   drifted ones. Slow + high memory for large tests. Need page-by-page counting.
2. **Propagate findings in test summary** — Agents always call `get_test_findings_counts` after `get_test_details`
   for Propagate tests. Counts already in API response — include them directly.
3. **Concurrency limiter** — Per-agent semaphore for parallel tool invocations. Tools buffer 100% of data before
   filtering. Default limit 2, configurable via env var. HTTP retry error when exceeded.

## Investigation Findings

### Item 1: Drift Count Performance

**Root cause:** `_get_simulation_statistics()` (data_functions.py:434-517) calls
`_get_all_simulations_from_cache_or_api()` (line 448) which fetches ALL simulations via paginated POST requests
(100/page) into a single list, just to count `is_drifted=True` entries. Only a single integer (drift count) is used
from the entire dataset.

**Key code path:**
- `sb_get_test_details(include_simulations_statistics=True)` → `_get_simulation_statistics()` →
  `_get_all_simulations_from_cache_or_api()` → N API calls (100/page) → buffer all → iterate → count drifts
- The `finalStatus` dict (missed/stopped/prevented/reported/logged/no-result counts) already comes from the test
  summary API — only drift count requires the simulation fetch
- `is_drifted` is computed from the presence of `driftType` field in each simulation's API response (data_types.py:94)
- Cache (1hr TTL) mitigates repeated calls, but first call on large tests is expensive + high memory

**Impact:** A test with 10,000 simulations → 100 API calls → ~10MB+ buffered → iterate → return one integer.

### Item 2: Propagate Findings in Test Summary

**Root cause:** The test summary API response (`/testsummaries/{test_id}`) returns fields that are currently
dropped by `reduced_test_summary_mapping` (data_types.py:12-19). The mapping only extracts: planName, planRunId,
startTime, endTime, duration, status, systemTags.

**Key findings:**
- `sb_get_test_findings_counts()` calls a separate endpoint: `/propagateSummary/{test_id}/findings/`
  (data_functions.py:1223)
- The ticket states that findings counts and compromised host counts are already in the test summary API response
- Currently `get_reduced_test_summary_mapping()` (data_types.py:77-85) ignores these fields
- Propagate vs Validate distinction: `systemTags` contains "ALM" for Propagate tests (data_types.py:83-84)

**Optimization:** For Propagate tests, extract findings/compromised host counts from the test summary API response
and include them in the returned entity, saving the agent a separate API call.

### Item 3: Concurrency Limiter

**Data buffering confirmed:**
- `_get_all_simulations_from_cache_or_api()` (data_functions.py:615-707): buffers all simulations before
  filtering/pagination
- `_get_all_attacks_from_cache_or_api()` (playbook_functions.py:33-99): buffers entire attack knowledge base

**Architecture for middleware injection:**
- ASGI middleware exists in `safebreach_base.py:152-437` (`_create_authenticated_asgi_app`)
- Injection point: line 138 `app = self._create_authenticated_asgi_app(app)`
- Client IP available from ASGI scope (line 166-168)
- No per-agent identification currently exists — no `contextvars`, no session/client ID tracking
- OAuth discovery endpoints exist but use hardcoded `client_id: "mcp-remote-client"` (not unique per agent)
- Environment variable pattern established: `SAFEBREACH_MCP_*`

**Per-agent identification options:**
1. Client IP (available, but NAT/proxy may share IPs)
2. Authorization Bearer token (single shared token, can't distinguish agents)
3. Custom header (e.g., `X-Agent-ID`) — requires client cooperation
4. SSE connection ID / transport-level session — needs investigation of FastMCP internals

## Brainstorming Results

### Item 1: Drift Count — Approach C (Hybrid)

**Always inline `finalStatus` counts** (missed/stopped/prevented/reported/logged/no-result) in test details — these come
free from the test summary API, no simulation fetch needed.

**Rename parameter** from `include_simulations_statistics` to `include_drift_count` (default `False`). When `True`, use
**streaming page-by-page counting** — iterate simulation pages, count `is_drifted=True` entries, discard each page before
fetching next. Never buffer all simulations in memory.

**Benefits:** Eliminates the common case penalty (agents always want status counts but rarely need drift), reduces memory
from O(all_simulations) to O(page_size), and the parameter name clearly communicates cost.

### Item 2: Propagate Findings — Extract from Existing API Response

For Propagate (ALM) tests, extract `findingsCount` and `compromisedHosts` from the test summary API response
(`/testsummaries/{test_id}`) and include them in `get_test_details` output. Detect Propagate tests via `systemTags`
containing "ALM". Saves agents a separate `get_test_findings_counts` call.

### Item 3: Concurrency Limiter — Approach A (SSE Connection-Scoped Semaphore)

Use `contextvars` to track per-SSE-connection identity. Each SSE connection gets a unique session ID set in a
`ContextVar` when the connection is established. ASGI middleware checks the `ContextVar`, applies an
`asyncio.Semaphore(limit)` per session. Default limit: 2, configurable via `SAFEBREACH_MCP_CONCURRENCY_LIMIT` env var.
When exceeded, return HTTP 429 (Too Many Requests) with retry hint.

**Benefits:** No client cooperation needed, natural per-agent scoping (each agent = one SSE connection), automatic
cleanup when connection drops.

## Status

Phase 6: PRD Created
