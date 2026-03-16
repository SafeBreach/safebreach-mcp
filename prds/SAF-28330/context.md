# Planning Context: SAF-28330

## Status
Phase 6: PRD Created

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

### Architecture Overview
The Data Server uses a three-tier pattern: `data_server.py` (MCP tool registration) → `data_functions.py` (business logic & API communication) → `data_types.py` (data transformations). All HTTP API calls and caching flow through the same pathway, ensuring consistency.

### Key Patterns Identified

#### 1. Drift Type Metadata (drifts_metadata.py)
- 273 drift pattern entries with structured mappings
- Each drift has: `type_of_drift`, `security_impact` (positive/negative/neutral), `description`, `hint_to_llm`
- Reference for new tools: use similar metadata structure for classifying drift transitions

#### 2. Reference Implementation: get_test_drifts (Lines 1464-1649, data_functions.py)
- Validates parameters, retrieves test details, gets simulations via cache-or-API pattern
- Groups by drift_tracking_code, compares statuses, looks up drift metadata
- Returns structured result with `total_drifts` and `_metadata` section
- Pattern to follow: validate → cache check → API call → transform → return with metadata

#### 3. HTTP API Call Pattern (Lines 206-235, data_functions.py)
```python
base_url = get_api_base_url(console, 'data')
account_id = get_api_account_id(console)
headers = {"Content-Type": "application/json", "x-apitoken": apitoken}
response = requests.post(api_url, headers=headers, json=data, timeout=120)
```
Key: Uses requests.post for endpoint calls, 120-second timeout, proper error handling

#### 4. SafeBreachCache Usage (Lines 30-32, data_functions.py)
- Instantiation: `SafeBreachCache(name="simulations", maxsize=3, ttl=600)`
- Cache size 3 (stores 3 different caches), TTL 600 seconds
- Usage: Check cache first, fetch from API on miss, store after transformation
- Recommended for new tools: `SafeBreachCache(name="simulation_drifts", maxsize=3, ttl=600)`

#### 5. Client-Side Pagination (Lines 596-627, data_functions.py)
- PAGE_SIZE = 10 (constant at line 35)
- Calculation: `total_pages = (total_items + PAGE_SIZE - 1) // PAGE_SIZE`
- Response includes: `page_number`, `total_pages`, `total_simulations`, items array, `applied_filters`, `hint_to_agent`
- Pattern: API returns unbounded array → paginate locally → include navigation hints for LLM

#### 6. MCP Tool Registration (Lines 46-75, data_server.py)
- @mcp.tool() decorator with name, description parameters
- Docstring pattern: What it does → specific outputs → key parameters → cross-references
- Tools should include "USE THIS WHEN" guidance for LLM tool selection

#### 7. Error Handling Convention (Lines 1802-1830, data_functions.py)
- HTTP status checks: 404 (not found), 401 (auth failed), raise_for_status()
- JSON parsing wrapped in try-except
- Timeout: 120 seconds standard

### Constants & Configuration
| Item | Location | Value |
|------|----------|-------|
| PAGE_SIZE | data_functions.py:35 | 10 |
| simulations_cache | data_functions.py:31 | maxsize=3, ttl=600s |
| findings_cache | data_functions.py:1206 | maxsize=3, ttl=600s |
| full_simulation_logs_cache | data_functions.py:1653 | maxsize=2, ttl=300s |

### Implementation Readiness
✅ Data server architecture fully understood
✅ Reference patterns (get_test_drifts) identified
✅ Cache instantiation pattern confirmed
✅ HTTP API call pattern documented
✅ Client-side pagination methodology verified
✅ MCP tool registration approach clarified
✅ Error handling conventions established
✅ Test patterns reviewed

## Brainstorming Results

### Chosen Approach: C — Shared Core with Validation Layer

Clear separation of concerns with explicit validation, fetch, paginate, and enrich layers:

**data_types.py**:
- `transform_drift_record()` — enriches each record with drifts_metadata lookup (security_impact, description)
- `build_drift_api_payload()` — constructs API request body from tool parameters

**data_functions.py**:
- `_fetch_and_cache_simulation_drifts(console, payload)` — handles API call + caching only
- `_paginate_and_enrich_drifts(records, page_number, applied_filters)` — handles pagination + enrichment
- `sb_get_simulation_result_drifts()` — validates result-mode params, builds payload, delegates
- `sb_get_simulation_status_drifts()` — validates status-mode params, builds payload, delegates

**data_server.py**:
- Two @mcp.tool() registrations with distinct docstrings and "USE THIS WHEN / DON'T USE FOR" guidance

### Design Decisions
1. **Full detail response** — Keep all API fields including loggedBy/reportedBy/alertedBy/preventedBy arrays
2. **Enrich all records** — Look up drift metadata from drifts_metadata.py for each record
3. **Single shared cache** — One SafeBreachCache(name='simulation_drifts', maxsize=3, ttl=600)
4. **Cache key includes filter mode** — Distinguish result vs status queries in cache key

### Alternatives Rejected
- **Approach A (Thin Wrappers)**: Too thin — no clear validation layer
- **Approach B (Fully Separate)**: Code duplication risk, inconsistency over time

## Implementation Plan
(Phase 6)
