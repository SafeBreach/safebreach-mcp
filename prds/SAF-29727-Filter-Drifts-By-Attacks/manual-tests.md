# Manual Test Cases — SAF-29727

Minimal set for product sign-off. Run against an environment where backend PR #2799 is deployed
(e.g., staging.sbops.com, account 3477291461).

## Prerequisites

- MCP data server running (`uv run -m safebreach_mcp_data.data_server`)
- Environment with drift data and backend PR #2799 deployed

---

## 1. Result drifts — attack_name filter narrows results

**Steps:**
1. Call `get_simulation_result_drifts` without any attack filter (wide window)
2. Note `total_drifts` count
3. Call again with `attack_name="Upload File over SMB"`
4. Call again with `attack_name="zzz_nonexistent"`

**Expected:**
- Step 3 returns `total_drifts > 0` and `< step 2 count`
- Step 4 returns `total_drifts == 0`
- Both filtered calls show `attack_name` in `applied_filters`

---

## 2. Status drifts — attack_type filter narrows results

**Steps:**
1. Call `get_simulation_status_drifts` without attack filters
2. Call again with `attack_type="Suspicious File Creation"`

**Expected:**
- Filtered result has `total_drifts <= unfiltered total_drifts`
- `applied_filters` contains `attack_type`

---

## 3. Security control drifts — all three attack filters work

**Steps:**
1. Call `get_security_control_drifts` with `security_control="Mockion"`,
   `transition_matching_mode="contains"`, no attack filters
2. Call again adding `attack_name="Upload File over SMB"`
3. Call again adding `attack_id=240`
4. Call again with `attack_name="zzz_nonexistent"`

**Expected:**
- Steps 2-3 return `total_drifts > 0` (subset of step 1)
- Step 4 returns `total_drifts == 0`
- `applied_filters` reflects the params passed

---

## 4. Drill-down attack_summary includes attack_name

**Steps:**
1. Call any drift tool in drill-down mode (`drift_key` set to a valid group key)
2. Inspect `attack_summary` in the response

**Expected:**
- Each entry in `attack_summary` has `attack_id`, `attack_name`, `attack_types`, `count`
- `attack_name` is a non-null string (e.g., "Upload File over SMB")

---

## 5. No filters = unchanged behavior

**Steps:**
1. Call each of the 3 drift tools without any attack filter params

**Expected:**
- Response structure identical to pre-change behavior
- No errors, no missing fields

---

## 6. Natural language query via MCP agent

**Steps:**
1. Ask an MCP-connected agent: "Show me drifts for attack Upload File over SMB last 30 days"

**Expected:**
- Agent uses `attack_name` filter in the drift tool call
- Returns meaningful filtered drift results
