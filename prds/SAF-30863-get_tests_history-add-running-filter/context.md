# SAF-30863: Context

## Status: Phase 5: Problem Analysis Complete

## Ticket Info
- **Title**: HELM | Transparency - Assistant incorrectly reports no tests running due to tool limitations
- **Type**: Bug
- **Priority**: High
- **Assignee**: Yossi Attas
- **Reporter**: Hadas Cohen
- **Branch**: SAF-30863-get_tests_history-add-running-filter

## Task Scope
1. Add "running" as a supported `status_filter` value so HELM can directly filter for running tests
2. Rename `get_tests_history` to `get_tests` — the old name implies only historical/past tests,
   which is misleading now that it also returns running tests

## Investigation Findings

### Repository: safebreach-mcp

#### 1. data_server.py (Tool Registration) — Lines 60-61
- Tool description lists only: `'completed'/'canceled'/'failed'/None`
- **"running" is NOT mentioned** — this is the root cause. The AI agent reads this description to know valid values.

#### 2. data_functions.py (Business Logic) — Lines 73-189
- **Already supports "running"**: Line 93 docstring documents it, Lines 127-128 implement cache-bypass for running tests
- Client-side filtering (Lines 302-304): case-insensitive match against any status value
- No validation whitelist — accepts any status string

#### 3. data_types.py — No changes needed
- Status passes through unchanged from API

#### 4. Tests (test_data_functions.py)
- Lines 277-292: Tests exist for "completed" and "failed" filtering
- **No test for "running" status** — coverage gap

#### 5. CLAUDE.md — Line 390
- Documentation lists only three status values, omits "running"

## Problem Analysis

### Root Cause
The `get_tests_history` tool's **MCP tool description** in `data_server.py` does not list "running" as a valid `status_filter` value. Since AI agents rely on tool descriptions to understand available options, HELM doesn't know it can filter for running tests. The underlying business logic already handles "running" correctly (including cache-bypass).

### Affected Areas
1. **data_server.py**: Tool name (`get_tests_history` → `get_tests`) + add "running" to status_filter description
2. **data_functions.py**: Function name (`sb_get_tests_history` → `sb_get_tests`)
3. **CLAUDE.md**: Update all references to old tool/function name + add "running" status filter
4. **test_data_functions.py**: Update test references + add test for "running" filter
5. **test_integration.py**: Update any cross-server test references

### Risk Assessment
- **Low risk for filter fix**: Business logic already works, cache-bypass already implemented
- **Medium risk for rename**: Tool name change affects AI agent prompts that reference the old name.
  No external consumers beyond HELM, and HELM discovers tools dynamically via MCP, so the rename
  is transparent to it.
