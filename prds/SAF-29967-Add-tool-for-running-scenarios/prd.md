# Run Scenario MCP Tool for Studio Server — SAF-29967

## 1. Overview

| Field | Value |
|-------|-------|
| **Task Type** | Feature |
| **Purpose** | Enable AI agents to execute SafeBreach scenarios via MCP tool |
| **Target Consumer** | AI agents (Claude, etc.) interacting with SafeBreach via MCP protocol |
| **Key Benefits** | 1) Scenario execution completes the discover→inspect→run workflow 2) Pass-through relay keeps implementation simple and future-proof 3) Elephant carpaccio slices enable safe incremental delivery with E2E sign-off |
| **Business Alignment** | Extends SafeBreach MCP coverage from read-only scenario inspection to full execution, completing the AI-driven Validate and Propagate workflows |
| **Originating Request** | [SAF-29967](https://safebreach.atlassian.net/browse/SAF-29967) |

## 1.5. Document Status

| Field | Value |
|-------|-------|
| **PRD Status** | Draft |
| **Last Updated** | 2026-04-18 11:00 |
| **Owner** | Yossi Attas |
| **Current Phase** | N/A |

## 2. Solution Description

### Chosen Solution
**Approach D — Pass-Through Relay with Elephant Carpaccio Delivery.**

Fetch the scenario payload as-is from the SafeBreach API, validate readiness, and relay the
entire payload unchanged to the orchestrator queue API. No field extraction, no transformation,
no DAG resolution — just validation and relay.

The tool lives in the **Studio Server** (port 8004) alongside `sb_run_studio_attack()`,
maintaining consistency with the existing execution pattern. Scenario data is fetched
directly from the SafeBreach API (no cross-server calls to Config Server).

### Delivery Strategy: Elephant Carpaccio

Five thin vertical slices, each delivering a complete end-to-end capability. Every slice
is signed off with real E2E tests against the pentest01 console before proceeding to the
next. Development is fully autonomous within each slice since pentest01 has scenarios of
every type needed.

| Slice | Capability | E2E Gate |
|-------|-----------|----------|
| **Slice 1** | Ready-to-run OOB scenario | Run OOB scenario on pentest01, verify test_id |
| **Slice 2** | Ready-to-run custom plan | Run custom plan on pentest01, verify test_id |
| **Slice 3** | Non-ready OOB scenario + augmentation | Augment missing filters, run on pentest01 |
| **Slice 4** | Non-ready custom plan + augmentation | Augment missing filters, run on pentest01 |
| **Slice 5** | Propagate scenario type support | Run Propagate scenario on pentest01 |

### Alternatives Considered

**Approach A: Thin Proxy — Forward Raw Steps + All Metadata**
- Forward the entire scenario object including unknown fields
- Pros: Simplest code
- Cons: Risk of sending fields the queue API rejects; no validation layer

**Approach B: Step Extraction — Forward Only Queue-Compatible Fields**
- Extract only `attacksFilter`, `attackerFilter`, `targetFilter`, `systemFilter` from each step
- Pros: Clean, mirrors Studio's payload exactly
- Cons: Discards DAG metadata (actions/edges) that the queue API needs; over-transforms

**Approach C: Hybrid — DAG Resolution + Field Extraction**
- Resolve step execution order from DAG, then extract queue-compatible fields
- Pros: Correct ordering + clean payload
- Cons: Duplicates DAG resolution logic; unnecessary complexity

### Decision Rationale
Approach D wins because the queue API already accepts the full OOB scenario object as-is
(confirmed via user-provided curl samples from pentest01). No transformation is needed —
just wrap the scenario in `{"plan": scenario}` and POST. This also provides the cleanest
path for Slices 3-4 (augmenting non-ready scenarios), since the payload is already in its
native format and fields can be modified in-place.

The key design decision to **duplicate `compute_is_ready_to_run` in Studio** (rather than
importing from config_types) is deliberate: Studio's version will evolve in Slices 3-4 to
return diagnostic output (what's missing and how to fill it) to guide the LLM, while
Config's version stays as a simple boolean filter.

## 3. Core Feature Components

### Component A: Scenario Readiness Validation (`studio_functions.py`)

**Purpose**: Scenario readiness checking with phased evolution.

**Slice 1-2 (boolean)**:
- `_has_real_filter_criteria(filter_dict)` — Check if a filter dict has at least one key
  with non-empty values. Duplicated from config_types.py.
- `compute_scenario_readiness(scenario)` — Returns `bool`. Checks that ALL steps have BOTH
  `targetFilter` AND `attackerFilter` with at least one key containing non-empty values.

**Slice 3-4 (diagnostic — future)**:
- `compute_scenario_readiness(scenario)` evolves to return a structured result: `bool` +
  per-step diagnostic info (which steps are missing which filters, what values are needed).
  This guides the LLM to call the tool with the right augmenting parameters.

### Component B: Scenario Fetch (`studio_functions.py`)

**Purpose**: Fetch scenario data from SafeBreach APIs.

**Slice 1**: `_fetch_all_scenarios(console)` — Fetches OOB scenarios from
`GET /api/content-manager/vLatest/scenarios`. No caching (execution is infrequent).

**Slice 2**: `_fetch_all_plans(console)` — Fetches custom plans from
`GET /api/config/v2/accounts/{account_id}/plans?details=true`.

### Component C: Scenario Run Orchestration (`studio_functions.py`)

**Purpose**: Main orchestration: find scenario → validate → build payload → queue.

**Slice 1**: `sb_run_scenario(scenario_id, console, test_name)` — OOB-only.
Finds by UUID, validates readiness, builds full relay payload, POSTs to queue.

**Slice 2**: Extends to search custom plans when OOB lookup misses. Custom plan payload
uses `planId` reference (no steps/actions/edges).

**Slice 3-4**: Accepts augmenting parameters (e.g., `target_filter_overrides`,
`attacker_filter_overrides`) and modifies the scenario payload in-place before relay.

**Slice 5**: Accepts `scenario_type` parameter (Validate/Propagate).

### Component D: MCP Tool Registration (`studio_server.py`)

**Purpose**: Register `run_scenario` as an MCP tool, evolving its parameters per slice.

**Slice 1**: `scenario_id`, `console`, `test_name`
**Slice 2**: Same parameters (custom plans discovered automatically by ID type)
**Slice 3-4**: Adds augmenting parameters for missing filters
**Slice 5**: Adds `scenario_type` parameter

### Component E: Tests

**Per-slice**: Each slice has its own RED/GREEN unit test cycle + E2E sign-off.
E2E tests run against pentest01 and gate progression to the next slice.

## 4. API Endpoints and Integration

### Existing APIs to Consume

**Scenarios List API** (content-manager) — Slice 1, 3:
- **URL**: `GET /api/content-manager/vLatest/scenarios`
- **Headers**: `x-apitoken: {token}`, `Content-Type: application/json`
- **Base URL Resolution**: `get_api_base_url(console, 'content-manager')`
- **Response**: JSON array of scenario objects. Each contains: `id` (UUID string), `name`,
  `description`, `createdBy`, `recommended`, `categories`, `tags`, `steps[]` (with all
  filters), `actions[]` (DAG nodes), `edges[]` (DAG edges), `phases[]`, `systemTags[]`,
  `createdAt`, `updatedAt`

**Plans List API** (config) — Slice 2, 4:
- **URL**: `GET /api/config/v2/accounts/{account_id}/plans?details=true`
- **Headers**: `x-apitoken: {token}`, `Content-Type: application/json`
- **Base URL Resolution**: `get_api_base_url(console, 'config')`
- **Response**: `{"data": [...]}` wrapping plan objects. Each contains: `id` (integer),
  `name`, `steps[]`, `tags`, `userId`, `originalScenarioId`, `createdAt`, `updatedAt`

**Orchestrator Queue API** — All slices:
- **URL**: `POST /api/orch/v4/accounts/{account_id}/queue`
- **Headers**: `x-apitoken: {token}`, `Content-Type: application/json`
- **Query Parameters**: `enableFeedbackLoop=true`, `retrySimulations=true`
- **Base URL Resolution**: `get_api_base_url(console, 'orchestrator')`

**OOB Scenario Run Payload** (Slice 1, confirmed via pentest01):
```
{
  "plan": {
    "name": "<scenario name or custom test_name>",
    "originalScenarioId": "<UUID>",
    "steps": [
      {
        "name": "<step name>",
        "uuid": "<step UUID>",
        "attacksFilter": { "tags": {...}, "origin": {...}, "attackType": {...}, ... },
        "attackerFilter": { "role": {...} },
        "targetFilter": { "os": {...} },
        "systemFilter": { "bypassProxy": {...}, "runAsRoot": {...}, ... }
      }
    ],
    "systemTags": [],
    "actions": [
      {"id": 1, "type": "multiAttack", "data": {"uuid": "<step UUID>"}},
      {"id": 1001, "type": "wait", "data": {"seconds": 0}}
    ],
    "edges": [
      {"to": 1},
      {"from": 1, "to": 1001},
      {"from": 1001, "to": 2}
    ]
  }
}
```

**Custom Plan Run Payload** (Slice 2, confirmed via pentest01):
```
{
  "plan": {
    "name": "<plan name>",
    "planId": <integer>,
    "systemTags": []
  }
}
```

**Queue API Response** (all slices):
```
{
  "data": {
    "planRunId": "<test_id>",
    "name": "<test name>",
    "steps": [
      {"stepRunId": "<step_run_id_1>"},
      {"stepRunId": "<step_run_id_2>"}
    ],
    "priority": "low",
    "draft": false,
    "ranBy": <user_id>,
    "retrySimulations": true
  }
}
```

**Queue Status API** (optional pre-flight, future enhancement):
- **URL**: `GET /api/orch/v4/accounts/{account_id}/queue`
- **Purpose**: Check if free slots are available before submitting

## 6. Non-Functional Requirements

### Technical Constraints
- **Integration**: Studio Server (port 8004) — extends existing `SafeBreachStudioServer`
- **Technology Stack**: Python 3.12+, `requests` library
- **Backward Compatibility**: No breaking changes — additive only
- **No Caching**: Scenarios fetched fresh per execution (infrequent action)

### Performance Requirements
- **Response Times**: Under 10s for fetch + queue submission (API round-trip)
- **Timeout**: 120 seconds per API call (consistent with existing pattern)
- **Memory**: Transient only — scenario list fetched per call, not persisted

## 7. Definition of Done

### Slice 1: Ready-to-run OOB Scenario
- [ ] `run_scenario` MCP tool registered in Studio Server
- [ ] Tool fetches OOB scenarios from content-manager API
- [ ] Tool validates scenario exists by UUID and is ready to run
- [ ] Rejects non-ready scenarios with clear error message
- [ ] OOB scenario payload relayed as-is to queue API (pass-through)
- [ ] Response includes test_id, test_name, step count, step_run_ids as markdown
- [ ] Unit tests pass (readiness, fetch, orchestration, payload, errors)
- [ ] E2E: Successfully runs a ready-to-run OOB scenario on pentest01
- [ ] CLAUDE.md updated

### Slice 2: Ready-to-run Custom Plan
- [ ] Custom plans fetched from plans API
- [ ] Plan run uses `planId` reference payload (no steps/actions/edges)
- [ ] Scenario lookup falls through OOB → custom automatically
- [ ] Unit tests pass for custom plan path
- [ ] E2E: Successfully runs a ready-to-run custom plan on pentest01

### Slice 3: Non-ready OOB Scenario + Augmentation
- [ ] `compute_scenario_readiness` returns diagnostic info (what's missing)
- [ ] Tool accepts augmenting parameters for missing filters
- [ ] Augmented payload relayed to queue API
- [ ] Unit tests pass for diagnostic readiness + augmentation
- [ ] E2E: Augments and runs a non-ready OOB scenario on pentest01

### Slice 4: Non-ready Custom Plan + Augmentation
- [ ] Custom plan augmentation supported
- [ ] Unit tests pass for custom plan augmentation
- [ ] E2E: Augments and runs a non-ready custom plan on pentest01

### Slice 5: Propagate Scenario Type
- [ ] `scenario_type` parameter added (Validate/Propagate)
- [ ] Propagate scenarios can be executed
- [ ] Unit tests pass for Propagate type
- [ ] E2E: Successfully runs a Propagate scenario on pentest01

## 8. Testing Strategy

### Unit Testing (per-slice TDD)
- **Framework**: pytest with `unittest.mock`
- **Pattern**: RED phase (write failing tests) → GREEN phase (implement to pass)
- **Mocking**: `@patch()` for `requests.get`, `requests.post`, `get_secret_for_console`,
  `get_api_base_url`, `get_api_account_id`
- **Fixtures**: Per-slice mock data matching real API structures from pentest01

### E2E Testing (per-slice sign-off gate)
- **Environment**: pentest01 console (`E2E_CONSOLE` env var, `source .vscode/set_env.sh`)
- **Markers**: `@pytest.mark.e2e` and `@skip_e2e`
- **Gate rule**: All E2E tests for a slice must pass before starting the next slice
- **Autonomy**: pentest01 has scenarios of all types — development is fully autonomous.
  If blocked on a specific scenario ID, user provides qualified payloads.

| Slice | E2E Gate Test |
|-------|--------------|
| 1 | Run ready-to-run OOB scenario, verify test_id returned |
| 2 | Run ready-to-run custom plan, verify test_id returned |
| 3 | Augment non-ready OOB scenario, run, verify test_id |
| 4 | Augment non-ready custom plan, run, verify test_id |
| 5 | Run Propagate scenario, verify test_id |

## 9. Implementation Phases

### Phase Overview

Five **elephant carpaccio slices**, each a complete vertical slice with its own TDD cycle
and E2E sign-off. Each slice adds a new capability that works end-to-end.

| Phase | Slice | Status | Completed | Commit SHA | Notes |
|-------|-------|--------|-----------|------------|-------|
| 1.1 | S1 | ⏳ Pending | - | - | RED: readiness + fetch tests |
| 1.2 | S1 | ⏳ Pending | - | - | GREEN: readiness + fetch impl |
| 1.3 | S1 | ⏳ Pending | - | - | RED: run OOB scenario tests |
| 1.4 | S1 | ⏳ Pending | - | - | GREEN: run OOB scenario impl |
| 1.5 | S1 | ⏳ Pending | - | - | MCP tool registration |
| 1.6 | S1 | ⏳ Pending | - | - | E2E sign-off (pentest01) |
| 1.7 | S1 | ⏳ Pending | - | - | Documentation |
| 2.1 | S2 | ⏳ Pending | - | - | RED: custom plan fetch + run tests |
| 2.2 | S2 | ⏳ Pending | - | - | GREEN: custom plan fetch + run impl |
| 2.3 | S2 | ⏳ Pending | - | - | E2E sign-off (pentest01) |
| 2.4 | S2 | ⏳ Pending | - | - | Documentation update |
| 3.1 | S3 | ⏳ Pending | - | - | RED: diagnostic readiness + augmentation tests |
| 3.2 | S3 | ⏳ Pending | - | - | GREEN: diagnostic readiness + augmentation impl |
| 3.3 | S3 | ⏳ Pending | - | - | MCP tool parameter extension |
| 3.4 | S3 | ⏳ Pending | - | - | E2E sign-off (pentest01) |
| 3.5 | S3 | ⏳ Pending | - | - | Documentation update |
| 4.1 | S4 | ⏳ Pending | - | - | RED: custom plan augmentation tests |
| 4.2 | S4 | ⏳ Pending | - | - | GREEN: custom plan augmentation impl |
| 4.3 | S4 | ⏳ Pending | - | - | E2E sign-off (pentest01) |
| 4.4 | S4 | ⏳ Pending | - | - | Documentation update |
| 5.1 | S5 | ⏳ Pending | - | - | RED: Propagate type tests |
| 5.2 | S5 | ⏳ Pending | - | - | GREEN: Propagate type impl |
| 5.3 | S5 | ⏳ Pending | - | - | E2E sign-off (pentest01) |
| 5.4 | S5 | ⏳ Pending | - | - | Documentation update |

---

## Slice 1: Ready-to-run OOB Scenario

**Goal**: A working `run_scenario` MCP tool that can execute ready-to-run OOB scenarios.
This is the foundational slice — establishes the fetch→validate→relay pattern.

### Phase 1.1: RED — Readiness + Fetch Tests

**Semantic Change**: Write all unit tests for scenario readiness validation and API fetch.
All tests will fail (RED) because the functions don't exist yet.

**Deliverables**: Test suite for `compute_scenario_readiness`, `_has_real_filter_criteria`,
and `_fetch_all_scenarios`.

**Implementation Details**:

1. **Test `_has_real_filter_criteria`** — `TestHasRealFilterCriteria` class
   - Empty dict returns False
   - Dict with key having `values: []` returns False
   - Dict with key having `values: ["WINDOWS"]` returns True
   - Dict with nested dict having non-empty values returns True
   - Non-dict truthy value returns True

2. **Test `compute_scenario_readiness`** — `TestComputeScenarioReadiness` class
   - Scenario with all steps having real target + attacker criteria returns True
   - Scenario with empty steps list returns False
   - Scenario with step missing targetFilter returns False
   - Scenario with step missing attackerFilter returns False
   - Scenario with step having empty targetFilter values returns False
   - Scenario with mixed steps (some ready, some not) returns False
   - Use realistic step structures matching the content-manager API format (with `name`,
     `uuid`, `attacksFilter`, `attackerFilter`, `targetFilter`, `systemFilter`)

3. **Test `_fetch_all_scenarios`** — `TestFetchAllScenarios` class
   - Successful API call: mock `requests.get` returning scenario list, verify return value
   - HTTP error: mock response raising HTTPError, verify exception propagates
   - Empty response: mock returning empty list, verify empty list returned
   - Verify correct URL construction: `{base_url}/api/content-manager/vLatest/scenarios`
   - Verify correct headers: `x-apitoken` and `Content-Type`

**Fixtures**: Mock scenario data matching real content-manager API response structure
(full OOB scenario with 5 steps, actions with multiAttack + wait nodes, edges defining
DAG). Use the pentest01 "Step 1 - Fortify your Network Perimeter" payload as reference.

**Changes**:

| File | Action | Description |
|------|--------|-------------|
| `safebreach_mcp_studio/tests/test_studio_functions.py` | Modify | Add readiness + fetch test classes (all RED) |

**Git Commit**: `test(studio): add RED unit tests for scenario readiness and fetch`

---

### Phase 1.2: GREEN — Readiness + Fetch Implementation

**Semantic Change**: Implement scenario readiness validation and API fetch functions
to make all Phase 1.1 tests pass.

**Deliverables**: `_has_real_filter_criteria`, `compute_scenario_readiness`,
`_fetch_all_scenarios` functions.

**Implementation Details**:

1. **`_has_real_filter_criteria(filter_dict)`**
   - Duplicate from config_types.py logic
   - Accept a dict, return False if empty
   - For each value: if it's a dict, check for non-empty `values` list; if truthy
     non-dict, return True
   - Return True if any key qualifies, False otherwise

2. **`compute_scenario_readiness(scenario)`**
   - Accept a full scenario dict
   - Return False if no steps (empty list)
   - For each step: check that `targetFilter` and `attackerFilter` both have real criteria
     via `_has_real_filter_criteria`
   - Return True only if ALL steps pass both checks

3. **`_fetch_all_scenarios(console)`**
   - Get auth token via `get_secret_for_console(console)`
   - Get base URL via `get_api_base_url(console, 'content-manager')`
   - Build URL: `{base_url}/api/content-manager/vLatest/scenarios`
   - Headers: `{"Content-Type": "application/json", "x-apitoken": apitoken}`
   - `requests.get(url, headers=headers, timeout=120)`
   - Call `response.raise_for_status()`
   - Return `response.json()` (the response IS the list, no `data` wrapper)

**Verification**: Run unit tests — all Phase 1.1 tests must pass (RED → GREEN).

**Changes**:

| File | Action | Description |
|------|--------|-------------|
| `safebreach_mcp_studio/studio_functions.py` | Modify | Add 3 new functions |

**Git Commit**: `feat(studio): implement scenario readiness and fetch (GREEN)`

---

### Phase 1.3: RED — Run OOB Scenario Tests

**Semantic Change**: Write all unit tests for the `sb_run_scenario` orchestration function.
All tests will fail (RED) because the function doesn't exist yet.

**Deliverables**: Test suite for `sb_run_scenario`.

**Implementation Details**:

1. **Test `sb_run_scenario`** — `TestRunScenario` class
   - **Mock decorators** on each test: `@patch` for `requests.post`, `requests.get`,
     `get_api_account_id`, `get_api_base_url`, `get_secret_for_console`

   - **`test_run_scenario_success`**: Mock GET returning scenario list with one ready
     scenario, mock POST returning queue response with `planRunId` and multiple
     `stepRunId`s. Verify: return dict has `test_id`, `scenario_id`, `scenario_name`,
     `step_count`, `step_run_ids`, `status='queued'`. Verify: POST payload has
     `plan.name`, `plan.originalScenarioId`, `plan.steps`, `plan.actions`, `plan.edges`,
     `plan.systemTags`.

   - **`test_run_scenario_custom_test_name`**: Provide `test_name="My Custom Test"`.
     Verify: `plan.name` in POST payload equals custom name, not scenario name.

   - **`test_run_scenario_not_found`**: Mock GET returning scenarios without the target
     ID. Verify: `ValueError` raised with "not found" message.

   - **`test_run_scenario_not_ready`**: Mock GET returning scenario with empty
     attackerFilter. Verify: `ValueError` raised with "not ready to run" message.

   - **`test_run_scenario_empty_id`**: Call with `scenario_id=""`.
     Verify: `ValueError` raised.

   - **`test_run_scenario_api_error`**: Mock POST raising `RequestException`.
     Verify: exception propagates.

   - **`test_run_scenario_multi_step_response`**: Mock POST response with 5 stepRunIds.
     Verify: `step_run_ids` list has 5 entries, `step_count` is 5.

**Fixtures**:
- `mock_oob_scenario`: Full OOB scenario matching pentest01 structure (5 steps with DAG
  actions/edges, attacksFilter with tags/origin/attackType, attackerFilter with role,
  targetFilter with os, systemFilter with bypassProxy/runAsRoot/simulationUsers/proxies)
- `mock_queue_response`: `{"data": {"planRunId": "...", "steps": [{"stepRunId": "..."}],
  "name": "..."}}`

**Changes**:

| File | Action | Description |
|------|--------|-------------|
| `safebreach_mcp_studio/tests/test_studio_functions.py` | Modify | Add run scenario test class (all RED) |

**Git Commit**: `test(studio): add RED unit tests for sb_run_scenario`

---

### Phase 1.4: GREEN — Run OOB Scenario Implementation

**Semantic Change**: Implement `sb_run_scenario` to make all Phase 1.3 tests pass.

**Deliverables**: Main orchestration function for scenario execution.

**Implementation Details**:

1. **`sb_run_scenario(scenario_id, console, test_name)`**
   - **Parameters**:
     - `scenario_id: str` — UUID string of the OOB scenario (required)
     - `console: str = "default"` — SafeBreach console identifier
     - `test_name: str = None` — Optional custom test name
   - **Returns**: Dict with `test_id`, `test_name`, `scenario_id`, `scenario_name`,
     `step_count`, `step_run_ids`, `status`
   - **Raises**: `ValueError` for invalid inputs, `Exception` for API errors

   **Step-by-step logic**:
   1. Validate `scenario_id` is not empty/None
   2. Call `_fetch_all_scenarios(console)` to get all OOB scenarios
   3. Find scenario where `str(scenario['id']) == scenario_id`
   4. If not found, raise `ValueError(f"Scenario '{scenario_id}' not found")`
   5. Call `compute_scenario_readiness(scenario)` — if False, raise
      `ValueError(f"Scenario '{scenario['name']}' is not ready to run...")`
   6. Set `effective_test_name = test_name or scenario['name']`
   7. Get auth: `apitoken`, `base_url` (orchestrator), `account_id`
   8. Build payload — relay scenario fields as-is inside `{"plan": ...}`:
      `name` (effective_test_name), `originalScenarioId` (scenario id),
      `steps`, `actions`, `edges`, `systemTags`
   9. POST to queue with `enableFeedbackLoop=true`, `retrySimulations=true`,
      timeout=120
   10. Parse response: `data.planRunId`, list of `data.steps[].stepRunId`,
       `data.name`
   11. Return result dict with `test_id`, `test_name`, `scenario_id`,
       `scenario_name`, `step_count`, `step_run_ids`, `status='queued'`

**Verification**: Run unit tests — all Phase 1.3 tests must pass (RED → GREEN).

**Changes**:

| File | Action | Description |
|------|--------|-------------|
| `safebreach_mcp_studio/studio_functions.py` | Modify | Add `sb_run_scenario` function |

**Git Commit**: `feat(studio): implement sb_run_scenario orchestration (GREEN)`

---

### Phase 1.5: MCP Tool Registration

**Semantic Change**: Register `run_scenario` as an MCP tool in the Studio Server.

**Deliverables**: New MCP tool accessible to AI agents.

**Implementation Details**:

1. **Update imports** in `studio_server.py` to include `sb_run_scenario`

2. **`run_scenario` tool registration**
   - Decorator: `@self.mcp.tool(name="run_scenario", description="...")`
   - Description documents all parameters for Claude:
     - `scenario_id` (required, str): UUID of the OOB scenario to execute
     - `console` (optional, str, default "default"): SafeBreach console name
     - `test_name` (optional, str): Custom name for the test execution
     - Include IMPORTANT note about triggering real attack simulations
   - Returns **markdown string** (Studio pattern):
     `## Scenario Execution Queued`, test_id, scenario name, step count, step_run_ids,
     next steps guidance (use `get_test_details` to track)
   - Error handling: catch ValueError then Exception
   - Single-tenant console auto-resolve pattern

**Changes**:

| File | Action | Description |
|------|--------|-------------|
| `safebreach_mcp_studio/studio_server.py` | Modify | Add `run_scenario` tool + import |

**Git Commit**: `feat(studio): register run_scenario MCP tool`

---

### Phase 1.6: E2E Sign-off

**Semantic Change**: E2E tests against pentest01 confirming real OOB scenario execution.

**Deliverables**: E2E test suite. **Gate**: all tests pass before Slice 2 begins.

**Implementation Details**:

1. **`TestRunScenarioE2E`** class
   - **`test_run_ready_oob_scenario`**: Fetch all scenarios from pentest01, find one
     where `compute_scenario_readiness` returns True, call `sb_run_scenario` with its
     ID. Verify: non-empty `test_id`, `step_count > 0`, `status='queued'`,
     `step_run_ids` is a non-empty list.
   - **`test_run_scenario_not_found`**: Call with fake UUID, verify ValueError.
   - **`test_run_scenario_not_ready`**: Find a non-ready scenario (if any), verify
     ValueError. Skip if all happen to be ready.
   - **`test_run_scenario_custom_name`**: Run with custom `test_name`, verify response
     matches.

2. **Infrastructure**: `@pytest.mark.e2e`, `@skip_e2e`, `E2E_CONSOLE` env var

**Changes**:

| File | Action | Description |
|------|--------|-------------|
| `safebreach_mcp_studio/tests/test_e2e_run_scenario.py` | Create | E2E tests for OOB scenario run |

**Git Commit**: `test(studio): add E2E tests for OOB scenario run against pentest01`

---

### Phase 1.7: Documentation

**Semantic Change**: Update CLAUDE.md with new tool documentation.

**Implementation Details**:
- Add `run_scenario` tool to Studio Server section (or create section)
- Document parameters, behavior, limitations
- Note: "Only ready-to-run OOB scenarios in this version"
- Update MCP Tools Available count

**Changes**:

| File | Action | Description |
|------|--------|-------------|
| `CLAUDE.md` | Modify | Add run_scenario tool documentation |

**Git Commit**: `docs: add run_scenario tool to CLAUDE.md`

---

## Slice 2: Ready-to-run Custom Plan

**Goal**: Extend `run_scenario` to also run custom plans by their integer ID.
Custom plans use a minimal `planId` reference payload — no steps/actions/edges.

**Pre-requisite**: Slice 1 E2E sign-off passed.

### Phase 2.1: RED — Custom Plan Fetch + Run Tests

**Semantic Change**: Write tests for custom plan fetching and the custom plan run path.

**Implementation Details**:

1. **Test `_fetch_all_plans`** — `TestFetchAllPlans` class
   - Successful fetch from plans API, verify return value
   - HTTP error handling
   - Verify URL: `{base_url}/api/config/v2/accounts/{account_id}/plans?details=true`
   - Verify response unwrapping: plans API wraps in `{"data": [...]}`

2. **Test `sb_run_scenario` custom plan path** — extend `TestRunScenario`
   - **`test_run_custom_plan_success`**: Mock OOB fetch returning empty (no match),
     mock plans fetch returning plan with matching integer ID. Mock POST returning
     queue response. Verify: payload has `plan.name`, `plan.planId`, `plan.systemTags`
     — NO `steps`, NO `actions`, NO `edges`.
   - **`test_run_custom_plan_by_integer_id`**: Call with integer-string ID (e.g., "130").
     Verify: custom plan path taken, correct `planId` in payload.
   - **`test_run_custom_plan_not_ready`**: Plan fails readiness check, verify ValueError.

**Fixtures**: Mock custom plan matching pentest01 "CISA Alert AA24-190A (APT40)" structure.

**Changes**:

| File | Action | Description |
|------|--------|-------------|
| `safebreach_mcp_studio/tests/test_studio_functions.py` | Modify | Add custom plan tests |

**Git Commit**: `test(studio): add RED tests for custom plan run path`

---

### Phase 2.2: GREEN — Custom Plan Fetch + Run Implementation

**Semantic Change**: Implement custom plan fetching and extend `sb_run_scenario` to handle
custom plans.

**Implementation Details**:

1. **`_fetch_all_plans(console)`**
   - Same auth pattern as `_fetch_all_scenarios`
   - Base URL: `get_api_base_url(console, 'config')`
   - URL: `{base_url}/api/config/v2/accounts/{account_id}/plans?details=true`
   - Unwrap response: `response.json().get("data", [])`

2. **Extend `sb_run_scenario`** lookup logic:
   - After OOB lookup misses, fall through to `_fetch_all_plans(console)`
   - Match by `str(plan['id']) == scenario_id`
   - If found as custom plan: build minimal payload
     `{"plan": {"name": ..., "planId": plan['id'], "systemTags": []}}`
   - Same POST to queue API

**Verification**: All Slice 1 + Slice 2 unit tests pass.

**Changes**:

| File | Action | Description |
|------|--------|-------------|
| `safebreach_mcp_studio/studio_functions.py` | Modify | Add `_fetch_all_plans`, extend `sb_run_scenario` |

**Git Commit**: `feat(studio): add custom plan support to run_scenario (GREEN)`

---

### Phase 2.3: E2E Sign-off

**Semantic Change**: E2E tests confirming custom plan execution on pentest01.

**Implementation Details**:
- **`test_run_ready_custom_plan`**: Fetch plans from pentest01, find a ready-to-run one,
  execute, verify test_id returned.
- Extends existing E2E test file.

**Changes**:

| File | Action | Description |
|------|--------|-------------|
| `safebreach_mcp_studio/tests/test_e2e_run_scenario.py` | Modify | Add custom plan E2E tests |

**Git Commit**: `test(studio): add E2E tests for custom plan run against pentest01`

---

### Phase 2.4: Documentation Update

**Semantic Change**: Update CLAUDE.md to document custom plan support.

**Changes**:

| File | Action | Description |
|------|--------|-------------|
| `CLAUDE.md` | Modify | Document custom plan support in run_scenario |

**Git Commit**: `docs: update run_scenario docs with custom plan support`

---

## Slice 3: Non-ready OOB Scenario + Augmentation

**Goal**: Allow running OOB scenarios that are NOT ready-to-run by accepting augmenting
parameters that fill in missing filters. `compute_scenario_readiness` evolves to return
diagnostic info guiding the LLM on what's missing.

**Pre-requisite**: Slice 2 E2E sign-off passed.

**Note**: Exact parameter design and augmentation API will be refined when this slice
begins. User will provide sample payloads of non-ready scenarios with augmented fields.
The phases below describe intent; implementation details will be filled in after Slice 2.

### Phase 3.1: RED — Diagnostic Readiness + Augmentation Tests

**Semantic Change**: Tests for diagnostic readiness output and payload augmentation.

**Implementation Details**:
- Evolve `compute_scenario_readiness` tests to expect structured diagnostic output:
  per-step analysis of what's missing (which filter, what field)
- Test augmentation function that modifies scenario payload in-place with user-provided
  filter values (e.g., target simulator IDs, attacker role overrides)
- Test that augmented payload passes readiness check

**Git Commit**: `test(studio): add RED tests for diagnostic readiness and augmentation`

---

### Phase 3.2: GREEN — Diagnostic Readiness + Augmentation Implementation

**Semantic Change**: Implement diagnostic readiness and payload augmentation.

**Implementation Details**:
- `compute_scenario_readiness` returns structured result (not just bool):
  `{"ready": bool, "steps": [{"step_name": ..., "missing": ["targetFilter", ...]}]}`
- Augmentation function accepts override parameters and injects them into the scenario
  payload's step filters before relay
- `sb_run_scenario` gains optional augmentation parameters

**Git Commit**: `feat(studio): implement diagnostic readiness and augmentation (GREEN)`

---

### Phase 3.3: MCP Tool Parameter Extension

**Semantic Change**: Add augmenting parameters to the `run_scenario` MCP tool.

**Implementation Details**:
- Add parameters for filter overrides (exact shape TBD after Slice 2)
- Update tool description to document augmentation capabilities
- When augmenting params provided, skip readiness gate (user is filling the gaps)

**Git Commit**: `feat(studio): extend run_scenario tool with augmentation params`

---

### Phase 3.4: E2E Sign-off

**Semantic Change**: E2E test augmenting and running a non-ready OOB scenario on pentest01.

**Git Commit**: `test(studio): add E2E tests for non-ready OOB scenario augmentation`

---

### Phase 3.5: Documentation Update

**Git Commit**: `docs: update run_scenario docs with OOB augmentation support`

---

## Slice 4: Non-ready Custom Plan + Augmentation

**Goal**: Same augmentation capability for custom plans.

**Pre-requisite**: Slice 3 E2E sign-off passed.

**Note**: Custom plan augmentation may differ from OOB (plans use `planId` reference,
so augmentation may need a different approach — perhaps converting to full payload or
using a plan-specific augmentation endpoint). Details refined after Slice 3.

### Phase 4.1: RED — Custom Plan Augmentation Tests

**Git Commit**: `test(studio): add RED tests for custom plan augmentation`

### Phase 4.2: GREEN — Custom Plan Augmentation Implementation

**Git Commit**: `feat(studio): implement custom plan augmentation (GREEN)`

### Phase 4.3: E2E Sign-off

**Git Commit**: `test(studio): add E2E tests for non-ready custom plan augmentation`

### Phase 4.4: Documentation Update

**Git Commit**: `docs: update run_scenario docs with custom plan augmentation`

---

## Slice 5: Propagate Scenario Type

**Goal**: Support Propagate (ALM) scenarios in addition to Validate (BAS).

**Pre-requisite**: Slice 4 E2E sign-off passed.

**Note**: Propagate scenarios may use different queue API parameters or have different
step structures. Details refined after Slice 4.

### Phase 5.1: RED — Propagate Type Tests

**Git Commit**: `test(studio): add RED tests for Propagate scenario type`

### Phase 5.2: GREEN — Propagate Type Implementation

**Git Commit**: `feat(studio): implement Propagate scenario type support (GREEN)`

### Phase 5.3: E2E Sign-off

**Git Commit**: `test(studio): add E2E tests for Propagate scenario on pentest01`

### Phase 5.4: Documentation Update

**Git Commit**: `docs: update run_scenario docs with Propagate type support`

---

## 10. Risks and Assumptions

### Technical Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Queue API rejects relayed payload fields | Medium | Confirmed via pentest01 curl — full relay works |
| Custom plan augmentation differs from OOB | Medium | Deferred to Slice 4 design; user provides samples |
| Propagate scenarios need different queue params | Low | Deferred to Slice 5; E2E will validate |
| Scenario fetch returns stale data (no cache) | Low | Fresh fetch ensures latest definitions |
| Rate limiting on queue API | Low | Execution is infrequent |

### Assumptions
- The `x-apitoken` header is accepted by the orchestrator queue API.
  Studio's `sb_run_studio_attack()` already uses `x-apitoken` successfully.
- The content-manager API returns all scenarios in a single response (no server-side
  pagination). Confirmed on pentest01 (443 scenarios).
- OOB scenarios include all fields needed for the queue payload.
- The `originalScenarioId` field should be set to the scenario's `id` (UUID).
- Custom plans use `planId` reference — server already has the full plan stored.
- pentest01 has scenarios of every type needed for autonomous E2E testing.

## 11. Future Enhancements

- **Queue pre-flight check**: Call `GET /queue` before submitting to check slot
  availability and report estimated wait time.
- **Scenario caching in Studio**: Add `SafeBreachCache` if execution frequency increases.
- **Batch scenario execution**: Run multiple scenarios in sequence with rollup reporting.
- **Execution progress tracking**: Poll `get_test_details` and report progress inline.

## 12. Executive Summary

- **Issue**: AI agents can discover and inspect scenarios but cannot execute them
- **What Will Be Built**: `run_scenario` MCP tool in the Studio Server, delivered in 5
  elephant carpaccio slices: (1) ready-to-run OOB, (2) ready-to-run custom plans,
  (3) non-ready OOB with augmentation, (4) non-ready custom plans with augmentation,
  (5) Propagate scenario type. Each slice is E2E-gated against pentest01.
- **Key Technical Decisions**: Studio Server placement; pass-through relay design;
  `compute_scenario_readiness` duplicated for diagnostic evolution; elephant carpaccio
  delivery with per-slice E2E sign-off enabling fully autonomous development
- **Business Value**: Completes the discover→inspect→execute workflow for AI agents,
  progressing from simple ready-to-run execution to intelligent augmentation of
  incomplete scenarios

## 14. Change Log

| Date | Change Description |
|------|-------------------|
| 2026-04-18 10:00 | PRD created — initial draft with 7 monolithic phases |
| 2026-04-18 11:00 | Restructured to elephant carpaccio: 5 vertical slices with per-slice TDD + E2E gates |
