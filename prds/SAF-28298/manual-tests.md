# SAF-28298: Manual Test Cases — Claude Desktop Sign-off

## Item 1: Inline finalStatus Counts

### TC-1.1: Status counts always present without parameter

**Prompt:** "Get the details of test {test_id} on {console}"

**Expected:**
- [ ] Response includes `simulations_statistics` list
- [ ] Contains 7 entries: missed, stopped, prevented, detected, logged, no-result, inconsistent
- [ ] Each entry has `status`, `explanation`, and `count` fields
- [ ] No `drifted_count` entry (drift not requested)
- [ ] Agent did NOT need to pass any extra parameter to get stats

### TC-1.2: Drift count requires explicit opt-in

**Prompt:** "Get the details of test {test_id} on {console} and include the drift count"

**Expected:**
- [ ] Response includes `simulations_statistics` with 8 entries (7 statuses + 1 drift)
- [ ] Drift entry has `drifted_count` (integer) and `explanation`
- [ ] Agent used `include_drift_count=True` in the tool call

### TC-1.4: Drift count performance on large test

**Prompt:** "Get the details of test {large_test_id} on {console} with drift count"

**Expected:**
- [ ] Completes without error (may take longer)
- [ ] Agent mentions or the tool description warns about potential slowness
- [ ] Returns valid drift count integer

---

## Item 2: Propagate Findings in Test Summary

### TC-2.1: Propagate test includes findings

**Prompt:** "Get the details of the latest Propagate test on {console}"

**Expected:**
- [ ] Response includes `test_type` containing "Propagate" or "ALM"
- [ ] Response includes `findings_count` (integer)
- [ ] Response includes `compromised_hosts` (integer or object)
- [ ] Agent did NOT need to call `get_test_findings_counts` separately

### TC-2.2: Validate test excludes findings

**Prompt:** "Get the details of the latest Validate test on {console}"

**Expected:**
- [ ] Response includes `test_type` containing "Validate" or "BAS"
- [ ] Response does NOT include `findings_count`
- [ ] Response does NOT include `compromised_hosts`

### TC-2.3: Agent workflow efficiency

**Prompt:** "Give me a summary of the latest Propagate test on {console}, including findings"

**Expected:**
- [ ] Agent calls `get_test_details` only (not `get_test_findings_counts`)
- [ ] Agent presents findings count and compromised hosts from the single call
- [ ] Total tool calls: 1-2 (history + details), NOT 3+ (history + details + findings)

---

## Item 3: Concurrency Limiter

### TC-3.1: Normal operation — no throttling

**Prompt:** "Get the details of test {test_id} on {console}"

**Expected:**
- [ ] Request succeeds normally (HTTP 200)
- [ ] No 429 errors in response
- [ ] No visible degradation

### TC-3.2: Tool description awareness

**Prompt:** "What tools are available on the data server?"

**Expected:**
- [ ] `get_test_details` description mentions `include_drift_count` may be slow for large tests
- [ ] Agent can explain the performance tradeoff when asked

---

## Cross-cutting

### TC-X.1: Full agent workflow — Validate test

**Prompt:** "Show me the results of the latest Validate test on {console}. I want to know the status
breakdown and whether any simulations drifted."

**Expected:**
- [ ] Agent calls `get_tests_history` to find the latest test
- [ ] Agent calls `get_test_details` with `include_drift_count=True`
- [ ] Agent presents the 7 status counts + drift count
- [ ] No separate API call for status counts (they come inline)

### TC-X.2: Full agent workflow — Propagate test

**Prompt:** "Show me the results of the latest Propagate test on {console}. How many findings were
there and how many hosts were compromised?"

**Expected:**
- [ ] Agent calls `get_tests_history` with type filter for propagate
- [ ] Agent calls `get_test_details` (single call)
- [ ] Agent presents findings count and compromised hosts from the details response
- [ ] Agent does NOT call `get_test_findings_counts` separately

---

## Test Environment

| Field | Value |
|-------|-------|
| Console | __________________ |
| Validate test_id | __________________ |
| Propagate test_id | __________________ |
| Large test_id (1000+ sims) | __________________ |
| Tester | __________________ |
| Date | __________________ |

## Sign-off

- [ ] All test cases passed
- [ ] Signed off by: __________________
- [ ] Date: __________________
