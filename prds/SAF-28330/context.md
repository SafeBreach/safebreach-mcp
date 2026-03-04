# Ticket Context: SAF-28330

## Status
Phase 6: Summary Created

## Mode
Improving

## Original Ticket
- **Summary**: Add Simulation Status Drift API to MCP
- **Description**: Expose the Simulation Status and Result Drift API endpoint as an MCP tool with comprehensive filtering support (time windows, drift types, attack filters, final status filters, simulation result filters). The existing MCP has 4 drift-related tools and this story aims to rethink the approach to drift analysis.
- **Acceptance Criteria**: API available as MCP tool, all filters mapped, functional tests, example prompts documented, product review.
- **Status**: In Progress
- **Type**: Story
- **Sprint**: Saf sprint 84
- **Assignee**: Yossi Attas
- **Reporter**: Shahaf Raviv

## Task Scope
Introduce the new Simulation Status Drift API tool while ensuring clear separation of responsibilities between existing drift tools and smooth, continuous user flow transitions across all drift-related MCP tools. Avoid duplication of functionality.

## Repositories Under Investigation
- /Users/yossiattas/Public/safebreach-mcp

## Investigation Findings

### Existing Drift Tools (4 features)

| Tool/Feature | Scope | API Called | Returns |
|---|---|---|---|
| `get_test_drifts` | Two tests (same name) | testsummaries + executionsHistoryResults | Status change patterns, exclusive sims |
| `drifted_only` filter | Single test | executionsHistoryResults | Simulations where driftType != "no_drift" |
| `include_drift_info` | Single simulation | executionsHistoryResults (x2) | Drift type, previous sim ID, security impact |
| `include_drift_count` | Test summary | executionsHistoryResults (streaming) | Count of drifted sims |

### Architecture Patterns
- **Data flow**: `data_types.py` (transforms) -> `data_functions.py` (business logic) -> `data_server.py` (MCP tools)
- **HTTP client**: `requests.post/get` with `x-apitoken` header, 120s timeout
- **Caching**: `SafeBreachCache` (TTLCache wrapper), simulations_cache (maxsize=3, ttl=600s)
- **Pagination**: PAGE_SIZE=10 for MCP, 100 for API calls
- **Drift metadata**: `drifts_metadata.py` has 273 drift pattern entries

### User Workflow (Current)
1. `get_test_details(include_drift_count=True)` - Quick health check
2. `get_test_drifts(test_id)` - Compare two test runs by name
3. `get_test_simulations(drifted_only=True)` - List drifted sims in a test
4. `get_simulation_details(include_drift_info=True)` - Inspect specific drift
5. `get_full_simulation_logs()` - Deep forensic analysis

### Key Risk: Overlap with New Tool
The new API provides server-side filtering (time windows, drift types, attack/status filters)
that could subsume parts of `get_test_drifts` and `drifted_only`. The new tool should
**complement** existing tools by providing a **filtered view of drift states** directly from
the API, rather than replacing client-side filtering.

## Brainstorming Results

### Approach: Two Specialized Tools (Approach B)
Split the new API into two tools based on analytical lens:
1. **`get_simulation_result_drifts`** — Security posture perspective (blocked/not-blocked)
2. **`get_simulation_status_drifts`** — Security control perspective (prevented/stopped/detected/logged/missed)

### API Confirmed
- **Endpoint**: `POST /api/data/v1/accounts/{accountId}/drift/simulationStatus`
- **Response**: Flat array of drift records (no server-side pagination, can be 10K+ items)
- **Mutual exclusion**: Server enforces — cannot mix `fromStatus`/`toStatus` with
  `fromFinalStatus`/`toFinalStatus` (returns 400)
- **500K simulation limit**: Returns error if time window covers too many simulations
- **Response fields**: trackingId, attackId, attackTypes, from/to objects with simulationId,
  executionTime, finalStatus, status, loggedBy, reportedBy, alertedBy, preventedBy

### Consolidation Decision
Keep all 4 existing tools. Each has unique value:
- `get_test_drifts`: Test-run-centric comparison, exclusive simulation detection, auto-baseline
- `drifted_only`: In-test filtering convenience
- `include_drift_info`: Single simulation drill-down
- `include_drift_count`: Quick health indicator

## Proposed Improvements
(Phase 6)
