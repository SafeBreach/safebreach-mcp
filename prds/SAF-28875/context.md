# Ticket Context: SAF-28875

## Status
Phase 6: PRD Created

## Mode
Improving

## Original Ticket
- **Summary**: [safebreach-mcp] MCP tools require the LLM to perform redundant conversions of ISO dates
- **Status**: To Do
- **Assignee**: Yossi Attas
- **Sprint**: Saf sprint 84
- **Estimate**: 2h
- **Description**: 4 Data Server tools (10 params) accept only epoch-ms timestamps, forcing LLMs to call
  `convert_datetime_to_epoch` before every time-filtered query. Proposed solution: accept both ISO 8601
  strings and epoch milliseconds, convert internally.

## Task Scope
Validate the proposed `_normalize_timestamp` approach by investigating `datetime_utils.py`, existing
timestamp handling patterns, and confirming the implementation approach is sound.

## Repositories Under Investigation
- /Users/yossiattas/Public/safebreach-mcp

## Investigation Findings

### 1. Existing Infrastructure (datetime_utils.py)
- `convert_datetime_to_epoch(datetime_str)` — ISO 8601 string to epoch ms. Supports Z, +00:00, offsets.
  Uses `datetime.fromisoformat()` internally. Returns dict with `epoch_timestamp` key or `error` key.
- `convert_epoch_to_datetime(epoch_timestamp)` — epoch to ISO string with auto-detection:
  `> 10^12` = milliseconds, else seconds.
- Both functions are in `safebreach_mcp_core/datetime_utils.py` and importable from any server.

### 2. Precedent: _normalize_numeric() Pattern (data_functions.py:40-52)
- Accepts `Any`, returns `Optional[float]`. Handles int/float pass-through and string-to-float
  conversion with try/except. Returns None on failure.
- **Direct parallel** for a `_normalize_timestamp()` helper.

### 3. FastMCP Union Type Support
- Python 3.12+ (`requires-python = ">=3.12"` in pyproject.toml) supports `str | int` natively.
- FastMCP introspects function signatures for tool parameters. Union types work — no framework
  restriction. Validation is the function's responsibility.

### 4. Where Normalization Should Happen
- **Option A**: In data_server.py tool wrappers (before calling data_functions.py)
- **Option B**: In data_functions.py at the top of each public function
- The `_normalize_numeric` precedent uses Option B (functions normalize internally).

### 5. Time Range Validation
- Validation (`start <= end`) at data_functions.py:116-118. Compares numeric values.
- Normalization must happen BEFORE validation for correct comparison.

### 6. Edge Cases
- **Date-only strings** ("2026-03-01"): `datetime.fromisoformat()` rejects these — NOT supported.
  Require time component (e.g., "2026-03-01T00:00:00Z").
- **Timezone handling**: Always converts to UTC epoch (Unix epoch is UTC-relative). No issues.
- **Relative expressions** ("7 days ago"): Out of scope. Not supported.
- **String-numeric** ("1705314600"): Could be handled but ambiguous — is it a number or malformed ISO?

### 7. Affected Parameters (10 total across 4 tools)
| Tool | Parameters | data_server.py lines |
|------|------------|---------------------|
| get_tests_history | start_date, end_date | 60-61 |
| get_test_simulations | start_time, end_time | 108-109 |
| get_simulation_result_drifts | window_start, window_end, look_back_time | 333-335, 342 |
| get_simulation_status_drifts | window_start, window_end, look_back_time | 399-401, 407 |

### 8. Risk Assessment
**Low risk**: Existing infrastructure covers all cases. Backward compatible. No API changes.

### 9. Regression Risk Analysis
- **Two epoch scales**: Tests use seconds (1640995200) for tests_history/simulations, milliseconds
  (1709251200000) for drift tools. Normalizer's `> 10^12` threshold handles both.
- **97 existing tests** in test_data_functions.py, 89 in test_drift_tools.py, 255 lines in
  test_utilities_server.py
- **String-to-int conversion already tested**: `_safe_time_compare()` handles "1640995200" strings
- **Range validation tested**: start_date > end_date raises ValueError (lines 1222, 1240)
- **Mock data patterns**: Fixtures use epoch seconds in test/simulation data. Must remain untouched.
- **Key regression checklist**: epoch int passthrough, string-to-int conversion, missing field handling,
  range validation, ordering, pagination, drift start_time comparison, None timestamps in findings

## Brainstorming Results
- **Helper location**: `safebreach_mcp_core/datetime_utils.py` (shared, reusable)
- **Integration approach**: Approach A — normalize in data_server.py tool wrappers, backend keeps int-only
- **String-numeric handling**: Treat as epoch (forgiving parsing)
- **Backward compat**: Not a concern, but accept both str|int for flexibility
- **Alternatives rejected**: normalize in data_functions.py (mixes concerns), both layers (redundant),
  string-only params (breaks epoch passthrough)

## Proposed Improvements
- See summary.md for full JIRA-ready content
