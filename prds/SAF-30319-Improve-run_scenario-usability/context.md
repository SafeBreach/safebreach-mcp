# Ticket Context: SAF-30319

## Status
Phase 6: PRD Created

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

## Deep Investigation Findings (PRD Phase 4)

### Architecture: No Inter-Server Communication
- Studio and Config servers both call SafeBreach backend APIs independently
- Studio fetches scenarios from content-manager API (`studio_functions.py:1915-1937`)
- Studio fetches plans from config API (`studio_functions.py:1940-1965`)
- Studio calls orchestrator statistics API (`studio_functions.py:2144-2235`)
- No studio→config server dependency; enrichment must call backend APIs directly

### Issue 1: step_overrides - Complete Filter Schema
- **Valid filter structure**: `{filter_type: {operator: "is", values: [...], name: filter_type}}`
- **Valid filter types**: os, role, simulators, connection
- **Valid OS values**: WINDOWS, MAC, LINUX, DOCKER, NETWORK (target); WINDOWS, MAC, LINUX, DOCKER (attacker)
- **Valid role values**: isInfiltration, isExfiltration, isAWSAttacker, isAzureAttacker, isGCPAttacker,
  isWebApplicationAttacker
- **No filter validation**: `_apply_step_overrides()` at lines 1734-1758 just assigns filters directly
- **_has_real_filter_criteria()** at lines 1652-1669 checks structure but doesn't validate

### Issue 2: default key - No Test Coverage
- NO tests for "default" key expansion logic (confirmed)
- Tests exist for `_apply_step_overrides()` at lines 6360-6485 but not for default expansion
- The default applies to `diagnose_scenario_readiness()` missing_steps BEFORE explicit overrides
- Partially-ready steps (one filter present, one missing) don't get default applied

### Issue 3: Stale Simulator UUIDs - Cross-Server Enrichment Challenge
- Simulator API: `GET /api/config/v1/accounts/{id}/nodes?details=true&deleted=false`
- Each simulator has `isConnected` boolean
- Simulator cache: 1-hour TTL, scenario cache: 30-min TTL (can drift)
- `_simplify_step()` at config_types.py:327-384 extracts UUIDs verbatim
- No cross-reference function exists; would need separate API call

### Issue 4: Attack Count - Data Available at Listing Time (Lower Priority)
- Raw API response has `steps[].attacksFilter.playbook.values` (list of attack IDs)
- Could sum `len(step.attacksFilter.playbook.values)` across steps
- For criteria-based steps, count is indeterminate at listing time
- Backend API limitation: no guaranteed attack count without statistics call

### Issue 5: Statistics API Error Handling
- Statistics API: `raise_for_status()` at line 2176 with NO error body extraction
- Queue API: Better pattern at lines 2472-2481 (logs `response.text` before raising)
- Fix: Simply extract and propagate the extended error info from the API response body
  (same pattern as queue API). Constraint descriptions (lines 1969-2011) are separate -
  those are for dry-run diagnostics, NOT for HTTP 400 error translation.
- Other API calls (lines 1932, 1958) also use raw `raise_for_status()`
- Validation precedent: early ValueError with descriptive messages used elsewhere

### Existing Patterns to Follow
- **Error handling**: Tool wrappers catch ValueError (user input) + Exception (system)
- **Diagnostic responses**: Two-turn workflow returns `{'status': 'not_ready', 'diagnostic': {...}}`
  instead of raising (lines 2320-2328)
- **Recommendation system**: Phase/type/MITRE inference chain for filter suggestions (lines 1815-1912)
- **Constraint rendering**: Zero-sim steps get per-attack detail; partial steps get aggregated summary

Status: Phase 4 Complete (PRD Investigation)

## Brainstorming Results (Phase 5)

### Chosen Approaches

**Issue #1+#2: step_overrides docs + default key** → Approach C: Both
- Concise schema reference in tool description (valid types, structure template, default key)
- Detailed examples with all valid values in diagnostic `hint_to_agent` response
- Document "default" key behavior and limitations in both places

**Issue #3: Stale simulator UUIDs** → Deferred
- Will not be addressed in this ticket

**Issue #4: Attack count in listing** → Approach A + hint
- Add `total_attack_count` field to `get_reduced_scenario_mapping()`
- Sum `len(step.attacksFilter.playbook.values)` across steps
- Mark criteria-based steps as indeterminate
- Add conditional `hint_to_agent` explaining that accurate count can be determined via
  `run_scenario` with `dry_run=True`

**Issue #5: Statistics API errors** → Approach A: Mirror queue API
- Log `response.text` before `raise_for_status()` (same pattern as queue API lines 2472-2481)
- Wrap in try/except, include response body in error message propagated to user
- Apply same pattern to other API calls that use raw `raise_for_status()` (lines 1932, 1958)

Status: Phase 5 Complete - Approaches approved by user

## Proposed Improvements
See summary.md for full proposed ticket content with acceptance criteria.
Status: Phase 6 Complete - Summary Created
