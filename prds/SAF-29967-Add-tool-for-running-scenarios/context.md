# Ticket Context: SAF-29967

## Status
Phase 3: Create Working Branch and PRD Context

## JIRA Ticket
- **Summary**: [safebreach-mcp] Add `run_scenario` MCP tool to execute ready-to-run Validate scenarios
- **Status**: To Do
- **Assignee**: Yossi Attas
- **Sprint**: SAF Sprint 87
- **Team**: AI Tools
- **Offering**: Validate
- **Linked**: SAF-29859 (MCP: Support basic actions for AI Agent, part 1)
- **Continuation of**: SAF-29966 (Scenario listing and detail tools — complete, 9 phases)

## Clarified Requirements

### Server Placement
- **Studio MCP Server** (not Config Server) — the tool lives alongside `sb_run_studio_attack()`
- Studio already has the orchestrator queue API integration pattern

### Scenario Data Fetching
- **Direct API fetch** from Studio Server — no cross-server calls to Config Server
- Studio will independently fetch scenario data from SafeBreach API

### Phased Implementation
1. **Phase A**: OOB Validate scenarios only (SafeBreach-published, ready-to-run)
2. **Phase B**: Custom plans support (after automated E2E sign-off of Phase A)
3. **Phase C**: Propagate scenario type support (separate implementation phase)

Each phase boundary requires passing automated E2E tests before proceeding.

### Scope
- Both OOB scenarios and custom plans supported (phased)
- Both Validate and Propagate types supported (phased)
- Scenarios must be `is_ready_to_run == True` to execute
- Uses scenario's built-in filters (no simulator override needed)

## Investigation Findings (from preparing-ticket)

### 1. Predecessor PRD (SAF-29966)
- **PRD Location**: `prds/SAF-29966-create-tool-to-list-scenarios/prd.md`
- SAF-29966 implemented `get_scenarios` and `get_scenario_details` in the Config Server
- Future enhancement explicitly listed: "Run scenario via queue API"
- `is_ready_to_run` field already computed — checks ALL steps have both targetFilter AND
  attackerFilter with non-empty criteria values
- Full scenario payloads are cached (scenarios_cache, maxsize=5, TTL=1800s)

### 2. Scenario API Endpoints
- OOB Scenarios: `GET /api/content-manager/vLatest/scenarios` (content-manager service)
- Custom Plans: `GET /api/config/v2/accounts/{account_id}/plans?details=true` (config service)
- Categories: `GET /api/content-manager/vLatest/scenarioCategories`

### 3. Orchestrator Queue API (Reference: studio_functions.py)
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

### 4. Studio Server Patterns
- Tools registered via `@self.mcp.tool()` decorator in `_register_tools()`
- Single-tenant console auto-resolve pattern used in all tools
- Functions return dict, server wraps with async def
- Error handling: try/except with error dict return

### 5. Environment Metadata
- `'orchestrator'` is a valid endpoint name for `get_api_base_url()`
- `'content-manager'` is a valid endpoint name for scenario API
- Account ID via `get_api_account_id(console)`
- Auth via `get_secret_for_console(console)`

## Problem Analysis

### Problem Description
AI agents can discover scenarios (`get_scenarios`) and inspect them (`get_scenario_details`) but
cannot execute them. The orchestrator queue API exists and is already used by the Studio server for
running individual draft attacks, but no tool exposes scenario execution. This is the "last mile" —
allowing agents to trigger a full multi-step scenario run using the scenario's built-in filters.

### Impact Assessment
- **Studio Server**: New `run_scenario` function + MCP tool registration + scenario API fetch
- **Queue API integration**: POST to `/api/orch/v4/accounts/{account_id}/queue` with scenario steps
- **Data flow**: Fetch raw scenarios from API, validate ready-to-run, forward steps to queue

### Risks & Edge Cases
- Scenario's step filters may reference disconnected simulators → API will handle gracefully
- OOB scenarios vs custom plans may need different payload construction
- Multi-step scenarios have DAG ordering (actions/edges) — queue API may or may not need this
- `is_ready_to_run=False` scenarios must be rejected before API call
- Rate limiting / accidental re-runs — tool should have clear confirmation semantics
