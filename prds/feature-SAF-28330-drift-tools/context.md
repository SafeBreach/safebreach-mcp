# Planning Context: SAF-28330

## Status
Phase 3: Create Working Branch and PRD Context

## JIRA Details
- **Ticket**: SAF-28330
- **Summary**: Add Simulation Result and Status Drift Tools to MCP
- **Type**: Story
- **Status**: In Progress
- **Assignee**: Yossi Attas
- **Sprint**: Saf sprint 84

## Description
Expose the Simulation Status and Result Drift API as two specialized MCP tools (get_simulation_result_drifts and get_simulation_status_drifts), enabling time-window-based drift analysis complementing existing test-run-centric drift tools.

## Requirements (from JIRA)

### Technical Context
* New API endpoint: `POST /api/data/v1/accounts/{accountId}/drift/simulationStatus`
* API supports two mutually exclusive filter modes:
  * Result mode: fromStatus/toStatus (FAIL/SUCCESS) — blocked vs not-blocked
  * Final Status mode: fromFinalStatus/toFinalStatus (prevented/stopped/detected/logged/missed/inconsistent)
* API returns unbounded flat arrays — client-side pagination required
* Shared filters: windowStart, windowEnd, driftType, attackId, attackType

### Proposed Approach
1. Add `get_simulation_result_drifts` — security posture lens (blocked/not-blocked transitions)
2. Add `get_simulation_status_drifts` — security control lens (final status transitions)
3. Both share: time window params, driftType, attack filters, client-side pagination (PAGE_SIZE=10)
4. Follow existing data server architecture: data_types.py → data_functions.py → data_server.py
5. Caching via SafeBreachCache (drift_cache, maxsize=3, TTL=600s)
6. Update existing tool docstrings with cross-references

### Acceptance Criteria
* Both tools exposed with appropriate filters (console, window_start, window_end, drift_type, attack_id, attack_type, ±status filters, page_number)
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

## Clarifications from User

### Investigation Scope
- Focus on Data server only (data_types.py, data_functions.py, data_server.py)
- Do NOT investigate existing drift tools, tests, or caching infrastructure in detail

### Implementation Preferences
1. Use existing drift function patterns as template
2. Prioritize docstring clarity for LLM tool selection
3. Ensure consistency with all other tools exposed by the data MCP server

## Investigation Findings
(Phase 4)

## Brainstorming Results
(Phase 5)

## Implementation Plan
(Phase 6)
