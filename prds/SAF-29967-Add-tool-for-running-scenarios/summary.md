# Ticket Summary: SAF-29967

## Overview
**Mode**: Improving existing
**Project**: SAF
**Repositories**: safebreach-mcp
**Continuation of**: SAF-29966 (Scenario listing and detail tools)

---

## Current State
**Summary**: [safebreach-mcp] Add Studio MCP tool to allow Running an existing Validate scenario
which is labeled as ready to run
**Issues Identified**: No description or acceptance criteria defined. Title references "Studio MCP tool"
but scenarios live in the Config Server. Needs clear scope: which scenario types, what parameters,
what response format.

---

## Investigation Summary

### safebreach-mcp
- SAF-29966 implemented `get_scenarios` and `get_scenario_details` with full scenario caching,
  `is_ready_to_run` computation, and support for both OOB scenarios and custom plans
- The orchestrator queue API (`POST /api/orch/v4/accounts/{account_id}/queue`) is already used by
  the Studio server's `sb_run_studio_attack()` for running individual draft attacks
- The queue API accepts a `plan` object with `name`, `steps[]`, and `draft` flag
- Each step contains `attacksFilter`, `attackerFilter`, `targetFilter`, `systemFilter`
- Raw scenario objects (cached) contain the full step definitions needed for the queue payload
- `is_ready_to_run` already validates that all steps have both target and attacker filters
- Relevant files:
  - `safebreach_mcp_config/config_functions.py` (scenario fetch/cache, lines 350-611)
  - `safebreach_mcp_config/config_types.py` (transforms, is_ready_to_run, lines 92-452)
  - `safebreach_mcp_config/config_server.py` (tool registration, lines 26-180)
  - `safebreach_mcp_studio/studio_functions.py` (queue API reference, lines 1054-1197)
  - `safebreach_mcp_core/environments_metadata.py` (orchestrator endpoint, line 100)

---

## Problem Analysis

### Problem Description
AI agents can discover and inspect scenarios but cannot execute them. The queue API exists and is
proven (Studio uses it), but no MCP tool exposes scenario execution. Ready-to-run scenarios already
have all filter data needed — the tool just needs to forward the scenario's steps to the queue API.

### Impact Assessment
- Config Server: New business logic function + MCP tool (additive, no breaking changes)
- Reuses existing cached scenario data and authentication infrastructure
- Response includes `test_id` (planRunId) for tracking via Data Server's `get_test_details`

### Risks & Edge Cases
- Scenario references disconnected simulators: API handles gracefully (simulations get no-result)
- Multi-step DAG ordering: Queue API likely flattens steps; need to verify with E2E test
- Accidental re-runs: Tool should have clear naming and description to prevent unintended execution
- OOB vs custom plan payload differences: Both have steps with same filter structure

---

## Proposed Ticket Content

### Summary (Title)
[safebreach-mcp] Add `run_scenario` MCP tool to execute ready-to-run Validate scenarios

### Description

**Background**
SAF-29966 added scenario discovery and inspection tools (`get_scenarios`, `get_scenario_details`)
to the Config Server. The natural next step is enabling scenario execution — the "last mile" that
allows AI agents to trigger a full scenario run using the scenario's built-in simulator and attack
filters.

**Technical Context**
* The orchestrator queue API (`POST /api/orch/v4/accounts/{account_id}/queue`) is already proven
  via the Studio server's `sb_run_studio_attack()` function
* Raw scenario objects are cached in Config Server and contain full step definitions (attacksFilter,
  attackerFilter, targetFilter, systemFilter) needed for the queue payload
* `is_ready_to_run` is already computed for every scenario — validates all steps have both
  target and attacker filters with non-empty criteria
* Both OOB scenarios (UUID IDs) and custom plans (integer IDs) share the same step/filter structure

**Problem Description**
* AI agents can list and inspect scenarios but cannot execute them
* The queue API payload for scenarios mirrors the Studio pattern: wrap steps in a `plan` object
* Ready-to-run scenarios have all filter data pre-configured — no simulator selection needed
* The tool should reject non-ready scenarios before calling the API

**Affected Areas**
* `safebreach_mcp_config/config_functions.py`: New `sb_run_scenario()` function
* `safebreach_mcp_config/config_server.py`: New `run_scenario` MCP tool registration
* `safebreach_mcp_config/tests/`: Unit and E2E tests

### Acceptance Criteria

- [ ] `run_scenario` MCP tool accepts scenario_id (UUID or integer string) and console
- [ ] Tool validates scenario exists and `is_ready_to_run == True` before calling queue API
- [ ] Tool rejects scenarios that are not ready to run with a clear error message
- [ ] Scenario's steps are forwarded to `POST /api/orch/v4/accounts/{account_id}/queue`
  with the scenario's built-in filters preserved
- [ ] Response includes `test_id` (planRunId), `test_name`, and `status: queued`
- [ ] Supports both OOB scenarios and custom plans
- [ ] Optional `test_name` parameter (defaults to scenario name)
- [ ] Single-tenant console auto-resolve works
- [ ] Unit tests cover: validation, ready-to-run rejection, payload construction, API call,
  response parsing, error handling
- [ ] E2E test against pentest01 console confirms end-to-end execution
- [ ] All existing Config Server tests still pass
- [ ] CLAUDE.md updated with new tool documentation

### Suggested Labels/Components
- Component: safebreach-mcp-config
- Labels: mcp, scenario, execution

---

## Proposed Ticket Content

<!-- Markdown format for JIRA Cloud -->

**Description (Markdown for JIRA):**
```markdown
### Background
SAF-29966 added scenario discovery and inspection tools (`get_scenarios`, `get_scenario_details`)
to the Config Server. The natural next step is enabling scenario execution — the "last mile" that
allows AI agents to trigger a full scenario run using the scenario's built-in simulator and attack
filters.

### Technical Context
* The orchestrator queue API (`POST /api/orch/v4/accounts/{account_id}/queue`) is already proven
  via the Studio server's `sb_run_studio_attack()` function
* Raw scenario objects are cached in Config Server and contain full step definitions needed for
  the queue payload
* `is_ready_to_run` is already computed — validates all steps have both target and attacker filters
* Both OOB scenarios and custom plans share the same step/filter structure

### Problem Description
* AI agents can list and inspect scenarios but cannot execute them
* Ready-to-run scenarios have all filter data pre-configured — no simulator selection needed
* The tool should reject non-ready scenarios before calling the API

### Affected Areas
* `safebreach_mcp_config/config_functions.py`: New `sb_run_scenario()` function
* `safebreach_mcp_config/config_server.py`: New `run_scenario` MCP tool registration
* `safebreach_mcp_config/tests/`: Unit and E2E tests
```

**Acceptance Criteria:**
```markdown
* `run_scenario` MCP tool accepts scenario_id (UUID or integer string) and console
* Tool validates scenario exists and is_ready_to_run before calling queue API
* Tool rejects non-ready scenarios with clear error message
* Scenario's steps forwarded to orchestrator queue API with built-in filters preserved
* Response includes test_id (planRunId), test_name, and status: queued
* Supports both OOB scenarios and custom plans
* Optional test_name parameter (defaults to scenario name)
* Single-tenant console auto-resolve works
* Unit tests cover validation, rejection, payload, API call, response, errors
* E2E test confirms end-to-end execution on pentest01
* All existing Config Server tests still pass
* CLAUDE.md updated with new tool documentation
```
