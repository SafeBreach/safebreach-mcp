# Ticket Summary: SAF-30319

## Overview
**Mode**: Improving existing
**Project**: SAF
**Repositories**: safebreach-mcp

---

## Current State
**Summary**: [safebreach-mcp] improve the run_scenario tool usability
**Issues Identified**: The ticket contains excellent feedback from Helm (in-console AI agent) but lacks
structured acceptance criteria and technical scoping for implementation.

---

## Investigation Summary

### safebreach-mcp
- **step_overrides schema**: Primary docstring example missing `name` field; correct examples only in
  secondary help text. No validation of filter structure before API call.
  Files: `studio_server.py:1042-1131`, `studio_functions.py:2238-2317`
- **default key**: Implemented at `studio_functions.py:2309-2317` but not documented in tool description.
  Only applies to "fully missing" steps, not partially-fixed ones.
- **Stale simulator UUIDs**: `config_types.py:327-384` returns simulator UUIDs as-is from scenario payload.
  No cross-reference with connected simulators. No staleness annotation.
- **Attack count**: `config_types.py:149-178` listing returns `step_count` but no attack count.
  `playbook_ids` available in detail view (lines 334-359) but not in listing.
- **Statistics API errors**: `studio_functions.py:2175-2176` uses `raise_for_status()` without
  extracting response body. Queue API (line 2475) has better error handling pattern.

---

## Problem Analysis

### Problem Description
The `run_scenario` tool has 5 interconnected usability issues that compound into a poor agent experience.
The tool was built for API correctness but not for LLM-agent consumption, where clear documentation,
pre-validation, and actionable error messages are critical. Agents waste multiple dry-run iterations
discovering the correct filter format, use stale simulator IDs from scenario details, and get
unactionable error messages when things fail.

### Impact Assessment
- **Agent productivity**: 5+ dry-run iterations needed to discover correct filter format
- **Error debuggability**: Raw HTTP 400 errors give zero context for remediation
- **Data reliability**: Stale simulator UUIDs in scenario details mislead agents
- **Discoverability**: No attack count in listing forces per-scenario detail fetches

### Risks & Edge Cases
- Filter validation must not be overly strict - API may accept formats we don't document
- Attack count is non-deterministic for criteria-based scenarios (depends on runtime matching)
- Simulator cross-referencing adds an API call per scenario detail request
- Statistics API error body format may vary - needs defensive parsing

---

## Proposed Ticket Content

### Summary (Title)
[safebreach-mcp] Improve run_scenario tool usability: filter docs, error handling, and data enrichment

### Description

**Background**

The in-console SafeBreach AI Agent (Helm) reported 5 usability issues with the `run_scenario` MCP tool
that cause agents to waste multiple iterations discovering correct filter formats, unknowingly use stale
simulator IDs, and receive unactionable error messages.

**Technical Context**

* `step_overrides` filter schema requires `{operator, values, name}` nested structure but primary
  docstring omits the `name` field
* `default` key in `step_overrides` exists in code but is not documented in tool description
* `get_scenario_details` returns simulator UUIDs without cross-referencing connected simulators
* Scenario listing exposes `step_count` but not attack count or `playbook_ids`
* Statistics API pre-flight call uses `raise_for_status()` without extracting response body

**Problem Description**

* Agents build invalid filters based on incomplete documentation, causing 400 errors that take 5+
  iterations to resolve
* The `default` key only applies to "fully missing" steps, not partially-fixed ones, causing silent
  partial failures
* Stale simulator UUIDs from scenario details are naturally reused by agents in `step_overrides`,
  leading to cryptic runtime failures
* No way to filter/sort scenarios by attack count without fetching full details for each
* Statistics API errors surface as generic "400 Client Error: Bad Request" with no indication whether
  it's a filter format issue, stale UUID, invalid role, or permissions problem

**Affected Areas**

* `safebreach_mcp_studio/studio_server.py` - tool description, error handling wrapper
* `safebreach_mcp_studio/studio_functions.py` - step_overrides processing, statistics API call,
  default key logic
* `safebreach_mcp_config/config_types.py` - scenario listing/detail transforms
* `safebreach_mcp_config/config_functions.py` - scenario data retrieval

### Acceptance Criteria

- [ ] `step_overrides` parameter docs include complete filter schema examples with all three required
  fields (`operator`, `values`, `name`) in the primary tool description
- [ ] `step_overrides` docs include the `"default"` key feature with clear explanation of behavior
  and limitations
- [ ] Filter structure is validated before calling the statistics API, with clear error messages
  for malformed filters (missing `name`, invalid `operator`, wrong `values` type)
- [ ] `default` key applies to steps that are still missing filters AFTER explicit overrides are
  applied (not just before)
- [ ] `get_scenario_details` annotates simulator UUIDs with connection status
  (e.g., `is_connected: true/false`) by cross-referencing with `get_console_simulators`
- [ ] Scenario listing includes `total_attack_count` field aggregated from step playbook_ids
  (or "criteria-based" indicator for non-deterministic scenarios)
- [ ] Statistics API 400 errors extract and surface the response body with translated,
  actionable error messages
- [ ] Statistics API errors distinguish between: malformed filter, stale simulator UUID,
  invalid role value, and permissions issues
- [ ] All existing unit tests pass; new tests cover validation logic and error translation
- [ ] E2E test coverage for the improved error messages and filter validation

---

## Proposed Ticket Content

<!-- Markdown format for JIRA Cloud -->

**Description (Markdown for JIRA):**
```markdown
### Background

The in-console SafeBreach AI Agent (Helm) reported 5 usability issues with the `run_scenario` MCP tool
that cause agents to waste multiple iterations discovering correct filter formats, unknowingly use stale
simulator IDs, and receive unactionable error messages.

### Technical Context

* `step_overrides` filter schema requires `{operator, values, name}` nested structure but primary
  docstring omits the `name` field
* `default` key in `step_overrides` exists in code but is not documented in tool description
* `get_scenario_details` returns simulator UUIDs without cross-referencing connected simulators
* Scenario listing exposes `step_count` but not attack count or `playbook_ids`
* Statistics API pre-flight call uses `raise_for_status()` without extracting response body

### Problem Description

* Agents build invalid filters based on incomplete documentation, causing 400 errors that take 5+
  iterations to resolve
* The `default` key only applies to "fully missing" steps, not partially-fixed ones, causing silent
  partial failures
* Stale simulator UUIDs from scenario details are reused by agents in `step_overrides`,
  leading to cryptic runtime failures
* No way to filter/sort scenarios by attack count without fetching full details for each
* Statistics API errors surface as generic "400 Client Error: Bad Request" with no actionable context

### Affected Areas

* `safebreach_mcp_studio/` - tool description, error handling, step_overrides processing
* `safebreach_mcp_config/` - scenario listing/detail transforms
```

**Acceptance Criteria:**
```markdown
* step_overrides docs include complete filter schema examples with all three required fields
  (operator, values, name) in the primary tool description
* step_overrides docs include the "default" key feature with clear explanation
* Filter structure validated before statistics API call with clear error messages
* "default" key applies after explicit overrides (not just before)
* get_scenario_details annotates simulator UUIDs with connection status
* Scenario listing includes total_attack_count field
* Statistics API 400 errors extract response body with actionable error messages
* Statistics API errors distinguish malformed filter vs stale UUID vs invalid role vs permissions
* All existing tests pass; new tests cover validation and error translation
* E2E coverage for improved error messages and filter validation
```
