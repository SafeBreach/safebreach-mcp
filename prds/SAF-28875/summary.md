# Ticket Summary: SAF-28875

## Overview
**Mode**: Improving existing
**Project**: SAF
**Repository**: safebreach-mcp

---

## Current State
**Summary**: [safebreach-mcp] MCP tools require the LLM to perform redundant conversions of ISO dates
**Issues Identified**: 4 Data Server tools (10 params) accept only epoch-ms timestamps, forcing LLMs
to call `convert_datetime_to_epoch` before every time-filtered query. Adds latency, wastes tokens, and
is error-prone.

---

## Investigation Summary

### safebreach-mcp
- `datetime_utils.py` already has `convert_datetime_to_epoch()` (ISO to epoch ms) and
  `convert_epoch_to_datetime()` (epoch to ISO with auto-detection at 10^12 threshold)
- `_normalize_numeric()` pattern in `data_functions.py` is a direct precedent for a normalizer helper
- FastMCP supports Union types (`str | int`) in tool parameter signatures
- Python 3.12+ (project requirement) supports `str | int` syntax natively
- Date-only strings ("2026-03-01") NOT supported by `datetime.fromisoformat()` — require time component
- Time range validation (`start <= end`) already compares numeric values — normalize before validating
- Relevant files:
  - `safebreach_mcp_core/datetime_utils.py` (conversion functions)
  - `safebreach_mcp_data/data_server.py` (tool wrappers, lines 56-77, 103-124, 332-355, 397-420)
  - `safebreach_mcp_data/data_functions.py` (business logic, _normalize_numeric at 40-52)

---

## Recommended Approach

Add a `normalize_timestamp()` function to `safebreach_mcp_core/datetime_utils.py` that accepts both
ISO 8601 strings and epoch integers, returning epoch milliseconds. Call it in `data_server.py` tool
wrappers to normalize parameters before passing to `data_functions.py`. Backend functions keep clean
`int`-only signatures.

The normalizer reuses existing `convert_datetime_to_epoch()` for ISO parsing and the `> 10^12`
threshold for seconds-vs-milliseconds auto-detection. String-numeric inputs (e.g., "1705314600") are
treated as epoch values (forgiving parsing).

### Key Decisions
- **Helper location**: `safebreach_mcp_core/datetime_utils.py` — shared, reusable across servers
- **Integration layer**: Normalize in `data_server.py` wrappers (Approach A) — cleanest separation
- **String-numeric handling**: Treat as epoch (forgiving) — practical for LLM interactions
- **Backward compatibility**: Not a concern — but both str and int accepted for flexibility

### Alternatives Considered
| Option | Description | Why Not Chosen |
|--------|-------------|----------------|
| Normalize in data_functions.py | Follow _normalize_numeric precedent exactly | Mixes type flexibility with business logic |
| Normalize at both layers | Belt-and-suspenders | Redundant, more code to maintain |
| String-only params | Simplest API, no Union types | Breaks epoch passthrough from tool responses |

---

## Proposed Ticket Content

### Summary (Title)
[safebreach-mcp] Accept ISO 8601 datetime strings in Data Server timestamp parameters

### Description

### Background
Data Server MCP tools accept only Unix epoch milliseconds for time-based filtering (10 parameters
across 4 tools). This forces LLMs to call `convert_datetime_to_epoch` (Utilities Server) before
every time-filtered query, adding round-trip latency, wasting tokens, and introducing error risk
(LLMs sometimes guess epoch values or confuse seconds vs milliseconds).

### Technical Context
* `datetime_utils.py` in `safebreach_mcp_core/` already provides `convert_datetime_to_epoch()` for
  ISO 8601 parsing and auto-detection logic for seconds vs milliseconds (threshold: 10^12)
* `_normalize_numeric()` in `data_functions.py` establishes the pattern for type-flexible helpers
* FastMCP and Python 3.12+ support `str | int` Union types in tool parameter signatures
* SafeBreach API always requires epoch milliseconds internally — normalization is transparent

### Proposed Approach
1. Add `normalize_timestamp(value) -> Optional[int]` to `safebreach_mcp_core/datetime_utils.py`
   - String input: parse as ISO 8601 via `convert_datetime_to_epoch()`, return epoch ms
   - String-numeric input (e.g., "1705314600"): parse as epoch with seconds/ms auto-detection
   - Integer input: apply seconds/ms auto-detection (> 10^12 = ms, else seconds * 1000)
   - None/invalid: return None
