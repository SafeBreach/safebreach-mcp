# Manual Test Cases — SAF-29727

Minimal set for product sign-off. Send each prompt from a Claude Desktop window connected to the
SafeBreach MCP data server running against an environment where backend PR #2799 is deployed
(e.g., staging.sbops.com).

## Prerequisites

- MCP data server running and connected to Claude Desktop
- Target console has drift data and backend PR #2799 deployed

---

## Test 1: attack_name filter narrows result drifts

**Prompt:**
> On staging, show me simulation result drifts for the last 60 days.
> Then show me only drifts for the attack named "Upload File over SMB".
> Then show me drifts for a nonexistent attack called "zzz_no_such_attack".

**Pass criteria:**
- First query returns drifts (total > 0)
- Second query returns fewer drifts than the first, but still > 0
- Third query returns zero drifts
- Agent used `attack_name` parameter in the tool calls

---

## Test 2: attack_type filter narrows status drifts

**Prompt:**
> On staging, show me simulation status drifts for the last 60 days,
> filtered to attack type "Suspicious File Creation".
> Compare the count to the unfiltered total.

**Pass criteria:**
- Agent calls `get_simulation_status_drifts` with `attack_type` parameter
- Filtered count is <= unfiltered count
- Response mentions the filter was applied

---

## Test 3: Security control drifts with attack filters

**Prompt:**
> On staging, show me security control drifts for "Mockion" in the last 60 days
> using contains transition mode.
> Then filter to only drifts for attack "Upload File over SMB".
> Then try filtering for attack ID 240.

**Pass criteria:**
- Unfiltered query returns drifts
- attack_name filtered query returns a non-empty subset
- attack_id filtered query returns a non-empty subset
- Agent used `attack_name` and `attack_id` parameters in the respective calls

---

## Test 4: Drill-down shows attack_name in attack_summary

**Prompt:**
> On staging, get simulation result drifts for the last 60 days,
> then drill down into the first drift group.
> What attack names appear in the attack summary?

**Pass criteria:**
- Agent drills down using a `drift_key` from the summary
- Response includes `attack_summary` with `attack_name` field populated
- Agent reports human-readable attack names (e.g., "Upload File over SMB")

---

## Test 5: No filters = unchanged behavior

**Prompt:**
> On staging, show me simulation result drifts, simulation status drifts,
> and security control drifts for "Mockion" — all for the last 60 days, no attack filters.

**Pass criteria:**
- All three tools return valid responses with no errors
- Response structure is correct (drift_groups, total_drifts, etc.)

---

## Test 6: Natural language end-to-end

**Prompt:**
> Show me all the drifts related to the "Upload File over SMB" attack
> against the Mockion security control on staging in the last 60 days.
> Which ones are regressions?

**Pass criteria:**
- Agent autonomously selects the right drift tool and applies attack_name filter
- Returns meaningful results identifying regressions by name
- Demonstrates the user story: "query drift data without additional processing"
