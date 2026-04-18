# Ticket Context: SAF-29967

## Status
Phase 6: PRD Created

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

### 4. Studio Server Architecture (Deep Investigation)

#### Server Structure
- **Class**: `SafeBreachStudioServer(SafeBreachMCPBase)` — `studio_server.py:31`
- **Port**: 8004 — `start_all_servers.py:212`
- **9 existing tools** registered in `_register_tools()` — `studio_server.py:43-1024`
- **Tool pattern**: `@self.mcp.tool()` decorator → async wrapper → business logic in studio_functions.py
- **Response format**: Tools return **markdown strings** (not dicts) to MCP client
- **Error handling**: catch `ValueError` first (validation), then `Exception` (runtime)

#### `sb_run_studio_attack()` Reference (studio_functions.py:1054-1197)
- Validates attack_id > 0, requires either simulator IDs or all_connected=True
- Auth: `get_secret_for_console()`, `get_api_base_url(console, 'orchestrator')`,
  `get_api_account_id()`
- Headers: `x-apitoken`, `Content-Type: application/json`
- Endpoint: `POST /api/orch/v4/accounts/{account_id}/queue`
- Query params: `enableFeedbackLoop=true`, `retrySimulations=false`
- Payload: `{"plan": {"name": ..., "steps": [...], "draft": true}}`
- Response: Extract `data.planRunId`, `data.steps[0].stepRunId`
- Returns dict: `test_id`, `step_run_id`, `test_name`, `attack_id`, `status='queued'`

#### Studio Tool Registration Pattern (studio_server.py:525-616)
- `@self.mcp.tool(name="run_studio_attack", description="...")` — rich description
- Wraps `sb_run_studio_attack()` call
- Formats result as markdown string with sections: `## Attack Execution Queued`, etc.
- Single-tenant console auto-resolve inside wrapper
- Catches ValueError and Exception separately

#### Studio Caching
- `studio_draft_cache = SafeBreachCache(name="studio_drafts", maxsize=5, ttl=1800)`
- Cache key: `f"studio_draft_{console}_{result['draft_id']}"`
- Controlled by `is_caching_enabled("studio")`

#### Test Patterns (test_studio_functions.py:1417-1595)
- `TestRunStudioAttack` class with 7 test methods
- Mock decorators: `@patch` for `requests.post`, `get_api_account_id`,
  `get_api_base_url`, `get_secret_for_console`
- Mock response fixture: `{"data": {"planRunId": "...", "steps": [{"stepRunId": "..."}], ...}}`
- Tests: all_connected, specific simulators, custom name, invalid ID, empty list, API error,
  missing simulators

### 5. Environment Metadata
- `'orchestrator'` is a valid endpoint name for `get_api_base_url()`
- `'content-manager'` is a valid endpoint name for scenario API
- Account ID via `get_api_account_id(console)`
- Auth via `get_secret_for_console(console)`

### 6. Key Differences: Studio Attack vs Scenario Execution
- **Studio**: Builds single-step plan with `attacksFilter.playbook` for one attack ID +
  user-specified simulator filters
- **Scenario**: Uses the scenario's OWN multi-step plan with pre-configured filters in each step
  (attacksFilter, attackerFilter, targetFilter, systemFilter already defined)
- **Studio**: `draft: true` (Studio attacks are drafts)
- **Scenario**: `draft: false` likely needed (scenarios are published) — verify in E2E
- **Studio**: Needs simulator selection from user
- **Scenario**: Simulators already defined in step filters (ready-to-run)

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

## Brainstorm Results

### Chosen Approach: D — Pass-Through Relay with Phased Augmentation

**Design principle**: Fetch scenario payload as-is from API, validate readiness, relay unchanged
to the queue API. No field extraction, no transformation — just validation and relay.

**Phased evolution**:
1. **Phase A (current ticket)**: OOB ready-to-run Validate scenarios only
   - Fetch from content-manager API → validate `is_ready_to_run` → relay to queue API
2. **Phase B**: Custom plans (from plans API) — same pass-through pattern
3. **Phase C**: NOT ready-to-run scenarios — `compute_is_ready_to_run` returns diagnostic info
   (what's missing), tool accepts parameters to augment payload in-place, then relay

### Key Design Decisions

1. **`compute_is_ready_to_run` duplicated in Studio** (not imported from config_types):
   Studio's version will evolve to return diagnostic output (what's missing and how to fill it)
   to guide the LLM in future phases. Config's version stays as a simple boolean filter.

2. **Response format**: Summary — test_id + step count + first/last stepRunId

3. **Payload wrapping**: Exact structure TBD — waiting for user-provided sample payloads
   of qualified scenarios (with/without DAG) and the corresponding queue API request format.

### Alternatives Considered
- **Approach A (Thin Proxy)**: Forward raw steps + DAG metadata — risk of unknown fields
- **Approach B (Step Extraction)**: Extract only 4 queue-compatible fields — over-transforms
- **Approach C (Hybrid)**: DAG resolution + extraction — unnecessary complexity for Phase A

### Sample Payload Analysis (from user-provided curls)

#### Queue Status Check (GET)
- `GET /api/orch/v4/accounts/{account_id}/queue` — checks free slots
- Auth: `x-token` header (session JWT). MCP uses `x-apitoken` (API key) — both accepted.
- Useful for optional pre-flight validation

#### OOB Scenario Run (POST) — Full Payload Relay
```
POST /api/orch/v4/accounts/{account_id}/queue?enableFeedbackLoop=true&retrySimulations=true
Content-Type: application/json
```
Payload wraps the scenario inside `{"plan": {...}}`:
- `plan.name` — scenario name (from scenario payload)
- `plan.originalScenarioId` — UUID (references the OOB scenario)
- `plan.steps[]` — full step array with `name`, `uuid`, + all 4 filters
- `plan.actions[]` — DAG execution nodes (`multiAttack` + `wait` types)
- `plan.edges[]` — DAG edges (`{from, to}` pairs defining execution order)
- `plan.systemTags` — always `[]`
- **NO `draft` field** (unlike Studio's `draft: true`)

Key: For OOB, the ENTIRE scenario object is relayed as-is inside `plan`.

#### Custom Plan Run (POST) — Reference Only (RADICALLY DIFFERENT!)
```
POST /api/orch/v4/accounts/{account_id}/queue?enableFeedbackLoop=true&retrySimulations=true
```
Payload is minimal — just a reference:
- `plan.name` — plan name
- `plan.planId` — integer ID (server already has the full plan stored)
- `plan.systemTags` — always `[]`
- **NO steps, NO actions, NO edges** — server fetches them from the stored plan

#### Implications for Implementation
1. **OOB Phase A**: Fetch full scenario from content-manager API → relay inside `{"plan": scenario}`
   Fields to include: `name`, `originalScenarioId`, `steps`, `actions`, `edges`, `systemTags`
2. **Custom Phase B**: Only need `name`, `planId`, `systemTags` — trivially simple
3. **Non-ready Phase C**: Augment the payload with missing filter info before relay
4. Auth: Use `x-apitoken` header (MCP pattern), query params `enableFeedbackLoop=true`,
   `retrySimulations=true`
