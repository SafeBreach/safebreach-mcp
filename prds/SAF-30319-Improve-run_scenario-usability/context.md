# Ticket Context: SAF-30319

## Status
Phase 4: Investigation Complete

## Mode
Improving

## Original Ticket
- **Summary**: [safebreach-mcp] improve the run_scenario tool usability
- **Description**: Candid feedback from the in-console SafeBreach AI Agent (Helm) identifying 5 usability issues with the `run_scenario` MCP tool:
  1. Undocumented filter schema for `step_overrides` - inner filter structure not specified
  2. `default` key in `step_overrides` unreliable - silently fails for some steps
  3. Stale simulator UUIDs in `get_scenario_details` - no indication they're disconnected
  4. No attack count in scenario listing - must fetch full details to count
  5. Raw 400 errors from statistics API - not translated to actionable messages
- **Acceptance Criteria**: Not yet defined
- **Status**: To Do
- **Assignee**: Yossi Attas
- **Priority**: Medium

## Task Scope
Guided by ticket - investigate all 5 reported issues in the codebase and propose improvements

## Repositories Under Investigation
- /Users/yossiattas/Public/safebreach-mcp

## Investigation Findings

### Area 1: step_overrides filter schema documentation
- **Tool definition**: `studio_server.py:1042-1050`, implementation: `studio_functions.py:2238-2317`
- The docstring example at `studio_functions.py:2254-2269` is INCOMPLETE - missing `"name"` field
- The server help text at `studio_server.py:1118-1131` has correct examples with all three fields
  (`operator`, `values`, `name`) but these are in secondary help, not the primary parameter docs
- No validation of filter structure in `_apply_step_overrides()` (lines 1734-1758) - any structure accepted
- No documentation of valid operators (only "is" shown)

### Area 2: `default` key behavior in step_overrides
- Implementation: `studio_functions.py:2309-2317`
- "default" key is NOT documented in the tool description at all
- Applies only to steps identified as "missing" via `diagnose_scenario_readiness()` BEFORE overrides
- If a step is partially fixed by an explicit override (e.g., has attackerFilter but not targetFilter),
  the default does NOT fill in the missing piece
- No validation of default override content; empty `{}` silently expands

### Area 3: Stale simulator UUIDs in get_scenario_details
- Detail transform: `config_types.py:327-384`, extracts `simulators` from criteria at line 363-377
- Simulator UUIDs from scenario payload are returned as-is - NEVER cross-referenced with connected simulators
- No `is_connected` flag, no "stale" annotation, no alternative simulator suggestions
- Users can unknowingly use defunct UUIDs in step_overrides, causing runtime failures

### Area 4: Attack count in scenario listing
- Listing transform: `config_types.py:149-178`
- Returns `step_count` but NO attack count / `playbook_ids` / complexity metric
- `playbook_ids` are extracted in detail view (lines 334-359) but not in listing
- `order_by` supports `name, step_count, createdAt, updatedAt` but not attack count

### Area 5: Statistics API error handling
- Statistics call: `studio_functions.py:2144-2235`, called at lines 2330-2335
- `response.raise_for_status()` at line 2176 - raw exception propagates
- No try/except around the call, response body details LOST on 400 errors
- Server wrapper (`studio_server.py:1335-1340`) catches as generic Exception
- User sees: "Error running scenario: 400 Client Error: Bad Request for url: ..."
- Queue API (line 2475) HAS better error logging (`response.text`) but statistics API does not
- No pre-validation of filter structure before calling statistics API

## Problem Analysis

The `run_scenario` tool has 5 interconnected usability issues. Root cause: the tool was built for
internal API correctness but not for LLM-agent consumption, where clear documentation, pre-validation,
and actionable error messages are critical.

1. **Filter schema is a black box** (HIGH) - `step_overrides` requires `{operator, values, name}`
   but primary docstring example omits `name`. No validation - malformed filters fail at statistics API.
2. **`default` key undocumented with edge cases** (MEDIUM-HIGH) - Exists in code but not in docs.
   Only applies to "fully missing" steps, not partially-fixed ones.
3. **Stale simulator UUIDs** (HIGH) - `get_scenario_details` returns UUIDs without checking if connected.
   Agents reuse these, causing runtime failures.
4. **No attack count in listing** (MEDIUM) - Cannot filter/sort by complexity. Only `step_count` exposed.
5. **Opaque statistics API errors** (HIGH) - `raise_for_status()` without extracting response body.
   Generic "400 Client Error" with no actionable context.

Status: Phase 5 Complete - Approved by user

## Proposed Improvements
See summary.md for full proposed ticket content with acceptance criteria.
Status: Phase 6 Complete - Summary Created
