# SAF-30863: Context

## Status: Phase 6: PRD Created

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

### Full Rename Scope (from deep investigation)

**Source code (3 files):**
- `data_server.py`: tool name (line 54), wrapper function (line 64), import (line 19), call (line 77),
  description (line 56-62 — add "running")
- `data_functions.py`: function name (line 73)
- `__init__.py`: import + `__all__` export (lines 10, 18)

**Tests (3 files):**
- `test_data_functions.py`: 10 test method renames, 18 function call updates, 3 mock patches
- `test_timestamp_normalization.py`: class rename, 4 mock patches, 4 tool name lookups
- `test_e2e.py`: import, 2 function calls, 1 test method rename

**Utilities (1 file):**
- `tests/memory_profile_baseline.py`: import + 2 function calls

**Documentation (5 files):**
- `CLAUDE.md`: ~15 occurrences (tool name, examples, status filter docs)
- `README.md`: ~15 occurrences (mirrors CLAUDE.md)
- `DESIGN.md`: ~5 occurrences
- `E2E_TESTING.md`: 2 occurrences
- `tests/README.md`: 1 occurrence

**No cross-server references** — rename is fully isolated to the data server.

### Risk Assessment
- **Low risk for filter fix**: Business logic already works, cache-bypass already implemented
- **Low risk for rename**: No cross-server dependencies, HELM discovers tools dynamically via MCP,
  no external consumers reference the tool name directly

## Brainstorming: Chosen Approach

**Clean rename** — rename everything in one shot, no backward compatibility shim.
- No tech debt or deprecated code
- Single atomic change
- Safe because HELM discovers tools dynamically and no external consumers found
