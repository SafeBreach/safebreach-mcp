# Manual LLM Tool Selection Tests — SAF-28330

## Purpose

Verify that an LLM agent with access to all data server tools consistently selects the correct drift
tool based on natural language prompts. These tests validate that docstrings, "USE THIS WHEN",
"DON'T USE FOR", and "TWO-PHASE USAGE" guidance are effective for tool selection.

## Setup

1. Connect an LLM agent to the data server MCP tools
2. Ensure all drift tools are available:
   - `get_simulation_result_drifts` (new)
   - `get_simulation_status_drifts` (new)
   - `get_test_drifts` (existing)
   - `get_test_simulations` with `drifted_only` (existing)
   - `get_test_simulation_details` with `include_drift_info` (existing)
3. Use a real console with recent test data

## Test Matrix

### Test 1: Time-window result drift — should select `get_simulation_result_drifts`

**Prompt**: "Show me all attacks that went from blocked to not-blocked in the last 7 days on demo"

**Expected tool**: `get_simulation_result_drifts`
**Expected params**: `console="demo"`, `window_start`/`window_end` covering 7 days,
`from_status="FAIL"`, `to_status="SUCCESS"`
**Why not others**: No test ID involved → not `get_test_drifts`. Time-window scope → not
`get_test_simulations`.

**Pass criteria**: Agent calls `get_simulation_result_drifts` with correct status filters.

---

### Test 2: Time-window status drift — should select `get_simulation_status_drifts`

**Prompt**: "Which simulations changed from prevented to just logged between March 1 and March 5
on demo?"

**Expected tool**: `get_simulation_status_drifts`
**Expected params**: `console="demo"`, appropriate `window_start`/`window_end`,
`from_final_status="prevented"`, `to_final_status="logged"`
**Why not others**: Final status transition → not `get_simulation_result_drifts`.
No test ID → not `get_test_drifts`.

**Pass criteria**: Agent calls `get_simulation_status_drifts` with correct final status filters.

---

### Test 3: Test-run comparison — should select `get_test_drifts`

**Prompt**: "Compare test 12345 with its previous run and show me what drifted on demo"

**Expected tool**: `get_test_drifts`
**Expected params**: `console="demo"`, `test_id="12345"`
**Why not others**: Comparing two specific test runs → exactly what `get_test_drifts` does.
Not a time-window query → not `get_simulation_result_drifts`/`get_simulation_status_drifts`.

**Pass criteria**: Agent calls `get_test_drifts` with the test ID.

---

### Test 4: Drifted simulations within a test — should select `get_test_simulations`

**Prompt**: "List the drifted simulations in test 12345 on demo"

**Expected tool**: `get_test_simulations`
**Expected params**: `console="demo"`, `test_id="12345"`, `drifted_only=True`
**Why not others**: Filtering within a single test → `get_test_simulations`.
Not analyzing drift types/transitions → not `get_test_drifts`.

**Pass criteria**: Agent calls `get_test_simulations` with `drifted_only=True`.

---

### Test 5: Single simulation drift detail — should select `get_test_simulation_details`

**Prompt**: "Show me drift details for simulation 9876543 on demo"

**Expected tool**: `get_test_simulation_details`
**Expected params**: `console="demo"`, `simulation_id="9876543"`, `include_drift_info=True`
**Why not others**: Single simulation → `get_test_simulation_details`.
Not a time window or test comparison.

**Pass criteria**: Agent calls `get_test_simulation_details` with `include_drift_info=True`.

---

### Test 6: Two-phase usage — summary then drill-down

**Prompt sequence**:
1. "What types of security posture drifts happened on demo in the last 3 days?"
2. (After seeing summary) "Show me the individual records for the fail-success group"

**Expected flow**:
1. Agent calls `get_simulation_result_drifts` **without** `drift_key` → gets grouped summary
2. Agent calls `get_simulation_result_drifts` **with** `drift_key="fail-success"` → gets paginated
   records

**Pass criteria**: Agent uses the two-phase pattern correctly — summary first, drill-down second.

