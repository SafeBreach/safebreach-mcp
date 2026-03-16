# ISO 8601 Timestamp Support for Data Server MCP Tools — SAF-28875

## 1. Overview

- **Task Type**: Refactor
- **Purpose**: Eliminate redundant `convert_datetime_to_epoch` tool calls that LLMs must make before
  every time-filtered Data Server query, reducing latency, token waste, and error risk
- **Target Consumer**: LLM agents using SafeBreach MCP tools (Claude Desktop, custom agents)
- **Key Benefits**:
  - Removes 1-2 extra tool calls per time-filtered query
  - Reduces token consumption and round-trip latency
  - Eliminates epoch value guessing and seconds/milliseconds confusion
- **Originating Request**: SAF-28875 (identified during LLM evaluation of SAF-28330 drift tools)

## 1.5. Document Status

| Field | Value |
|-------|-------|
| **PRD Status** | Complete |
| **Last Updated** | 2026-03-07 |
| **Owner** | Yossi Attas |
| **Current Phase** | N/A |

## 2. Solution Description

### Chosen Solution
Add a `normalize_timestamp(value)` function to `safebreach_mcp_core/datetime_utils.py` that accepts
ISO 8601 strings, epoch integers (seconds or milliseconds), and string-numeric values. Returns epoch
milliseconds or None. Call it in `data_server.py` tool wrappers to normalize parameters before passing
to `data_functions.py`. Backend functions keep clean `int`-only signatures.

The normalizer reuses existing `convert_datetime_to_epoch()` for ISO parsing and the `> 10^12`
threshold for seconds-vs-milliseconds auto-detection.

### Alternatives Considered

| Option | Description | Why Not Chosen |
|--------|-------------|----------------|
| Normalize in data_functions.py | Follow `_normalize_numeric` precedent, functions accept mixed types | Mixes type flexibility concerns with business logic |
| Normalize at both layers | Belt-and-suspenders in server + functions | Redundant code, more to maintain |
| String-only params | Change all params to `str`, accept only ISO 8601 | Breaks epoch passthrough from tool responses |

### Decision Rationale
Approach A (normalize in wrappers) provides the cleanest separation: `data_server.py` handles
MCP-facing type flexibility, `data_functions.py` handles business logic with guaranteed integer inputs.
The normalizer is tested once in `datetime_utils.py`, called in 4 tool wrappers.

## 3. Core Feature Components

### Component A: normalize_timestamp() Helper

- **Purpose**: New function in `safebreach_mcp_core/datetime_utils.py` — the single conversion entry point
- **Key Features**:
  - Accept `str`, `int`, `float`, or `None` input
  - ISO 8601 string parsing via existing `convert_datetime_to_epoch()`
  - String-numeric detection (try `float()` parse before ISO parse)
  - Seconds-vs-milliseconds auto-detection using `> 10^12` threshold
  - Return `Optional[int]` (epoch milliseconds) — None on invalid input
  - No exceptions raised — caller decides error handling

### Component B: Tool Wrapper Normalization

- **Purpose**: Modify 4 tool wrappers in `data_server.py` to normalize timestamp params before dispatch
- **Key Features**:
  - Change parameter type annotations from `Optional[int]` to `Optional[str | int]` (10 parameters)
  - Call `normalize_timestamp()` on each timestamp param at the top of each wrapper
  - Pass normalized `int` values to `data_functions.py` — no changes to backend signatures
  - Raise `ValueError` with clear message if normalization returns None for a required parameter

### Component C: Tool Description Updates

- **Purpose**: Update MCP tool descriptions so LLMs know they can pass ISO strings directly
- **Key Features**:
  - Document both accepted formats in parameter descriptions
  - Remove "Note: Use convert_datetime_to_epoch tool to get timestamps" guidance
  - Add examples: `"2026-03-01T00:00:00Z"` or `1709251200000`

## 6. Non-Functional Requirements

### Backward Compatibility
- Existing epoch integer callers (both seconds and milliseconds) continue to work unchanged
- `convert_datetime_to_epoch` / `convert_epoch_to_datetime` utility tools remain available
- No changes to `data_functions.py` function signatures — they still accept `Optional[int]`
- Config, Playbook, and Studio servers are unaffected (no timestamp parameters)