2. Change parameter types in `data_server.py` tool wrappers from `Optional[int]` to
   `Optional[str | int]` for all 10 timestamp parameters
3. Normalize in tool wrappers before calling `data_functions.py` — backend functions keep `int`-only
4. Update tool descriptions: document both formats accepted, remove "use convert_datetime_to_epoch" notes
5. Keep `convert_datetime_to_epoch` / `convert_epoch_to_datetime` utility tools available

### Affected Tools (Data Server, port 8001)
* `get_tests_history`: `start_date`, `end_date`
* `get_test_simulations`: `start_time`, `end_time`
* `get_simulation_result_drifts`: `window_start`, `window_end`, `look_back_time`
* `get_simulation_status_drifts`: `window_start`, `window_end`, `look_back_time`

### Acceptance Criteria

- [ ] `normalize_timestamp()` helper added to `safebreach_mcp_core/datetime_utils.py`
- [ ] All 10 timestamp parameters accept ISO 8601 strings (e.g., "2026-03-01T00:00:00Z",
  "2026-03-01T12:00:00+02:00")
- [ ] All 10 timestamp parameters continue to accept epoch integers (milliseconds and seconds)
- [ ] String-numeric inputs (e.g., "1705314600") treated as epoch values
- [ ] Tool descriptions updated to document both accepted formats
- [ ] "Use convert_datetime_to_epoch" notes removed from tool descriptions
- [ ] Invalid format inputs return clear error messages
- [ ] Unit tests cover: ISO string input, epoch integer input, string-numeric input, invalid input,
  None input, seconds-vs-ms auto-detection
- [ ] All existing unit and E2E tests continue to pass
- [ ] CLAUDE.md updated to reflect dual-format timestamp support

---

## JIRA-Ready Content

**Description (Markdown for JIRA):**
```markdown
### Background
Data Server MCP tools accept only Unix epoch milliseconds for time-based filtering (10 parameters
across 4 tools). This forces LLMs to call `convert_datetime_to_epoch` (Utilities Server) before
every time-filtered query, adding round-trip latency, wasting tokens, and introducing error risk
(LLMs sometimes guess epoch values or confuse seconds vs milliseconds).

### Technical Context
* `datetime_utils.py` already provides `convert_datetime_to_epoch()` for ISO 8601 parsing and
  auto-detection logic for seconds vs milliseconds (threshold: 10^12)
* `_normalize_numeric()` in `data_functions.py` establishes the pattern for type-flexible helpers
* FastMCP and Python 3.12+ support `str | int` Union types in tool parameter signatures
* SafeBreach API always requires epoch milliseconds internally — normalization is transparent

### Proposed Approach
1. Add `normalize_timestamp(value) -> Optional[int]` to `safebreach_mcp_core/datetime_utils.py`
   - String input: parse as ISO 8601, return epoch ms
   - String-numeric input: parse as epoch with seconds/ms auto-detection
   - Integer input: apply seconds/ms auto-detection (> 10^12 = ms, else seconds * 1000)
   - None/invalid: return None
2. Change parameter types in `data_server.py` from `Optional[int]` to `Optional[str | int]`
3. Normalize in tool wrappers — backend functions keep `int`-only signatures
4. Update tool descriptions: document both formats, remove "use convert_datetime_to_epoch" notes
5. Keep utility conversion tools available for standalone use

### Affected Tools (Data Server, port 8001)
* `get_tests_history`: `start_date`, `end_date`
* `get_test_simulations`: `start_time`, `end_time`
* `get_simulation_result_drifts`: `window_start`, `window_end`, `look_back_time`
* `get_simulation_status_drifts`: `window_start`, `window_end`, `look_back_time`

### Origin
Identified during LLM evaluation of drift analysis tools (SAF-28330 PR #27).
```

**Acceptance Criteria:**
```markdown
* `normalize_timestamp()` helper added to `safebreach_mcp_core/datetime_utils.py`
* All 10 timestamp parameters accept ISO 8601 strings
* All 10 timestamp parameters continue to accept epoch integers (ms and seconds)
* String-numeric inputs treated as epoch values
* Tool descriptions updated to document both formats
* "Use convert_datetime_to_epoch" notes removed from descriptions
* Invalid format inputs return clear error messages
* Unit tests cover ISO strings, epoch ints, string-numeric, invalid, None, seconds-vs-ms
* All existing unit and E2E tests pass
* CLAUDE.md updated
```
