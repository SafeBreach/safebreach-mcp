# Ticket Context: SAF-29966

## Status
Phase 6: Summary Created

## Mode
Improving

## Original Ticket
- **Summary**: [safebreach-mcp] Create tools to allow listing of all available scenarios and drilling in into a specific one
- **Description**: List of scenarios should indicate which are OOB vs custom, which are ready to run, how many attacks are included, and what category is each one in. A second tool should accept the scenario id as input and return a full payload of a scenario.
- **Status**: In Progress
- **Assignee**: Yossi Attas
- **Priority**: Medium

## Task Scope
Full investigation of codebase architecture and existing patterns to prepare for implementing two new MCP tools:
1. `get_scenarios` — List all available scenarios with OOB/custom indicator, ready-to-run status, attack count, and category
2. `get_scenario_details` — Get full scenario payload by ID

## API Endpoints
- `GET /api/content-manager/vLatest/scenarios` — Lists all scenarios
- `GET /api/content-manager/vLatest/scenarioCategories` — Lists scenario categories
- Authentication: `x-token` header (JWT)
- Base path: `/api/content-manager/vLatest/`

## Repositories Under Investigation
- /Users/yossiattas/Public/safebreach-mcp

## Investigation Findings

### Server Architecture & API Paths
Each server handles specific API base paths:
- **Config (8000)**: `/api/config/v1/` — Simulators
- **Data (8001)**: `/api/data/v1/` and `/api/siem/v1/` — Tests/simulations
- **Playbook (8003)**: `/api/kb/vLatest/` — Attack moves
- **Studio (8004)**: `/api/content/v1/` — Custom attack code

Scenario APIs use `/api/content-manager/vLatest/` — similar content domain as Studio.

### Implementation Patterns (from Playbook server reference)
- **types.py**: Transform API dicts → reduced/full output dicts, client-side filtering, pagination (PAGE_SIZE=10)
- **functions.py**: `requests.get()` with `x-apitoken` header, 120s timeout, optional `SafeBreachCache` (TTLCache)
- **server.py**: `@self.mcp.tool()` decorator, returns `str` (formatted text, not JSON), error wrapping
- **tests/**: `@patch()` mocking of `requests.get`, `get_secret_for_console`, `get_api_base_url`;
  `@pytest.fixture` for test data; class-based grouping with `setup_method`/`teardown_method`

### Auth Pattern
- Token: `get_secret_for_console(console)` → header `{"x-apitoken": token}`
- Base URL: `get_api_base_url(console, endpoint_type)` → e.g., `https://console.safebreach.com`
- Note: Scenario API uses `x-token` header (JWT), which differs from existing `x-apitoken` pattern

### Caching
- `SafeBreachCache(name=..., maxsize=..., ttl=...)` wrapper around `cachetools.TTLCache`
- Opt-in via env vars: `SB_MCP_CACHE_<SERVER>=true`
- Key format: `f"{type}_{console}"`, e.g., `"scenarios_demo"`

### Existing Scenario Code
- **None found** — this is a greenfield feature

### Server Placement Options
1. **Studio Server (8004)**: Closest domain (content), avoids new server complexity
2. **New Content-Manager Server (8005)**: Clean separation, new port

## Problem Analysis

### Problem Scope
Two new MCP tools needed in the Config Server to expose SafeBreach scenario management:
1. **`get_scenarios`** — List all scenarios with metadata (OOB/custom, ready-to-run, attack count, category)
2. **`get_scenario_details`** — Full scenario payload by ID

### API Integration
- **List endpoint**: `GET /api/content-manager/vLatest/scenarios`
- **Categories endpoint**: `GET /api/content-manager/vLatest/scenarioCategories`
- **Detail endpoint**: Likely `GET /api/content-manager/vLatest/scenarios/{id}` (TBD — may be in list payload)
- **Auth**: `x-apitoken` header (standard pattern, per user decision)
- **URL resolution**: `get_api_base_url(console, 'content-manager')` — no `account_id` in path

### Affected Areas
- `safebreach_mcp_config/config_types.py` — Add scenario transform functions
- `safebreach_mcp_config/config_functions.py` — Add scenario business logic, cache, API calls
- `safebreach_mcp_config/config_server.py` — Register two new MCP tools
- `safebreach_mcp_config/tests/` — Unit tests for all new code
- `safebreach_mcp_core/environments_metadata.py` — Add 'content-manager' to endpoint docs
- `CLAUDE.md` — Update tool documentation

### Key Design Decisions
1. **Server placement**: Config Server (8000) — user decision
2. **Auth method**: `x-apitoken` — matches existing pattern
3. **Caching**: Use existing `SB_MCP_CACHE_CONFIG` env var, new SafeBreachCache for scenarios
4. **Categories**: May need to join scenarios with categories endpoint, or categories may already
   be embedded in scenario response (need API response analysis)
5. **Pagination**: Follow existing PAGE_SIZE=10 pattern if scenario list is large

### Risks & Edge Cases
- **API response structure unknown**: Need actual API response to design transforms accurately
- **Category join**: If categories are separate, need to fetch both and join client-side
- **No account_id in path**: Scenario API may use different URL structure than config API
- **Large scenario lists**: May need pagination if response is large
- **OOB vs custom distinction**: Need to identify which field in API response indicates this

## Proposed Improvements
(Phase 6)