### Technical Constraints
- Python 3.12+ required (already enforced by `pyproject.toml`)
- `str | int` Union type syntax used natively (no `typing.Union` import needed)
- FastMCP supports Union types in tool parameter introspection

## 7. Definition of Done

- [x] `normalize_timestamp()` function added to `safebreach_mcp_core/datetime_utils.py`
- [x] All 10 timestamp parameters accept ISO 8601 strings
- [x] All 10 timestamp parameters accept epoch integers (seconds and milliseconds)
- [x] String-numeric inputs treated as epoch values with auto-detection
- [x] Invalid inputs return None (no exceptions from normalizer)
- [x] Tool descriptions updated to document both formats
- [x] "Use convert_datetime_to_epoch" notes removed from 4 tool descriptions
- [x] Unit tests for `normalize_timestamp()` cover all input types
- [x] Unit tests for tool wrappers cover ISO string passthrough
- [x] All existing 97+ data function tests pass (zero regressions)
- [x] All existing 89+ drift tool tests pass (zero regressions)
- [x] Cross-server test suite passes
- [x] CLAUDE.md updated to reflect dual-format timestamp support

## 8. Testing Strategy

### Unit Testing — normalize_timestamp()

**Scope**: The normalizer function in `datetime_utils.py`
**Framework**: pytest
**Location**: `safebreach_mcp_utilities/tests/test_utilities_server.py` (alongside existing datetime tests)

**Test cases**:
- ISO 8601 with Z suffix: `"2026-03-01T00:00:00Z"` → epoch ms
- ISO 8601 with offset: `"2026-03-01T12:00:00+02:00"` → epoch ms (UTC-adjusted)
- Epoch milliseconds (int): `1709251200000` → unchanged (passthrough)
- Epoch seconds (int): `1640995200` → `1640995200000` (multiplied by 1000)
- String-numeric (seconds): `"1640995200"` → `1640995200000`
- String-numeric (milliseconds): `"1709251200000"` → `1709251200000`
- Float input: `1640995200.5` → `1640995200500` (or `1640995200000`)
- None input: `None` → `None`
- Invalid string: `"not-a-date"` → `None`
- Empty string: `""` → `None`
- Boundary: `999999999999` (just below threshold) → `999999999999000`
- Boundary: `1000000000000` (at threshold) → `1000000000000` (unchanged)
- Round-trip: ISO string → normalize → should match `convert_datetime_to_epoch` output

### Unit Testing — Tool Wrapper Integration

**Scope**: Verify ISO strings flow through tool wrappers to backend functions
**Location**: `safebreach_mcp_data/tests/test_data_functions.py`

**Test cases** (per affected tool):
- Pass ISO string as start_date/start_time/window_start → verify backend receives epoch int
- Pass ISO string as end_date/end_time/window_end → verify backend receives epoch int
- Pass invalid string → verify ValueError raised with clear message
- Pass None → verify None passthrough (optional params)

### Regression Testing

**Scope**: All existing tests must pass unchanged
**Command**: `uv run pytest safebreach_mcp_data/tests/ safebreach_mcp_utilities/tests/ -v -m "not e2e"`

**Key regression areas**:
- Epoch integer passthrough (tests use seconds: `1640995200`)
- Drift tool epoch milliseconds (tests use: `1709251200000`)
- Range validation (`start > end` raises ValueError)
- String-to-int conversion in `_safe_time_compare()`
- Pagination with timestamp ordering

## 9. Implementation Phases

| Phase | Status | Completed | Commit SHA | Notes |
|-------|--------|-----------|------------|-------|
| Phase 1: normalize_timestamp() + Tests | ✅ Complete | 2026-03-07 | 604ce57 | |
| Phase 2: Tool Wrapper Integration + Tests | ✅ Complete | 2026-03-07 | - | |
| Phase 3: Documentation Updates | ✅ Complete | 2026-03-07 | - | |

### Phase 1: normalize_timestamp() Helper + Tests (TDD)

