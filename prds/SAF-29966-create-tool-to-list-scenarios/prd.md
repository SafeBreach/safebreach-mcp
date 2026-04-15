# Scenario Listing and Detail Tools for Config Server — SAF-29966

## 1. Overview

| Field | Value |
|-------|-------|
| **Task Type** | Feature |
| **Purpose** | Enable AI agents to discover and inspect SafeBreach scenarios via MCP tools |
| **Target Consumer** | AI agents (Claude, etc.) interacting with SafeBreach via MCP protocol |
| **Key Benefits** | 1) Scenario discovery with filtering and pagination 2) Full scenario payload for inspection and future queue API integration 3) Ready-to-run status visibility |
| **Business Alignment** | Extends SafeBreach MCP coverage to scenario management, completing the AI-driven workflow |
| **Originating Request** | [SAF-29966](https://safebreach.atlassian.net/browse/SAF-29966) |

## 1.5. Document Status

| Field | Value |
|-------|-------|
| **PRD Status** | Draft |
| **Last Updated** | 2026-04-14 18:30 |
| **Owner** | Yossi Attas |
| **Current Phase** | N/A |

## 2. Solution Description

### Chosen Solution
Single API call with client-side filtering, pagination, and category join.
Fetch all scenarios from `GET /api/content-manager/vLatest/scenarios` in one call,
cache full objects, and perform all filtering, ordering, and pagination client-side.
Categories are fetched from a separate endpoint and cached independently.
`get_scenario_details` performs a lookup by ID from the cached scenario list.

This approach mirrors the proven Playbook Server pattern, keeping implementation
simple, consistent, and maintainable.

### Alternatives Considered

**Approach B: Reduced Cache + API Details on Demand**
- Cache only transformed reduced objects for the list view
- Hit the API for every `get_scenario_details` call
- Pros: Lower memory footprint (~500KB vs ~3MB per console)
- Cons: Extra API call per detail request; `is_ready_to_run` must be precomputed during
  initial transform since step data is discarded; inconsistent with existing patterns

**Approach C: Dual Cache (Reduced + Full)**
- Maintain separate caches for reduced list and full objects
- Pros: Both tools served from cache; fastest responses
- Cons: Higher memory; more complex cache management; no real benefit over
  Approach A since full objects are needed for `is_ready_to_run` computation anyway

### Decision Rationale
Approach A wins because `is_ready_to_run` requires step data regardless, making memory
savings from Approach B illusory. Memory is trivial (443 scenarios ~3MB vs Playbook's
4600+ attacks already cached similarly). Approach A also enables `get_scenario_details`
for free from the cached list, and the full payload stays cached for future queue API use.

## 3. Core Feature Components

### Component A: Scenario Data Transforms (`config_types.py`)

**Purpose**: Transform raw API scenario objects into reduced list view and compute derived fields.
New functions added to the existing `config_types.py`.

**Key Features**:
- `get_reduced_scenario_mapping(scenario, categories_map)` — Transforms a full scenario object
  into a reduced representation for list view. Includes: `id`, `name`, `description` (truncated
  to 200 chars), `createdBy`, `recommended`, `category_names` (resolved from categories_map),
  `tags`, `step_count`, `is_ready_to_run`, `createdAt`, `updatedAt`
- `compute_is_ready_to_run(scenario)` — Evaluates whether ALL steps have BOTH `targetFilter`
  AND `attackerFilter` with at least one key containing non-empty `values` arrays. Returns bool.
- `filter_scenarios_by_criteria(scenarios, ...)` — Applies all 6 filters using AND logic:
  name (partial), creator (safebreach/custom), category (partial on resolved names),
  recommended (bool), tag (partial), ready_to_run (bool)
- `apply_scenario_ordering(scenarios, order_by, order_direction)` — Sorts by name, step_count,
  createdAt, or updatedAt in asc/desc order
- `paginate_scenarios(scenarios, page_number, page_size)` — Returns paginated dict with
  `page_number`, `total_pages`, `total_scenarios`, `scenarios_in_page`, `hint_to_agent`

### Component B: Scenario Business Logic (`config_functions.py`)

**Purpose**: API integration, caching, and orchestration for scenario operations.
New functions added to the existing `config_functions.py`.

**Key Features**:
- `scenarios_cache` — `SafeBreachCache(name="scenarios", maxsize=5, ttl=1800)` for full
  scenario objects per console
- `categories_cache` — `SafeBreachCache(name="scenario_categories", maxsize=5, ttl=3600)`
  for category reference data per console
- `_get_all_scenarios_from_cache_or_api(console)` — Fetches all scenarios from
  `GET {base_url}/api/content-manager/vLatest/scenarios` with `x-apitoken` header.
  Caches full response list. Returns `List[Dict]`.
- `_get_categories_map_from_cache_or_api(console)` — Fetches categories from
  `GET {base_url}/api/content-manager/vLatest/scenarioCategories` with `x-apitoken` header.
  Returns `Dict[int, str]` mapping category ID to name. Cached separately with longer TTL.
- `sb_get_scenarios(console, page_number, name_filter, creator_filter, category_filter,
  recommended_filter, tag_filter, ready_to_run_filter, order_by, order_direction)` —
  Main orchestration: fetch scenarios + categories, transform to reduced view, apply filters,
  order, paginate, return result dict with `applied_filters` and `hint_to_agent`.
- `sb_get_scenario_details(scenario_id, console)` — Lookup scenario by UUID from cached list.
  Returns full raw scenario object with `category_names` resolved. Raises `ValueError` if not found.
- `clear_scenarios_cache()` / `clear_categories_cache()` — Cache clearing for tests.

### Component C: MCP Tool Registration (`config_server.py`)

**Purpose**: Register `get_scenarios` and `get_scenario_details` as MCP tools.
New tool registrations added to the existing `_register_tools()` method.

**Key Features**:
- `get_scenarios` tool — `async def` returning `-> dict`. Includes single-tenant console
  auto-resolve. Rich description documenting all parameters for Claude.
- `get_scenario_details` tool — `async def` returning `-> dict`. Accepts `scenario_id` (UUID
  string) and `console`. Single-tenant auto-resolve.

### Component D: Unit Tests

**Purpose**: Comprehensive test coverage for all new scenario functionality.

**Key Features**:
- `test_config_types.py` — Tests for `get_reduced_scenario_mapping`, `compute_is_ready_to_run`,
  `filter_scenarios_by_criteria`, `apply_scenario_ordering`, `paginate_scenarios`
- `test_config_functions.py` — Tests for `_get_all_scenarios_from_cache_or_api`,
  `_get_categories_map_from_cache_or_api`, `sb_get_scenarios`, `sb_get_scenario_details`
  with mocked API responses, cache behavior, error handling

## 4. API Endpoints and Integration

### Existing APIs to Consume

**Scenarios List API**:
- **URL**: `GET /api/content-manager/vLatest/scenarios`
- **Headers**: `x-apitoken: {token}`, `Content-Type: application/json`
- **Response**: JSON array of scenario objects. Each object contains:
  `id` (UUID string), `name`, `description` (nullable), `createdBy`,
  `recommended` (bool), `categories` (int[]), `tags` (string[] or null),
  `createdAt`, `updatedAt`, `steps` (array of step objects with
  `name`, `draft`, `systemFilter`, `targetFilter`, `attackerFilter`, `attacksFilter`),
  `order`, `actions`, `edges`, `phases`, `minApiVer`, `maxApiVer`

**Scenario Categories API**:
- **URL**: `GET /api/content-manager/vLatest/scenarioCategories`
- **Headers**: `x-apitoken: {token}`, `Content-Type: application/json`
- **Response**: JSON array of category objects. Each object contains:
  `id` (int), `name`, `description`, `icon`, `scenarioIcon`,
  `cardBackGround`, `order`, `minApiVer`

**Base URL Resolution**:
- Multi-tenant: `get_api_base_url(console, 'content-manager')` resolves to console URL
- Single-tenant: Falls back to `CONTENT_MANAGER_URL` env var or console config URL
- No `account_id` in the URL path (unlike Config's simulator API)

## 5. Example Customer Flow

_Omitted — backend-only MCP tool changes, no UI workflow._

## 6. Non-Functional Requirements

### Technical Constraints
- **Integration**: Config Server (port 8000) — extends existing `SafeBreachConfigServer` class
- **Technology Stack**: Python 3.12+, `requests` library, `SafeBreachCache` (cachetools)
- **Backward Compatibility**: No breaking changes — additive only (two new tools)
- **Caching**: Controlled by existing `SB_MCP_CACHE_CONFIG` env var

### Performance Requirements
- **Response Times**: List endpoint under 2s (cached), under 10s (cold API call for 443 scenarios)
- **Memory**: ~3MB per cached console (full scenario objects), max 5 consoles = ~15MB
- **Category Cache**: ~10KB per console (15 categories), negligible

## 7. Definition of Done

**Core Functionality**:
- [ ] `get_scenarios` returns paginated, filtered scenario list
- [ ] `get_scenario_details` returns full raw scenario payload by UUID
- [ ] Category names resolved from separate API endpoint
- [ ] `is_ready_to_run` computed correctly per the agreed definition
- [ ] All 6 filters work correctly in combination (AND logic)
- [ ] Ordering works for all 4 fields in both directions
- [ ] Pagination with `hint_to_agent` works correctly
- [ ] Single-tenant mode auto-resolve works for both tools
- [ ] Caching controlled by `SB_MCP_CACHE_CONFIG` env var

**Quality Gates**:
- [ ] Unit tests cover: transforms, filtering, pagination, ready-to-run, category join, caching, errors
- [ ] All existing Config Server tests still pass
- [ ] No regressions in other servers' test suites

**Documentation**:
- [ ] `CLAUDE.md` updated with new tool documentation

## 8. Testing Strategy

### Unit Testing
- **Framework**: pytest with `unittest.mock`
- **Scope**:
  - `config_types.py`: Transform functions, `compute_is_ready_to_run` (edge cases: no steps,
    empty filters, mixed filter types), filtering (each filter individually + combinations),
    ordering (each field + direction), pagination (first/middle/last/invalid pages)
  - `config_functions.py`: API call mocking (success, HTTP errors, malformed responses),
    cache hit/miss behavior, category fetching and map building,
    `sb_get_scenarios` full orchestration, `sb_get_scenario_details` found/not-found
- **Mocking**: `@patch()` for `requests.get`, `get_secret_for_console`, `get_api_base_url`
- **Fixtures**: Mock scenario data matching real API response structure,
  mock category data, pre-built categories map

### Integration Testing
- E2E tests (marked `@pytest.mark.e2e`) that call real SafeBreach API
  on pentest01 console — deferred to separate E2E test pass

## 9. Implementation Phases

| Phase | Status | Completed | Commit SHA | Notes |
|-------|--------|-----------|------------|-------|
| Phase 1: RED — Types Tests | ⏳ Pending | - | - | Write tests first (all fail) |
| Phase 2: GREEN — Types Implementation | ⏳ Pending | - | - | Implement to make tests pass |
| Phase 3: RED — Functions Tests | ⏳ Pending | - | - | Write tests first (all fail) |
| Phase 4: GREEN — Functions Implementation | ⏳ Pending | - | - | Implement to make tests pass |
| Phase 5: MCP Tool Registration | ⏳ Pending | - | - | |
| Phase 6: RED/GREEN — E2E Tests | ⏳ Pending | - | - | Against pentest01 console |
| Phase 7: Documentation | ⏳ Pending | - | - | |

### Phase 1: RED — Types Tests

**Semantic Change**: Write all unit tests for scenario transform, filter, ordering, and
pagination functions. All tests will fail (RED) because the functions don't exist yet.

**Deliverables**: Complete test suite for `config_types.py` scenario functions.

**Implementation Details**:

1. **Test `compute_is_ready_to_run`** — `TestComputeIsReadyToRun` class
   - Scenario with all steps having real OS/role criteria → `True`
   - Scenario with steps having empty `simulators.values: []` only → `False`
   - Scenario with no steps → `False`
   - Scenario with mixed steps (some ready, some not) → `False`
   - Scenario with one step having targetFilter but no attackerFilter → `False`

2. **Test `get_reduced_scenario_mapping`** — `TestGetReducedScenarioMapping` class
   - Verify all expected keys are present in output
   - Verify `description` truncation at 200 chars
   - Verify `category_names` resolved correctly from map
   - Verify `step_count` computed correctly
   - Verify `is_ready_to_run` computed correctly
   - Verify null `tags` and `description` handled safely

3. **Test `filter_scenarios_by_criteria`** — `TestFilterScenariosByCriteria` class
   - Each filter individually with matching and non-matching data
   - Combined filters (AND logic)
   - `creator_filter`: "safebreach" matches "SafeBreach" (case-insensitive)
   - `creator_filter`: "custom" excludes "SafeBreach"
   - `tag_filter` with null tags scenarios
   - `category_filter` partial matching on resolved names
   - Empty filter set returns all scenarios

4. **Test `apply_scenario_ordering`** — `TestApplyScenarioOrdering` class
   - Each order_by field in asc and desc
   - Case-insensitive name ordering

5. **Test `paginate_scenarios`** — `TestPaginateScenarios` class
   - First page, middle page, last page
   - Invalid page number (negative, beyond total)
   - `hint_to_agent` present on non-last pages, None on last page
   - Empty input list
   - Single-page result

**Fixtures**: Mock scenario data matching real API response structure (full scenario objects
with steps, targetFilter, attackerFilter), mock categories map `Dict[int, str]`,
pre-transformed reduced scenario dicts for filter/ordering/pagination tests.

**Changes**:

| File | Action | Description |
|------|--------|-------------|
| `safebreach_mcp_config/tests/test_config_types.py` | Modify | Add scenario test classes (all RED) |

**Git Commit**: `test(config): add RED unit tests for scenario types and transforms`

---

### Phase 2: GREEN — Types Implementation

**Semantic Change**: Implement scenario transform, filter, ordering, and pagination functions
to make all Phase 1 tests pass.

**Deliverables**: All pure functions passing their tests.

**Implementation Details**:

1. **`compute_is_ready_to_run(scenario)`**
   - Accept a full scenario dict
   - Return `False` if scenario has no steps (empty list)
   - For each step, check that `targetFilter` is a non-empty dict AND `attackerFilter`
     is a non-empty dict
   - For each non-empty filter dict, verify at least one key has a `values` list that is
     non-empty. A key like `"simulators"` with `"values": []` does NOT qualify.
   - Return `True` only if ALL steps pass both checks

2. **`get_reduced_scenario_mapping(scenario, categories_map)`**
   - Accept a full scenario dict and a `Dict[int, str]` mapping category IDs to names
   - Return a new dict with these keys:
     - `id`, `name`, `createdBy`, `recommended`, `tags`, `createdAt`, `updatedAt`
       — preserved directly from the scenario
     - `description` — truncated to 200 characters with "..." suffix if longer; `None` if null
     - `category_names` — list of resolved category name strings by looking up each int in
       `scenario['categories']` against the categories_map; skip unknown IDs
     - `step_count` — `len(scenario.get('steps', []))`
     - `is_ready_to_run` — result of `compute_is_ready_to_run(scenario)`

3. **`filter_scenarios_by_criteria(scenarios, name_filter, creator_filter, category_filter,
   recommended_filter, tag_filter, ready_to_run_filter)`**
   - Copy input list, then chain filters sequentially (AND logic)
   - `name_filter`: case-insensitive partial match on `name`
   - `creator_filter`: if `"safebreach"` → match `createdBy == "SafeBreach"` (case-insensitive);
     if `"custom"` → match `createdBy != "SafeBreach"` (case-insensitive)
   - `category_filter`: case-insensitive partial match on any string in `category_names` list
   - `recommended_filter`: exact boolean match on `recommended`
   - `tag_filter`: case-insensitive partial match on any string in `tags` list; scenarios with
     `tags=None` or empty tags are excluded when this filter is active
   - `ready_to_run_filter`: exact boolean match on `is_ready_to_run`

4. **`apply_scenario_ordering(scenarios, order_by, order_direction)`**
   - Valid `order_by`: `"name"` (default), `"step_count"`, `"createdAt"`, `"updatedAt"`
   - Valid `order_direction`: `"asc"` (default), `"desc"`
   - Sort using appropriate key function; for string fields use `.lower()` for
     case-insensitive ordering

5. **`paginate_scenarios(scenarios, page_number, page_size)`**
   - Follow exact pattern from `playbook_types.py:paginate_attacks`
   - Return dict: `page_number`, `total_pages`, `total_scenarios`,
     `scenarios_in_page`, `hint_to_agent` (None on last page)
   - On invalid page_number: return `error` key with empty `scenarios_in_page`

**Verification**: Run `uv run pytest safebreach_mcp_config/tests/test_config_types.py -v`
— all Phase 1 tests must pass (RED → GREEN).

**Changes**:

| File | Action | Description |
|------|--------|-------------|
| `safebreach_mcp_config/config_types.py` | Modify | Add 5 new functions for scenario transforms |

**Git Commit**: `feat(config): implement scenario transforms to pass types tests (GREEN)`

---

### Phase 3: RED — Functions Tests

**Semantic Change**: Write all unit tests for scenario business logic functions.
All tests will fail (RED) because the functions don't exist yet.

**Deliverables**: Complete test suite for `config_functions.py` scenario functions.

**Implementation Details**:

1. **Test `_get_all_scenarios_from_cache_or_api`** — `TestGetAllScenariosFromCacheOrApi` class
   - Successful API call: mock `requests.get` returning scenario list, verify return
   - Cache hit: enable caching, pre-populate cache, verify no API call made
   - Cache miss: enable caching, verify API called and result cached
   - API error: mock `requests.get` raising exception, verify it propagates
   - HTTP error: mock response with non-200 status, verify `raise_for_status()` triggers

2. **Test `_get_categories_map_from_cache_or_api`** — `TestGetCategoriesMapFromCacheOrApi` class
   - Successful API call: verify returns `Dict[int, str]` mapping
   - Cache hit/miss behavior
   - API error handling

3. **Test `sb_get_scenarios`** — `TestSbGetScenarios` class
   - Full orchestration: mock both API calls, verify paginated filtered result
   - Invalid `order_by`: verify `ValueError`
   - Invalid `creator_filter`: verify `ValueError`
   - API failure: verify error dict returned (not exception raised)
   - Pagination: create 25+ mock scenarios, verify page_number/total_pages

4. **Test `sb_get_scenario_details`** — `TestSbGetScenarioDetails` class
   - Found: mock scenarios list with target ID, verify full payload returned
   - Not found: verify `ValueError` raised
   - Empty scenario_id: verify `ValueError` raised
   - Verify `category_names` added to returned scenario

5. **Fixture setup**
   - `setup_method`: clear both `scenarios_cache` and `categories_cache`
   - `@pytest.fixture` for mock scenario data matching real API structure
   - `@pytest.fixture` for mock categories API response (list of category objects)
   - `@patch()` decorators for `requests.get`, `get_secret_for_console`, `get_api_base_url`

**Changes**:

| File | Action | Description |
|------|--------|-------------|
| `safebreach_mcp_config/tests/test_config_functions.py` | Modify | Add scenario function test classes (all RED) |

**Git Commit**: `test(config): add RED unit tests for scenario business logic functions`

---

### Phase 4: GREEN — Functions Implementation

**Semantic Change**: Implement scenario business logic functions to make all Phase 3
tests pass.

**Deliverables**: API integration, caching, and orchestration functions.

**Implementation Details**:

1. **Module-level cache instances**
   - `scenarios_cache = SafeBreachCache(name="scenarios", maxsize=5, ttl=1800)`
   - `categories_cache = SafeBreachCache(name="scenario_categories", maxsize=5, ttl=3600)`
   - `clear_scenarios_cache()` and `clear_categories_cache()` helper functions

2. **`_get_all_scenarios_from_cache_or_api(console)`**
   - Cache key: `f"scenarios_{console}"`
   - If `is_caching_enabled("config")`, check `scenarios_cache.get(cache_key)`
   - On cache miss: call `get_secret_for_console(console)` for token,
     `get_api_base_url(console, 'content-manager')` for base URL
   - Build URL: `f"{base_url}/api/content-manager/vLatest/scenarios"`
   - Headers: `{"Content-Type": "application/json", "x-apitoken": apitoken}`
   - `requests.get(url, headers=headers, timeout=120)`, call `response.raise_for_status()`
   - Parse `response.json()` — the response IS the list (no `data` wrapper)
   - Cache result if caching enabled
   - Return `List[Dict]`

3. **`_get_categories_map_from_cache_or_api(console)`**
   - Cache key: `f"categories_{console}"`
   - Same cache-check pattern with `is_caching_enabled("config")` and `categories_cache`
   - Same API call pattern, URL: `f"{base_url}/api/content-manager/vLatest/scenarioCategories"`
   - Parse response list and build `Dict[int, str]` mapping `category['id']` to
     `category['name']`
   - Cache the map if caching enabled
   - Return `Dict[int, str]`

4. **`sb_get_scenarios(console, page_number, name_filter, creator_filter, category_filter,
   recommended_filter, tag_filter, ready_to_run_filter, order_by, order_direction)`**
   - Validate `order_by` against valid list, raise `ValueError` if invalid
   - Validate `order_direction` against `['asc', 'desc']`
   - Validate `creator_filter` against `['safebreach', 'custom']` if provided
   - Validate `page_number >= 0`
   - Inside try/except:
     - Fetch all scenarios: `_get_all_scenarios_from_cache_or_api(console)`
     - Fetch categories map: `_get_categories_map_from_cache_or_api(console)`
     - Transform each scenario to reduced view: `get_reduced_scenario_mapping(s, categories_map)`
     - Apply filters: `filter_scenarios_by_criteria(reduced, ...)`
     - Apply ordering: `apply_scenario_ordering(filtered, order_by, order_direction)`
     - Paginate: `paginate_scenarios(ordered, page_number, PAGE_SIZE)`
     - Build `applied_filters` dict (only non-default values)
     - Add `applied_filters` to paginated result
     - Return result dict
   - On exception: return `{"error": f"Failed to get scenarios: {str(e)}", "console": console}`

5. **`sb_get_scenario_details(scenario_id, console)`**
   - Validate `scenario_id` is not empty
   - Fetch all scenarios: `_get_all_scenarios_from_cache_or_api(console)`
   - Fetch categories map: `_get_categories_map_from_cache_or_api(console)`
   - Find scenario by matching `scenario['id'] == scenario_id`
   - If not found: raise `ValueError(f"Scenario with ID '{scenario_id}' not found")`
   - Return full scenario dict with added `category_names` field (resolved from categories_map)

**Verification**: Run `uv run pytest safebreach_mcp_config/tests/ -v -m "not e2e"`
— all Phase 1 + Phase 3 tests must pass (RED → GREEN).

**Changes**:

| File | Action | Description |
|------|--------|-------------|
| `safebreach_mcp_config/config_functions.py` | Modify | Add cache instances, 5 new functions, 2 cache-clear helpers |

**Git Commit**: `feat(config): implement scenario business logic to pass functions tests (GREEN)`

---

### Phase 5: MCP Tool Registration

**Semantic Change**: Register `get_scenarios` and `get_scenario_details` as MCP tools in the
Config Server.

**Deliverables**: Two new MCP tools accessible to AI agents.

**Implementation Details**:

1. **Update imports** in `config_server.py` to include `sb_get_scenarios` and
   `sb_get_scenario_details` from `.config_functions`

2. **`get_scenarios` tool registration**
   - Decorator: `@self.mcp.tool(name="get_scenarios", description="...")`
   - Description must document all parameters for Claude (same style as `get_console_simulators`)
   - Function signature: `async def get_scenarios_tool(console, page_number, name_filter,
     creator_filter, category_filter, recommended_filter, tag_filter, ready_to_run_filter,
     order_by, order_direction) -> dict`
   - All filter parameters default to `None`, page_number defaults to `0`,
     order_by defaults to `"name"`, order_direction defaults to `"asc"`
   - Include single-tenant console auto-resolve pattern (same as `get_console_simulators`)
   - Call `sb_get_scenarios(...)` and return result

3. **`get_scenario_details` tool registration**
   - Decorator: `@self.mcp.tool(name="get_scenario_details", description="...")`
   - Function signature: `async def get_scenario_details_tool(scenario_id, console) -> dict`
   - `scenario_id` is required (UUID string), `console` defaults to `"default"`
   - Include single-tenant console auto-resolve
   - Call `sb_get_scenario_details(scenario_id, console)` and return result

**Changes**:

| File | Action | Description |
|------|--------|-------------|
| `safebreach_mcp_config/config_server.py` | Modify | Add 2 new tool registrations + import |

**Git Commit**: `feat(config): register get_scenarios and get_scenario_details MCP tools`

---

### Phase 6: RED/GREEN — E2E Tests

**Semantic Change**: Add end-to-end tests that call the real SafeBreach API on pentest01
console to validate scenario tools work against real data.

**Deliverables**: E2E test suite marked with `@pytest.mark.e2e` and `@skip_e2e`.

**Implementation Details**:

1. **Test `get_scenarios` E2E** — `TestScenarioE2E` class
   - Fetch scenarios from pentest01 console with no filters, verify non-empty response
   - Verify response structure: `page_number`, `total_pages`, `total_scenarios`,
     `scenarios_in_page`, `hint_to_agent`
   - Verify each scenario in page has expected keys: `id`, `name`, `createdBy`,
     `category_names`, `step_count`, `is_ready_to_run`, `recommended`
   - Test `name_filter` with a known scenario name substring
   - Test `creator_filter="safebreach"` returns only SafeBreach-created scenarios
   - Test `recommended_filter=True` returns only recommended scenarios
   - Test `ready_to_run_filter=True` returns only ready scenarios (expect 4 on pentest01)
   - Test pagination: verify page 0 returns PAGE_SIZE items, verify `hint_to_agent`
     points to page 1

2. **Test `get_scenario_details` E2E**
   - Fetch scenario list, pick the first ID, call `sb_get_scenario_details` with that ID
   - Verify full payload: `id`, `name`, `steps`, `categories`, `category_names`
   - Verify `category_names` is a list of strings (resolved from categories endpoint)
   - Test with non-existent ID: verify `ValueError` raised

3. **Test infrastructure**
   - Use `@pytest.mark.e2e` and `@skip_e2e` decorators (following existing E2E pattern)
   - Console: `E2E_CONSOLE` env var or default to `"pentest01"`
   - Requires `source .vscode/set_env.sh` before running

**Changes**:

| File | Action | Description |
|------|--------|-------------|
| `safebreach_mcp_config/tests/test_e2e_scenarios.py` | Create | E2E tests for scenario tools against pentest01 |

**Git Commit**: `test(config): add E2E tests for scenario tools against pentest01`

---

### Phase 7: Documentation

**Semantic Change**: Update CLAUDE.md with new tool documentation.

**Deliverables**: Updated documentation reflecting the two new Config Server tools.

**Implementation Details**:

1. **Update CLAUDE.md Config Server section**
   - Add `get_scenarios` tool to the Config Server tools list with description of all
     parameters and filtering capabilities
   - Add `get_scenario_details` tool with description
   - Update the tool count
   - Add scenario-specific sections: ready-to-run definition, category resolution

2. **Update cache configuration section**
   - Document `scenarios` cache (maxsize=5, TTL=1800s)
   - Document `scenario_categories` cache (maxsize=5, TTL=3600s)

**Changes**:

| File | Action | Description |
|------|--------|-------------|
| `CLAUDE.md` | Modify | Add scenario tool documentation, cache config |

**Git Commit**: `docs: add scenario tools to CLAUDE.md documentation`

## 10. Risks and Assumptions

### Technical Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Scenario API response structure changes | Medium | Transform functions isolate API changes from tool interface |
| Large scenario counts on customer consoles | Low | Client-side pagination handles any count; cache bounds memory |
| `x-apitoken` auth rejected by content-manager API | Low | Already tested live on pentest01; fallback to session token if needed |

### Assumptions
- The `/api/content-manager/vLatest/scenarios` endpoint returns ALL scenarios in a single
  response (no server-side pagination). Confirmed on pentest01 (443 scenarios).
- Category IDs in scenario objects always reference valid categories from the categories
  endpoint. Unknown IDs are silently skipped in resolution.
- The `createdBy` field will contain `"SafeBreach"` for OOB scenarios and a different
  value (user name) for custom scenarios.

## 11. Future Enhancements

- **Run scenario via queue API**: Use the full cached scenario payload to submit scenarios
  for execution via the SafeBreach queue API
- **Scenario search by MITRE technique**: Cross-reference scenario step attack filters with
  playbook MITRE data for technique-based discovery
- **Scenario comparison**: Compare two scenarios' attack coverage

## 12. Executive Summary

- **Issue**: AI agents cannot discover or inspect SafeBreach scenarios via MCP tools
- **What Was Built**: Two new MCP tools (`get_scenarios`, `get_scenario_details`) in the
  Config Server with comprehensive filtering, pagination, and category resolution
- **Key Technical Decisions**: Config Server placement; single API call with client-side
  processing; separate category cache; ready-to-run computed from step filter analysis;
  full raw payload for details (future queue API use)
- **Business Value**: Completes the MCP tool coverage for scenario management, enabling AI
  agents to assist users with scenario discovery, selection, and inspection

## 14. Change Log

| Date | Change Description |
|------|-------------------|
| 2026-04-14 18:30 | PRD created — initial draft |
| 2026-04-14 18:45 | Restructured to pure TDD phases (RED → GREEN), added E2E test phase against pentest01 |
| 2026-04-15 12:00 | Added Phase 8 — integrate custom scenarios (plans API) discovered after initial impl. Added source_type field to unify OOB and custom. |
