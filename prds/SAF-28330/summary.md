# Ticket Summary: SAF-28330

## Overview
**Mode**: Improving existing
**Project**: SAF
**Repositories**: safebreach-mcp

---

## Current State
**Summary**: Add Simulation Status Drift API to MCP
**Issues Identified**: The ticket describes a single tool but the underlying API has mutually
exclusive filter modes (result vs. final status) that map naturally to two distinct tools.
The relationship with existing drift tools needs explicit documentation.

---

## Investigation Summary

### safebreach-mcp
- **Existing drift tools (4)**: get_test_drifts (test-run comparison), drifted_only filter
  (in-test filtering), include_drift_info (simulation drill-down), include_drift_count (quick count)
- **New API endpoint**: `POST /api/data/v1/accounts/{accountId}/drift/simulationStatus`
- **API returns flat array** with no pagination — 10K+ items for 3-day window on pentest01
- **Mutual exclusion enforced server-side**: Cannot mix fromStatus/toStatus with
  fromFinalStatus/toFinalStatus (returns 400)
- **Response structure confirmed**: Each record has trackingId, attackId, attackTypes[],
  from/to objects (simulationId, executionTime, finalStatus, status, loggedBy[], reportedBy[],
  alertedBy[], preventedBy[]), driftType
- **Key files**: data_types.py, data_functions.py, data_server.py, drifts_metadata.py
- **500K simulation limit**: API returns error if time window covers too many simulations

---

## Recommended Approach

Expose the new API as **two specialized MCP tools**, split by analytical lens, matching the
API's mutually exclusive filter design. This provides clear LLM tool selection and avoids
parameter confusion.

All 4 existing drift tools are kept — each has unique value (test-run comparison, in-test
filtering, simulation drill-down, quick counts) that the new API does not replicate. The
new tools add a **time-window-centric** drift analysis paradigm complementing the existing
**test-run-centric** paradigm.

### Key Decisions
- **Two tools, not one**: The API's mutually exclusive filter pairs (fromStatus/toStatus vs
  fromFinalStatus/toFinalStatus) naturally split into two distinct analytical perspectives
- **Client-side pagination**: API returns full array; MCP tool paginates locally (PAGE_SIZE=10)
- **Keep all existing tools**: Each has unique capabilities not covered by the new API
- **Epoch input, ISO-8601 internal**: Tool accepts epoch timestamps (consistent with existing
  tools), converts to ISO-8601 for the API
- **Caching**: New cache category for drift results (maxsize=3, TTL=600s)

### Alternatives Considered
| Option | Description | Why Not Chosen |
|--------|-------------|----------------|
| Single unified tool | One tool with all filters | Mutually exclusive params confuse LLMs |
| Single tool + mode param | analysis_mode="result"\|"status" | Conditional params add complexity |
| Deprecate get_test_drifts | Replace with new API | Loses exclusive-sim detection + auto-baseline |

---

## Proposed Ticket Content

### Summary (Title)
Add Simulation Result and Status Drift Tools to MCP

### Description

### Background
The SafeBreach MCP server needs to expose the Simulation Status and Result Drift API as MCP
tools, enabling time-window-based drift analysis. The existing 4 drift tools provide
test-run-centric analysis; the new tools add complementary time-window-centric analysis.

### Technical Context
* New API endpoint: `POST /api/data/v1/accounts/{accountId}/drift/simulationStatus`
* API supports two mutually exclusive filter modes:
  * Result mode: fromStatus/toStatus (FAIL/SUCCESS) — blocked vs not-blocked
  * Final Status mode: fromFinalStatus/toFinalStatus (prevented/stopped/detected/logged/missed/inconsistent)
* API returns unbounded flat arrays (no server-side pagination) — client-side pagination required
* API enforces 500K simulation limit per time window
* Shared filters: windowStart, windowEnd, driftType (Improvement/Regression/NotApplicable),
  attackId, attackType, earliestSearchTime, maxOutsideWindowExecutions

### Proposed Approach
1. Add `get_simulation_result_drifts` tool — security posture lens (blocked/not-blocked)
2. Add `get_simulation_status_drifts` tool — security control lens (prevented/detected/missed/etc.)
3. Both tools share: time window params, driftType, attack filters, client-side pagination
4. Follow existing architecture: data_types.py (transform) -> data_functions.py (logic) ->
   data_server.py (MCP tool)
5. Add caching via SafeBreachCache (drift_cache, maxsize=3, TTL=600s)
6. Update existing tool docstrings with cross-references to new tools
7. Add comprehensive unit tests

