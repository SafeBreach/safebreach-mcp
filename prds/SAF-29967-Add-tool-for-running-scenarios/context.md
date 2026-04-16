# Ticket Context: SAF-29967

## Status
Phase 6: Summary Created

## Mode
Improving

## Original Ticket
- **Summary**: [safebreach-mcp] Add Studio MCP tool to allow Running an existing Validate scenario
  which is labeled as ready to run
- **Description**: No description provided
- **Acceptance Criteria**: TBD
- **Status**: To Do
- **Continuation of**: SAF-29966 (Scenario listing and detail tools — complete, 9 phases)

## Task Scope
Add an MCP tool for running/executing an existing Validate scenario that is marked as ready-to-run.
This extends the scenario listing (`get_scenarios`) and detail (`get_scenario_details`) tools from
SAF-29966 with the ability to actually trigger scenario execution via the queue API.

## Repositories Under Investigation
- /Users/yossiattas/Public/safebreach-mcp

## Investigation Findings

### safebreach-mcp

#### 1. Predecessor PRD (SAF-29966)
- **PRD Location**: `prds/SAF-29966-create-tool-to-list-scenarios/prd.md`
- SAF-29966 implemented `get_scenarios` and `get_scenario_details` in the Config Server
- Future enhancement explicitly listed: "Run scenario via queue API"
- `is_ready_to_run` field already computed — checks ALL steps have both targetFilter AND attackerFilter
  with non-empty criteria values
- Full scenario payloads are cached (scenarios_cache, maxsize=5, TTL=1800s)
- Categories resolved via separate endpoint and cache

#### 2. Existing Scenario Infrastructure (config_functions.py)
- OOB Scenarios: `GET /api/content-manager/vLatest/scenarios` (content-manager service)
- Custom Plans: `GET /api/config/v2/accounts/{account_id}/plans?details=true` (config service)
- Categories: `GET /api/content-manager/vLatest/scenarioCategories`
- `sb_get_scenarios()` orchestrates fetch, transform, filter, paginate
- `sb_get_scenario_details()` looks up from cached list, returns full payload with category_names

#### 3. Orchestrator Queue API (Reference: studio_functions.py)
- **Endpoint**: `POST /api/orch/v4/accounts/{account_id}/queue`
- **Base URL service**: `'orchestrator'`
- **Query params**: `enableFeedbackLoop`, `retrySimulations`
- **Payload structure**:
  ```json
  {
    "plan": {
      "name": "Test Name",
      "steps": [{
        "attacksFilter": {...},
        "attackerFilter": {...},
        "targetFilter": {...},
        "systemFilter": {}
      }],
      "draft": true
    }
  }
  ```
- **Response**: `planRunId` (test_id), `stepRunId`, `name`, status
- Studio's `sb_run_studio_attack()` is the closest reference implementation

#### 4. Config Server Patterns (config_server.py)
- Tools registered via `@self.mcp.tool()` decorator in `_register_tools()`
- Single-tenant console auto-resolve pattern used in all tools
- Functions return dict, server wraps with async def
- Error handling: try/except with error dict return

#### 5. Environment Metadata (environments_metadata.py)
- `'orchestrator'` is a valid endpoint name for `get_api_base_url()`
- Account ID via `get_api_account_id(console)`
- Auth via `get_secret_for_console(console)`

#### 6. Test Patterns (test_config_functions.py)
- `@patch` decorators for `requests.get`/`requests.post`, `get_secret_for_console`,
  `get_api_base_url`, `get_api_account_id`
- Cache clearing in setup_method/teardown_method
- Mock response objects with `.json()` and `.raise_for_status()`
- E2E tests in separate file with `@pytest.mark.e2e` and `@skip_e2e`

## Problem Analysis

### Problem Description
AI agents can discover scenarios (`get_scenarios`) and inspect them (`get_scenario_details`) but
cannot execute them. The orchestrator queue API exists and is already used by the Studio server for
running individual draft attacks, but no tool exposes scenario execution. This is the "last mile" —
allowing agents to trigger a full multi-step scenario run using the scenario's built-in filters.

### Impact Assessment
- **Config Server**: New `run_scenario` function + MCP tool registration
- **Queue API integration**: POST to `/api/orch/v4/accounts/{account_id}/queue` with scenario steps
- **Data flow**: Reuses cached raw scenarios (not simplified detail view) to extract full step payload

### Risks & Edge Cases
- Scenario's step filters may reference disconnected simulators → API will handle gracefully
- OOB scenarios vs custom plans may need different payload construction
- Multi-step scenarios have DAG ordering (actions/edges) — queue API may or may not need this
- `is_ready_to_run=False` scenarios must be rejected before API call
- Rate limiting / accidental re-runs — tool should have clear confirmation semantics

## Proposed Improvements
(Phase 6 — see summary.md)