**Semantic Change**: Add the shared timestamp normalizer function and its test suite

**Deliverables**: `normalize_timestamp()` function with full unit test coverage

**Implementation Details**:

1. **TDD Step 1 — Write failing tests** in `safebreach_mcp_utilities/tests/test_utilities_server.py`:
   - Add a new test class `TestNormalizeTimestamp` with test methods for each input type:
     ISO 8601 strings (Z suffix, timezone offset), epoch milliseconds passthrough, epoch seconds
     conversion, string-numeric detection, None/invalid/empty inputs, boundary values at 10^12 threshold
   - Verify round-trip consistency with existing `convert_datetime_to_epoch()`
   - Run tests — all new tests should fail (function doesn't exist yet)

2. **TDD Step 2 — Implement** `normalize_timestamp(value: Any) -> Optional[int]` in
   `safebreach_mcp_core/datetime_utils.py`:
   - Accept any input type
   - If None: return None
   - If string: first try `float()` parse (string-numeric detection); if that succeeds, treat as
     epoch number and apply seconds/ms auto-detection; if `float()` fails, try
     `convert_datetime_to_epoch()` for ISO parsing; if both fail, return None
   - If int/float: apply seconds/ms auto-detection (`> 10^12` = ms, else multiply by 1000)
   - Always return int (milliseconds) or None

3. **TDD Step 3 — Run tests**: All normalize_timestamp tests pass. All existing datetime tests pass.

**Changes**:

| File | Change |
|------|--------|
| `safebreach_mcp_core/datetime_utils.py` | Add `normalize_timestamp()` function |
| `safebreach_mcp_utilities/tests/test_utilities_server.py` | Add `TestNormalizeTimestamp` test class |

**Test Plan**: Run `uv run pytest safebreach_mcp_utilities/tests/ -v` — all tests pass

**Git Commit**: `feat(core): add normalize_timestamp helper for ISO 8601 and epoch input (SAF-28875)`

---

### Phase 2: Tool Wrapper Integration + Tests (TDD)

**Semantic Change**: Wire normalize_timestamp into all 4 Data Server tool wrappers

**Deliverables**: All 10 timestamp parameters accept ISO 8601 strings via normalization in wrappers

**Implementation Details**:

1. **TDD Step 1 — Write failing tests** in `safebreach_mcp_data/tests/test_data_functions.py`:
   - Add tests that call each of the 4 tool-level functions with ISO 8601 string timestamps
   - For `get_tests_history`: pass `start_date="2024-01-01T00:00:00Z"`, verify it filters correctly
   - For `get_test_simulations`: pass `start_time="2024-01-01T00:00:00Z"`, verify filtering
   - For `get_simulation_result_drifts`: pass `window_start="2024-03-01T00:00:00Z"`,
     `window_end="2024-03-02T00:00:00Z"`, verify API payload built correctly
   - For `get_simulation_status_drifts`: same pattern as result drifts
   - Test invalid string input raises ValueError with descriptive message
   - Run tests — all new tests should fail (wrappers don't normalize yet)

2. **TDD Step 2 — Modify `data_server.py`** tool wrappers:
   - Import `normalize_timestamp` from `safebreach_mcp_core.datetime_utils`
   - In each of the 4 tool wrapper functions:
     - Change parameter type annotations from `Optional[int]` to `Optional[str | int]`
     - At the top of the function, normalize each timestamp parameter
     - For optional params: `normalized = normalize_timestamp(param) if param is not None else None`
     - For required params (window_start, window_end): normalize and raise ValueError if result is None
     - Pass normalized values to the `data_functions.py` call
   - **Important**: `data_functions.py` signatures remain unchanged (`Optional[int]`)

3. **TDD Step 3 — Run all tests**:
   - New ISO string tests pass
   - All existing 97+ data function tests pass (regression check)
   - All existing 89+ drift tool tests pass (regression check)

**Changes**:

| File | Change |
|------|--------|
| `safebreach_mcp_data/data_server.py` | Import normalizer; update 4 wrappers (types + normalization) |
| `safebreach_mcp_data/tests/test_data_functions.py` | Add ISO string integration tests |

**Test Plan**: Run `uv run pytest safebreach_mcp_data/tests/ -v -m "not e2e"` — all tests pass

**Git Commit**: `feat(data): accept ISO 8601 strings in all timestamp parameters (SAF-28875)`

---

### Phase 3: Documentation Updates

**Semantic Change**: Update tool descriptions and project documentation

**Deliverables**: Updated tool descriptions, CLAUDE.md, PRD status

**Implementation Details**:

1. **Update tool descriptions** in `data_server.py`:
   - For each of the 4 tools, update the description string:
     - Change "Unix timestamp in MILLISECONDS" to "Unix epoch timestamp (milliseconds or seconds) or
       ISO 8601 datetime string (e.g., '2026-03-01T00:00:00Z')"
     - Remove "Note: Use convert_datetime_to_epoch tool to get timestamps in the correct milliseconds
       format" from all 4 tools
     - Add brief note: "Accepts both epoch timestamps and ISO 8601 strings"

2. **Update CLAUDE.md**:
   - In the Filtering and Search Capabilities section, update timestamp parameter descriptions
   - Note that ISO 8601 strings are now accepted alongside epoch timestamps

3. **Update PRD status**:
   - Mark all phases as complete in the phase table
   - Update Definition of Done checkboxes

**Changes**:

| File | Change |
|------|--------|
| `safebreach_mcp_data/data_server.py` | Update 4 tool description strings |
| `CLAUDE.md` | Update timestamp parameter documentation |
| `prds/SAF-28875/prd.md` | Mark phases complete |

**Test Plan**: Run full cross-server test suite to verify no description parsing issues:
`uv run pytest safebreach_mcp_config/tests/ safebreach_mcp_data/tests/ safebreach_mcp_utilities/tests/ safebreach_mcp_playbook/tests/ -v -m "not e2e"`

**Git Commit**: `docs: update tool descriptions and CLAUDE.md for ISO timestamp support (SAF-28875)`

## 10. Risks and Assumptions

### Technical Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Two epoch scales (seconds vs ms) cause incorrect filtering | Medium | Auto-detection threshold (10^12) is well-tested; boundary tests included |
| String-numeric "1640995200" mistaken for invalid ISO | Low | Normalizer tries float() parse before ISO parse — numeric strings caught first |
| FastMCP schema generation with Union types | Low | Python 3.12+ Union syntax verified; FastMCP introspects natively |

### Assumptions
- LLMs will naturally provide ISO 8601 strings when users mention dates (validated during SAF-28330 evaluation)
- The `> 10^12` threshold correctly classifies all practical SafeBreach timestamps (post-2001 in ms,
  post-1970 through year 33658 in seconds)
- Existing epoch-only callers (tests, scripts) will not be affected since integer passthrough is preserved

## 11. Future Enhancements

- **Date-only string support**: Accept `"2026-03-01"` and auto-append `T00:00:00Z` — requires custom
  parsing beyond `datetime.fromisoformat()`
- **Relative time expressions**: Support `"7 days ago"`, `"last week"` — would reduce LLM computation
  further but adds parsing complexity
- **Apply to other servers**: If Config/Playbook/Studio servers add timestamp parameters, they can
  reuse `normalize_timestamp()` from the shared core

## 12. Executive Summary

- **Issue**: Data Server MCP tools require epoch-only timestamps, forcing LLMs to make redundant
  `convert_datetime_to_epoch` calls before every time-filtered query
- **What Was Built**: A shared `normalize_timestamp()` helper that auto-detects ISO 8601 strings,
  epoch seconds, and epoch milliseconds, integrated into all 4 Data Server tool wrappers
- **Key Technical Decisions**: Normalizer in shared core (`datetime_utils.py`), normalize at server
  wrapper layer (not in business logic), forgiving string-numeric parsing
- **Business Value**: Faster LLM interactions (fewer tool calls), reduced token usage, lower error
  rate from epoch guessing

## 14. Change Log

| Date | Change Description |
|------|-------------------|
| 2026-03-06 19:15 | PRD created — initial draft |
| 2026-03-07 | All 3 phases implemented and verified — PRD complete |
