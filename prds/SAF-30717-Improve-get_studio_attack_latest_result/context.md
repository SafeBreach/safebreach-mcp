# SAF-30717 Investigation Context

## Status: Phase 6 — PRD Created

## Ticket Information
- **ID**: SAF-30717
- **Title**: get_studio_attack_latest_result returns simulation-scoped timing and count instead of test-level aggregates
- **Type**: Bug
- **Status**: To Do
- **Assignee**: Yossi Attas
- **Priority**: Medium

## Task Scope
Enrich `get_studio_attack_latest_result` response with test-level metadata so calling agents can correctly determine whether a test is still running, how long the overall test took, and how many simulations exist in total.

## Investigation Findings

### 1. Current Response Structure (studio_server.py:627-814)

The tool queries the execution history API (`POST executionsHistoryResults`) and returns individual simulation results. Response includes:
- `Total Executions Found`: from API's `total` field (actual count of matching simulations)
- `Showing`: number of results returned (capped by `max_results`, default=1)
- Per-simulation: timing, status, simulators, drift, logs

**Key observation**: `total_found` does correctly reflect the API total (not `max_results`). However, if a test is still running and only 1 simulation has completed, the API truthfully returns `total: 1`. The problem is there's no context telling the agent the test expects 22 simulations and is still running.

### 2. Business Logic (studio_functions.py:1217-1365)

- Calls `POST /api/data/v1/accounts/{account_id}/executionsHistoryResults`
- Query: `Playbook_id:("{attack_id}")` with optional `AND runId:{test_id}`
- Sorts by `startTime` descending, pages with `pageSize: min(page_size, max_results)`
- Returns: `executions`, `returned_count`, `total_found`, `has_more`

**Missing**: No call to the test summary API. The function only knows about simulations, not the parent test.

### 3. Data Transformations (studio_types.py:219-343)

`get_execution_result_mapping()` transforms raw simulation data. Each simulation already has `test_id` (planRunId) which is the key to fetch test-level data.

### 4. How Data Server Gets Test-Level Data (data_functions.py:397-469)

`sb_get_test_details()` fetches from `GET /api/data/v1/accounts/{account_id}/testsummaries/{test_id}`. The response includes:
- `status`: running, completed, canceled, failed
- `startTime`, `endTime`, `duration`
- `finalStatus`: dict with simulation counts (missed, stopped, prevented, detected, logged, no-result, inconsistent)
- `planName`: test name

This is the same API endpoint the studio server can call to enrich its response.

### 5. Test File (test_studio_functions.py:1732-1941)

7 existing test cases covering success, multiple results, empty, validation, and errors. Mock data has 2 executions with `total: 2`.

## Problem Analysis

### Problem Scope
The `get_studio_attack_latest_result` tool returns accurate simulation-level data but lacks test-level context. This creates two information gaps for calling agents:

1. **No test status**: The agent cannot tell if a test is still running or completed. When a test with 22 expected simulations has only 1 completed, the tool returns that 1 simulation with no indication more are coming.

2. **No test-level timing**: The timing shown (`start_time`/`end_time`) belongs to the individual simulation, not the overall test. An agent sees "7 seconds" for a single simulation and assumes the test took 7 seconds, when the full test actually took 3+ minutes.

3. **No total simulation expectation**: `total_found` is the count of completed simulations matching the query at query time, not the expected total for the test. There's no way to know "1 of 22" without additional context.

### Affected Areas
- `studio_functions.py`: `sb_get_studio_attack_latest_result()` — needs to fetch test summary
- `studio_server.py`: `get_studio_attack_latest_result` tool — needs to format and display test-level section
- `studio_types.py`: May need a helper to transform test summary data
- `test_studio_functions.py`: Tests need updating for new response fields

### Risks
- **Extra API call**: Fetching test summary adds one GET request per invocation. Low risk since the endpoint is lightweight.
- **test_id availability**: The `planRunId` is already present in each simulation result, so we always have the key needed to fetch the test summary. When `test_id` parameter is provided, we can use it directly. When not provided, we can extract it from the first (latest) simulation result.

### Edge Cases
- No simulations found (total_found=0): No test_id available to fetch summary — skip enrichment
- Multiple test_ids in results (when `test_id` param not provided and `max_results > 1`): Simulations from different test runs may appear. Should fetch test summary for each unique test_id, or just the first one.
- Test summary API failure: Should not break the tool — gracefully degrade to current behavior

### Dependencies
- Data server's `testsummaries` API endpoint (already used extensively by `data_functions.py`)
- Auth infrastructure (`get_auth_headers_for_console`, `get_api_base_url`) — already available in studio_functions.py

## Brainstorming Results (Phase 5)

### Chosen Approach
All decisions agreed upon:

| Decision | Choice |
|----------|--------|
| When to fetch test summary | Always — use `test_id` param or extract `planRunId` from first simulation |
| Status breakdown format | Status + count with total line (no explanations) |
| hint_to_agent target | Suggest both: poll this tool OR use `get_test_details` from Data Server |
| Multiple test runs | Overview for first (latest) test only |
| Extra API call latency | Always fetch, graceful degradation on failure (try/except, log warning) |
