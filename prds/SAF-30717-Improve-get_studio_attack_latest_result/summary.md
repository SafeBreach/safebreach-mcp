# SAF-30717: Enrich get_studio_attack_latest_result with Test-Level Context

## Problem Statement

`get_studio_attack_latest_result` returns accurate simulation-level data but lacks test-level context, causing calling agents to misinterpret results. Specifically:
- Agents cannot determine if a test is still running or completed
- Timing reflects individual simulations, not the overall test duration
- `total_found` shows completed simulations at query time, not the expected total

## Proposed Fix

Enrich the tool's response with a **Test Overview** section by fetching test summary data from the existing `GET /testsummaries/{test_id}` API endpoint. This is additive — no changes to existing response fields.

## New Response Fields

| Field | Source | Purpose |
|-------|--------|---------|
| Test Status | `testsummaries.status` | Running/completed/canceled/failed |
| Test Start Time | `testsummaries.startTime` | When the overall test began |
| Test End Time | `testsummaries.endTime` | When the overall test finished (null if running) |
| Test Duration | `testsummaries.duration` | Total test duration |
| Simulation Status Breakdown | `testsummaries.finalStatus` | Counts by status (missed, stopped, prevented, etc.) with total |
| hint_to_agent | Computed | Polling guidance when test is still running |

## Affected Files

| File | Change |
|------|--------|
| `studio_functions.py` | Add test summary fetch after simulation query |
| `studio_server.py` | Add "Test Overview" section to formatted response |
| `test_studio_functions.py` | Update tests for new response fields |

## Acceptance Criteria

- [ ] Response includes test-level status (running/completed/canceled/failed)
- [ ] Response includes test-level start/end times and duration
- [ ] Response includes simulation status breakdown with total count
- [ ] When test is still running, response includes `hint_to_agent` with polling guidance
- [ ] When no simulations found (total_found=0), test overview is gracefully skipped
- [ ] Test summary API failure degrades gracefully (existing response preserved)
- [ ] Existing unit tests continue to pass
- [ ] New unit tests cover the enrichment logic
