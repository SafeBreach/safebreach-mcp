# Ticket Context: SAF-29966

## Status
Phase 6: PRD Created

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
- Confirmed: `x-apitoken` works with `/api/content-manager/vLatest/` endpoints (tested live)

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
- **Category join**: Categories are separate endpoint, need client-side join by integer ID
- **No account_id in path**: Scenario API uses `/api/content-manager/vLatest/scenarios` (no account_id)
- **Large scenario lists**: 443 scenarios on pentest01 — pagination essential
- **Null-safe handling**: `tags` and `description` can be null

## Real API Response Analysis (from pentest01 console)

### Scenario Object Fields
`id` (UUID), `name`, `description` (nullable), `createdBy`, `recommended` (bool),
`categories` (int[]), `tags` (str[] or null), `createdAt`, `updatedAt`,
`steps` (step objects), `order`, `actions`, `edges`, `phases`, `minApiVer`, `maxApiVer`

### Category Object Fields
`id` (int), `name`, `description`, `icon`, `scenarioIcon`, `cardBackGround`, `order`, `minApiVer`

### Data Volume
- 443 scenarios total (all `createdBy: "SafeBreach"` on this console, but field supports custom)
- 15 categories (static reference data)
- 6 recommended scenarios
- 206 scenarios with tags
- Steps per scenario: 0-16, avg 6.3
- 1 scenario has no steps

### Ready-to-Run Definition (confirmed with user)
A scenario is "ready to run" when ALL steps have BOTH `targetFilter` AND `attackerFilter`
with at least one key containing non-empty `values` arrays (e.g., `os`, `role`, `simulators`
with actual IDs). Empty `simulators.values: []` does NOT qualify.
- 4 of 443 are ready on pentest01
- targetFilter keys found: `os`, `simulators`
- attackerFilter keys found: `os`, `role`, `simulators`

### Step Structure
Each step has: `name`, `draft` (bool), `systemFilter`, `targetFilter`, `attackerFilter`,
`attacksFilter` (references attacks by `playbook` IDs or `tags` criteria)

### Proposed Filters
| Filter | Type | Field Source |
|--------|------|-------------|
| `name_filter` | Partial match (case-insensitive) | `name` |
| `creator_filter` | "safebreach"/"custom" | `createdBy` |
| `category_filter` | Category name partial match | `categories[]` → join |
| `recommended_filter` | Boolean | `recommended` |
| `tag_filter` | Partial match (case-insensitive) | `tags[]` |
| `ready_to_run_filter` | Boolean | computed from steps |

### Ordering Options
name (default), step_count, created_at, updated_at — asc/desc

## Implementation Pattern Details (Phase 4 Deep Dive)

### Config Server Tool Pattern
- Tools return `-> dict` (not str like Playbook)
- Functions are `async def`
- Single-tenant auto-resolve: check `if not safebreach_envs:` then override console name
- Import: `from safebreach_mcp_core.environments_metadata import get_console_name, safebreach_envs`

### Pagination Pattern (from playbook_types.py:561-600)
- 0-based page numbering, PAGE_SIZE=10
- Ceiling division: `total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE`
- Slice: `start = page * PAGE_SIZE`, `end = min(start + PAGE_SIZE, total)`
- Response keys: `page_number`, `total_pages`, `total_scenarios`, `scenarios_in_page`, `hint_to_agent`
- `hint_to_agent` = None on last page
- Invalid page returns `error` key with empty list

### Filtering Pattern (from playbook_types.py:369-497)
- Copy input list, chain sequential filters (AND logic)
- Case-insensitive partial match: `filter.lower() in item['name'].lower()`
- Use `.get()` for safe access
- `applied_filters` dict tracks only provided (non-default) filters

### Cache Pattern
- `scenarios_cache = SafeBreachCache(name="scenarios", maxsize=5, ttl=1800)`
- `categories_cache = SafeBreachCache(name="scenario_categories", maxsize=5, ttl=3600)`
- Check `is_caching_enabled("config")` before get/set
- Cache key: `f"scenarios_{console}"`, `f"categories_{console}"`

### Test Pattern (from config tests)
- `setup_method()`: clear caches
- `@pytest.fixture` for mock data matching API response structure
- `@patch()` decorators for `requests.get`, `get_secret_for_console`, `get_api_base_url`
- Config does NOT need `get_api_account_id` for scenarios (no account_id in path)
- Assert dict structure and pagination metadata

### Naming Convention (confirmed with user)
- **Tool input params**: snake_case (`name_filter`, `page_number`)
- **Pagination/metadata keys**: snake_case (`total_pages`, `hint_to_agent`, `applied_filters`)
- **Entity fields from API**: Preserve API names (`createdBy`, `createdAt`, `updatedAt`)
- **New computed fields**: snake_case (`step_count`, `is_ready_to_run`, `category_names`)

## Brainstorming Results

### Chosen Approach: Single API Call + Client-Side Everything (Approach A)
- Fetch all scenarios in one `/scenarios` call, cache full objects
- Categories fetched separately with dedicated cache (TTL=3600s)
- Filter, compute ready-to-run, join categories, paginate — all client-side
- `get_scenario_details` looks up by ID from cached list (free, no extra API call)
- Matches proven playbook server pattern exactly

### Key Design Decisions
1. **get_scenario_details returns full raw payload** (for future queue API use)
2. **get_scenarios list view is minimal**: step_count only, no step names
3. **Categories**: Separate cache, lazy-loaded, TTL=3600s
4. **Scenarios**: Cache full objects, TTL=1800s, maxsize=5
5. **is_ready_to_run computed from steps** during transform (not stored in API)