---

### Test 7: Ambiguous prompt — broad drift question

**Prompt**: "Are there any security regressions on demo this week?"

**Expected tool**: `get_simulation_result_drifts` OR `get_simulation_status_drifts`
**Expected params**: `drift_type="regression"`, appropriate time window
**Acceptable**: Either tool is valid — the agent should pick one and explain why.

**Pass criteria**: Agent selects one of the two new tools with `drift_type="regression"`.
Does NOT call `get_test_drifts` (no test ID).

---

### Test 8: Result drift without status filters — unfiltered posture view

**Prompt**: "Give me a full overview of all result drifts on demo for the past 2 weeks"

**Expected tool**: `get_simulation_result_drifts`
**Expected params**: `console="demo"`, `window_start`/`window_end` covering 2 weeks,
no `from_status`/`to_status` (unfiltered)
**Why not others**: "Result drifts" maps directly to `get_simulation_result_drifts`.

**Pass criteria**: Agent calls `get_simulation_result_drifts` without status filters.

---

### Test 9: Status drift with attack filter

**Prompt**: "Show detection drift for attack 1263 on demo in the last month"

**Expected tool**: `get_simulation_status_drifts`
**Expected params**: `console="demo"`, `attack_id=1263`, appropriate time window
**Why not others**: "Detection drift" implies final status transitions → `get_simulation_status_drifts`.
Attack filter narrows scope within the time-window tool.

**Pass criteria**: Agent calls `get_simulation_status_drifts` with `attack_id=1263`.

---

### Test 10: Drill-down pagination

**Prompt sequence**:
1. "Show me status drifts on demo for the past week"
2. (After summary) "Drill into the prevented-logged group"
3. (After page 0) "Next page"

**Expected flow**:
1. `get_simulation_status_drifts` without `drift_key`
2. `get_simulation_status_drifts` with `drift_key="prevented-logged"`, `page_number=0`
3. `get_simulation_status_drifts` with `drift_key="prevented-logged"`, `page_number=1`

**Pass criteria**: Agent follows the full two-phase + pagination flow correctly.

---

## Results Tracking

| Test | Result | Notes |
|------|--------|-------|
| Test 1: Time-window result drift | | |
| Test 2: Time-window status drift | | |
| Test 3: Test-run comparison | | |
| Test 4: Drifted sims in test | | |
| Test 5: Single sim drift detail | | |
| Test 6: Two-phase usage | | |
| Test 7: Ambiguous prompt | | |
| Test 8: Unfiltered result drift | | |
| Test 9: Status drift + attack filter | | |
| Test 10: Drill-down pagination | | |

## Known Drift Windows on pentest01

The following time ranges contain verified **simulation status drifts** (final status transitions)
that can be used for live testing:

| # | Window (UTC) | Drifts | Breakdown |
|---|-------------|--------|-----------|
| 1 | Feb 5, 2026 08:00–14:00 | 6 | logged→prevented ×2, logged→stopped ×2, missed→stopped ×2 |
| 2 | Feb 15, 2026 14:00–20:00 | 4 | missed→stopped ×3, logged→stopped ×1 |
| 3 | Feb 26, 2026 14:00–20:00 | 1 | detected→stopped ×1 |
| 4 | Mar 4, 2026 12:00–18:00 | 1 | inconsistent→prevented ×1 |

**Notes**:
- All drifts above are from not-blocked to blocked (security improvements)
- Use `get_simulation_status_drifts` with `console="pentest01"` and appropriate epoch timestamps
- The API may return additional drifts beyond these counts (the above are filtered subsets)
- Epoch timestamps for Window 1: `window_start=1770278400000`, `window_end=1770300000000`

## Sign-off

- [ ] All 10 tests executed
- [ ] At least 9/10 pass (correct tool selected)
- [ ] Two-phase usage (Tests 6, 10) works as designed
- [ ] No test consistently selects the wrong tool (indicates docstring issue)

**Tested by**: _______________
**Date**: _______________
