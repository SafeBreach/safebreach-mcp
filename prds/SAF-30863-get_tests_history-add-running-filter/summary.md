# SAF-30863: Add "running" filter + rename get_tests_history to get_tests

## Title
Add "running" status filter and rename get_tests_history to get_tests

## Description
HELM incorrectly reports "no tests are currently running" because the `get_tests_history` MCP tool
description does not list "running" as a valid `status_filter` value. The AI agent reads the tool
description to determine valid options and never attempts to filter by "running".

The underlying business logic in `data_functions.py` already supports "running" (including
cache-bypass for fresh data), but the tool registration in `data_server.py` and project
documentation only advertise `"completed"`, `"canceled"`, and `"failed"`.

Additionally, the tool name `get_tests_history` is misleading — it implies only historical/past
tests, which reinforces the AI agent's assumption that running tests aren't available. Renaming
to `get_tests` better reflects that the tool returns tests in any status.

### Root Cause
1. Tool description in `data_server.py` omits "running" from the listed status_filter values
2. Tool name `get_tests_history` implies only historical data

### Fix
1. Rename tool from `get_tests_history` to `get_tests` in `data_server.py`
2. Rename function from `sb_get_tests_history` to `sb_get_tests` in `data_functions.py`
3. Add "running" to the `status_filter` values in the tool description
4. Update `CLAUDE.md` documentation (tool name + "running" status filter)
5. Update all test references
6. Add unit test for "running" status filtering

## Acceptance Criteria
1. Tool is named `get_tests` (renamed from `get_tests_history`)
2. Tool description lists "running" as a valid `status_filter` value
3. CLAUDE.md documents the new tool name and "running" as a supported status filter
4. Unit test exists for filtering tests by "running" status
5. All existing tests pass with updated references