### Affected Areas
* safebreach-mcp: data_types.py, data_functions.py, data_server.py, tests/

### Acceptance Criteria

* [ ] `get_simulation_result_drifts` tool exposed with filters: console, window_start,
  window_end, drift_type, attack_id, attack_type, from_status, to_status, page_number
* [ ] `get_simulation_status_drifts` tool exposed with filters: console, window_start,
  window_end, drift_type, attack_id, attack_type, from_final_status, to_final_status,
  page_number
* [ ] Client-side pagination (PAGE_SIZE=10) with total_drifts, total_pages, applied_filters
* [ ] Epoch-to-ISO-8601 time conversion for API calls
* [ ] Caching for API responses (SafeBreachCache, maxsize=3, TTL=600s)
* [ ] Input validation: mutual exclusion guard (reject if user somehow passes both filter types)
* [ ] Error handling: 400 (too many simulations), 401 (auth), timeout
* [ ] Docstrings with "USE THIS WHEN" / "DON'T USE FOR" guidance for LLM tool selection
* [ ] Existing drift tool docstrings updated with cross-references to new tools
* [ ] hint_to_agent in responses guiding to drill-down tools (get_simulation_details, etc.)
* [ ] Unit tests covering: all filter combinations, pagination, error handling,
  mutual exclusion guard, cache behavior
* [ ] E2E tests for basic smoke testing against live environment

### Suggested Labels/Components
- Component: data-server
- Labels: drift, mcp-tools

---

## JIRA-Ready Content

**Description (Markdown for JIRA):**
```markdown
### Background
The SafeBreach MCP server needs to expose the Simulation Status and Result Drift API as MCP
tools, enabling time-window-based drift analysis. The existing 4 drift tools provide
test-run-centric analysis; the new tools add complementary time-window-centric analysis.

### Technical Context
* New API endpoint: `POST /api/data/v1/accounts/{accountId}/drift/simulationStatus`
* API supports two mutually exclusive filter modes:
  * Result mode: fromStatus/toStatus (FAIL/SUCCESS) — blocked vs not-blocked
  * Final Status mode: fromFinalStatus/toFinalStatus (prevented/stopped/detected/etc.)
* API returns unbounded flat arrays — client-side pagination required
* Shared filters: windowStart, windowEnd, driftType, attackId, attackType

### Proposed Approach
1. Add `get_simulation_result_drifts` — security posture lens (blocked/not-blocked transitions)
2. Add `get_simulation_status_drifts` — security control lens (final status transitions)
3. Both share: time window params, driftType, attack filters, client-side pagination (PAGE_SIZE=10)
4. Follow existing data server architecture: data_types.py → data_functions.py → data_server.py
5. Caching via SafeBreachCache (drift_cache, maxsize=3, TTL=600s)
6. Update existing tool docstrings with cross-references

### Affected Areas
* safebreach-mcp: data_types.py, data_functions.py, data_server.py, tests/

### Drift Tool Landscape (After Implementation)
| Tool | Paradigm | Purpose |
|------|----------|---------|
| get_test_drifts | Test-run-centric | Compare two test runs by name |
| get_simulation_result_drifts (NEW) | Time-window-centric | Blocked/not-blocked transitions |
| get_simulation_status_drifts (NEW) | Time-window-centric | Final status transitions |
| drifted_only filter | In-test | Filter drifted sims within a test |
| include_drift_info | Drill-down | Single simulation drift details |
| include_drift_count | Quick count | Number of drifts in a test |
```

**Acceptance Criteria:**
```markdown
* get_simulation_result_drifts tool exposed with: console, window_start, window_end,
  drift_type, attack_id, attack_type, from_status, to_status, page_number
* get_simulation_status_drifts tool exposed with: console, window_start, window_end,
  drift_type, attack_id, attack_type, from_final_status, to_final_status, page_number
* Client-side pagination (PAGE_SIZE=10) with total_drifts, total_pages, applied_filters
* Epoch-to-ISO-8601 time conversion for API calls
* Caching (SafeBreachCache, maxsize=3, TTL=600s)
* Input validation: mutual exclusion guard
* Error handling: 400 (too many simulations), 401 (auth), timeout
* Docstrings with USE THIS WHEN / DON'T USE FOR guidance for LLM tool selection
* Existing tool docstrings updated with cross-references
* hint_to_agent guiding to drill-down tools
* Unit tests: all filters, pagination, errors, cache
* E2E smoke tests
```
