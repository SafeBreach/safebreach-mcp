# MCP Studio: Add `run_adhoc_scenario` Tool — SAF-31295

## 1. Overview

- **Title**: Add `run_adhoc_scenario` tool for ad-hoc attack execution
- **Task Type**: Feature
- **Purpose**: Enable AI agents to construct and execute ad-hoc test scenarios from explicit playbook
  attack IDs without requiring a pre-existing OOB or custom plan scenario
- **Target Consumer**: AI agents (LLMs) interacting with SafeBreach via the MCP Studio Server
- **Key Benefits**:
  1. Fills the gap between single-attack execution (`run_studio_attack`) and full scenario execution
     (`run_scenario`) — users can run arbitrary attack combinations on the fly
  2. Re-run historic simulations on exact simulators (per-attack UUID targeting)
  3. Mandatory dry-run preview prevents accidental combinatorial explosion
- **Business Alignment**: Extends the MCP platform's attack execution capabilities, enabling more
  flexible and ad-hoc security validation workflows for AI-powered agents
- **Originating Request**: SAF-31295

---

## 1.5. Document Status

| Field | Value |
|-------|-------|
| **PRD Status** | Complete |
| **Last Updated** | 2026-05-19 14:30 |
| **Owner** | Yossi Attas / AI Agent |
| **Current Phase** | N/A |

---

## 2. Solution Description

### Chosen Solution: Dedicated `run_adhoc_scenario` Tool

Create a new MCP tool on the Studio Server (Port 8004) that:
- Accepts a comma-separated list of playbook attack IDs
- Creates **one step per attack** (simplest possible step structure)
- Builds a **linear sequential DAG** (proven `run_scenario` pattern)
- Calls the statistics API for simulation count prediction
- Defaults to `dry_run=True` — the agent must get user confirmation before execution
- Supports `simulator_overrides` for per-attack simulator targeting
- Supports `all_connected` as a global override

### Alternatives Considered

**Alternative A: Extend `run_scenario`**
- Add `attack_ids` parameter to the existing tool, making `scenario_id` optional
- **Pros**: Single tool, shared code
- **Cons**: `run_scenario` is already the most complex tool (66-line description, 3.9x average).
  Conditional parameters, dual interaction patterns (3-turn vs 2-turn), and description bloat
  would degrade LLM reliability. Rejected.

**Alternative B: Phase-based step grouping (7 groups)**
- Classify attacks by attacker role requirement and group into steps by phase
  (host, infil, exfil, AWS, Azure, GCP, webapp)
- **Pros**: Targeted filters per step, potentially fewer steps
- **Cons**: Complex classification logic with fallback chains. Attack phase metadata is not
  reliably available in the playbook API. Step-level filtering doesn't affect simulation counts
  (per-attack constraints handle matching regardless of grouping). Rejected in favor of
  one-attack-per-step simplicity.

**Alternative C: Parallel fan-out DAG**
- All steps start concurrently from the entry node instead of sequential execution
- **Pros**: Faster execution for many attacks
- **Cons**: Validated at API level (accepted, RUNNING, cancellable) but completion not verified
  in experiments due to console load. Deferred as future optimization. Linear DAG is proven
  and reliable.

### Decision Rationale

One-attack-per-step + linear DAG + dedicated tool provides:
1. Zero classification logic (no phase heuristics, no fallback chains)
2. Trivial `simulator_overrides` mapping (attack ID = step)
3. Clean separation from `run_scenario` (different interaction pattern, different user intent)
4. Proven DAG topology already in production
5. Target tool complexity: 6 params, ~30-line description (well within baseline)

---

## 3. Core Feature Components

### Component A: `sb_run_adhoc_scenario` Business Logic

**Purpose**: New function in `studio_functions.py` that constructs and executes ad-hoc scenarios.
This is the core business logic — no MCP framework dependencies.

**Key Features**:
- Parse and validate attack IDs against the playbook cache
- Construct one step per attack with `attacksFilter.playbook` containing the single attack ID
- Apply default filters: `connection: all_connected` for both target and attacker
- Apply `simulator_overrides` when provided — replace target/attacker filters for specific attacks
- Apply `all_connected=True` global override — ignore all overrides, use connection filter
- Build linear sequential DAG (actions + edges) using the extracted shared helper
- Call statistics API for simulation count prediction per step
- On `dry_run=True` (default): return prediction without queuing
- On `dry_run=False`: validate (total > 0), submit to queue API, return test_id
- Partial execution: skip 0-sim steps on real run (user already saw dry_run preview)
- Rate limiting: `check_limit` before queue POST, `record_action` after success

**Function signature**:
```
sb_run_adhoc_scenario(
    attack_ids: str,
    console: str = "default",
    test_name: str = None,
    all_connected: bool = False,
    simulator_overrides: str = None,
    dry_run: bool = True,
) -> Dict[str, Any]
```

### Component B: `run_adhoc_scenario` MCP Tool Wrapper

**Purpose**: Register the tool on the Studio Server with annotations, description, and Markdown
response formatting. Thin wrapper over Component A.

**Key Features**:
- Tool registration with `readOnlyHint=False`, `destructiveHint=True`
- ~30-line tool description (clear, focused, no conditional semantics)
- Single-tenant console auto-resolve (same pattern as `run_scenario`)
- Markdown formatting for two response modes:
  - `dry_run` preview: per-step attack name, simulation count, flagged 0-sim attacks
  - `queued` response: test_id, step count, predicted sims, next-steps guidance
- Error formatting for ValueError and API errors

### Component C: Shared Helper Extraction

**Purpose**: Extract duplicated queue submission and DAG generation logic from `sb_run_scenario`
and `sb_run_studio_attack` into shared helpers. The new tool becomes the third consumer.

**Key Features**:
- `_submit_to_queue(payload, console, query_params)`: Handles POST to queue API, error checking,
  response extraction, RBAC check. Used by `run_scenario`, `run_studio_attack`, and
  `run_adhoc_scenario`.
- `_build_linear_dag(steps)`: Generate sequential actions + edges from a list of steps.
  Used by `run_scenario` and `run_adhoc_scenario`.
- Refactor existing callers to use the shared helpers (no behavior change).

---

## 4. API Endpoints and Integration

### Existing APIs to Consume

**Statistics API** (prediction):
- **URL**: `POST /api/orch/v1/accounts/{account_id}/plan/statistics?limit=500000&includeDisabled=true`
- **Headers**: `Content-Type: application/json`, `x-apitoken: {token}`
- **Request**: `{"name": "", "steps": [...]}`
- **Response**: `{"data": {"steps": [{"simulationCount": N, "targetSimulators": {...},
  "attackerSimulators": {...}, "moves": {...}, "simulatorConstraints": {...}}]}}`

**Queue API** (execution):
- **URL**: `POST /api/orch/v4/accounts/{account_id}/queue?enableFeedbackLoop=true&retrySimulations=true`
- **Headers**: `Content-Type: application/json`, `x-apitoken: {token}`
- **Request**: `{"plan": {"name": "...", "steps": [...], "systemTags": [], "actions": [...], "edges": [...]}}`
- **Response**: `{"data": {"planRunId": "...", "name": "...", "steps": [{"stepRunId": "..."}]}}`
- **Note**: Do NOT use `"draft": True` (that is for studio draft attacks only)

**Playbook API** (attack validation, via direct Python import):
- **Source**: `safebreach_mcp_playbook.playbook_functions._get_all_attacks_from_cache_or_api(console)`
- **Purpose**: Validate attack IDs exist, resolve attack names for display
- **Cache**: 30-min TTL, per-console

---

## 5. Example Customer Flow

### Primary Scenario: Ad-hoc attack test with dry-run preview

**Entry Point**: AI agent conversation (e.g., "Run attacks 8849 and 217 on my Windows machines")

1. Agent identifies attack IDs from user request (may use `get_playbook_attacks` first)
2. Agent calls `run_adhoc_scenario(attack_ids="8849,217", console="demo")`
3. Tool validates both IDs exist in playbook — constructs 2 steps
4. Tool calls statistics API — predicts 10 sims for step 1, 8 sims for step 2
5. Tool returns dry-run preview (Markdown) to the agent
6. Agent presents preview to user: "This will run 2 attacks producing 18 simulations. Proceed?"
7. User confirms
8. Agent calls `run_adhoc_scenario(attack_ids="8849,217", console="demo", dry_run=False)`
9. Tool submits to queue API — returns test_id
10. Agent reports: "Test queued (test_id: 1779188...). Use get_test_details to track progress."

### Alternative Scenario: Per-attack simulator override (rerun)

1. User: "Rerun attack 8849 on simulator sim-abc-123"
2. Agent calls: `run_adhoc_scenario(attack_ids="8849", simulator_overrides='{"8849": {"target":
   ["sim-abc-123"], "attacker": ["sim-abc-123"]}}', console="demo")`
3. Dry-run shows 1 simulation — user confirms — agent calls with `dry_run=False`

### Alternative Scenario: All-connected override

1. User: "Run attacks 100, 200, 300 on all connected simulators"
2. Agent calls: `run_adhoc_scenario(attack_ids="100,200,300", all_connected=True, console="demo")`
3. Dry-run shows high sim count — user reviews and confirms or adjusts

### Edge Case: Some attacks produce 0 simulations

1. Dry-run shows attack 300 has 0 sims (no compatible simulator)
2. User reviews and calls with `dry_run=False` anyway
3. Tool executes attacks 100 and 200 (skips 300), reports which were skipped

### Edge Case: All attacks produce 0 simulations

1. Dry-run shows all 0 — tool refuses with clear error when `dry_run=False` is called

---

## 6. Non-Functional Requirements

### Code Reuse

- Extract `_submit_to_queue()` and `_build_linear_dag()` as shared helpers
- Reuse `_get_scenario_statistics()`, `_summarize_constraints()`,
  `_build_attack_name_map()`, `CONSTRAINT_REASON_DESCRIPTIONS`
- Cross-server import from `safebreach_mcp_playbook` for attack validation (existing pattern)

### Performance Requirements

- Statistics API adds ~2-5s latency per call (acceptable — same as `run_scenario`)
- Attack validation via playbook cache: O(n) lookup against cached list (30-min TTL)
- Tool description target: ~30 lines (half of `run_scenario`'s 66) for better LLM reliability

### Technical Constraints

- **Backward Compatibility**: No changes to existing tool interfaces. Helper extraction is a
  refactor with no behavior change.
- **Rate Limiting**: Must follow existing two-phase gate pattern (`check_limit` / `record_action`).
  Tool name: `"run_adhoc_scenario"`.
- **DAG Topology**: Linear sequential (same as `run_scenario`). Parallel fan-out deferred.

---

## 7. Definition of Done

**Core Functionality**:
- [ ] `run_adhoc_scenario` tool registered on Studio Server (Port 8004)
- [ ] Accepts comma-separated attack IDs, validates all exist in playbook cache
- [ ] Constructs one step per attack with `attacksFilter.playbook` filter
- [ ] Default filters: `connection: all_connected` for both target and attacker
- [ ] `simulator_overrides` replaces filters for specific attack steps
- [ ] `all_connected=True` overrides all selection with connection filter
- [ ] `dry_run=True` (default) returns preview with per-step simulation counts
- [ ] `dry_run=False` submits to queue API and returns test_id + step_run_ids
- [ ] Partial execution: skips 0-sim steps, hard-refuses if total is 0
- [ ] Rate limiting gates: check before POST, record after success, dry-run exempt
- [ ] Markdown response formatting for dry_run and queued modes

**Shared Helpers**:
- [ ] `_submit_to_queue()` extracted and used by all three queue-posting tools
- [ ] `_build_linear_dag()` extracted and used by `run_scenario` and `run_adhoc_scenario`
- [ ] Existing `run_scenario` and `run_studio_attack` refactored to use helpers (no behavior change)

**Quality Gates**:
- [ ] Unit tests covering: attack validation, step construction, filter defaults, simulator_overrides,
  all_connected, dry_run response, execution response, partial execution, rate limiting gates
- [ ] Unit tests for extracted shared helpers
- [ ] Existing tests for `run_scenario` and `run_studio_attack` still pass after refactor
- [ ] E2E test against real console
- [ ] All cross-server tests pass (`uv run pytest ... -m "not e2e"`)

---

## 8. Testing Strategy

**Approach: Test-Driven Development (TDD)**

Tests are written BEFORE implementation in each phase (Phases 1-5). Each phase's commit
includes both the failing tests and the implementation that makes them pass.

### Unit Testing

**Scope**: `safebreach_mcp_studio/tests/test_studio_functions.py`
**Framework**: pytest with unittest.mock (same as existing tests)
**Coverage Target**: Maintain existing coverage level

**Test distribution across TDD phases**:

| Phase | Test Focus | Approximate Test Count |
|-------|-----------|----------------------|
| Phase 1 | `_build_linear_dag`, `_submit_to_queue`, existing test regression | ~10 |
| Phase 2 | Input parsing, attack ID validation, step construction | ~12 |
| Phase 3 | `simulator_overrides`, `all_connected`, filter precedence | ~8 |
| Phase 4 | Statistics, dry-run, execution, partial execution, rate limiting | ~12 |
| Phase 5 | Tool registration, Markdown formatting, error handling | ~8 |

**Total estimated**: ~50 new unit tests

### Integration / E2E Testing

**Scope**: `safebreach_mcp_studio/tests/test_e2e_run_adhoc_scenario.py` (Phase 6)
**Test Environment**: pentest01 console (same as existing E2E tests)
**Pattern**: Queue → verify → cancel (same as `test_e2e_run_scenario.py`)

E2E tests are NOT TDD — they validate the full stack against real infrastructure after
all unit-tested phases are complete.

---

## 9. Implementation Phases

**Approach: Test-Driven Development (TDD)**

Each phase follows the Red-Green-Refactor cycle:
1. **Red**: Write failing tests that define the expected behavior
2. **Green**: Write the minimal implementation to make tests pass
3. **Refactor**: Clean up while keeping tests green

Tests and implementation are committed together per phase — the tests define the contract,
the implementation fulfills it.

| Phase | Status | Completed | Commit SHA | Notes |
|-------|--------|-----------|------------|-------|
| Phase 1: Shared helpers (TDD) | ✅ Complete | 2026-05-19 | 75ee1e3 | 15 tests |
| Phase 2: Input validation & step construction (TDD) | ✅ Complete | 2026-05-19 | a420cf2 | 18 tests |
| Phase 3: Simulator overrides & all_connected (TDD) | ✅ Complete | 2026-05-19 | fdd4ada | 10 tests |
| Phase 4: Statistics, dry-run & execution (TDD) | ✅ Complete | 2026-05-19 | - | 13 tests |
| Phase 5: MCP tool wrapper (TDD) | ✅ Complete | 2026-05-19 | - | 7 tests |
| Phase 6: E2E tests | ✅ Complete | 2026-05-19 | - | 4 tests, all pass on pentest01 |
| Phase 7: Documentation updates | ✅ Complete | 2026-05-19 | - | |

### Phase 1: Shared Helpers (TDD)

**Semantic Change**: Extract duplicated queue submission and DAG generation into shared helpers.

**Red — Write tests first**:

1. **`_build_linear_dag` tests**:
   - 1 step: returns 1 action (multiAttack), 1 edge (entry), no wait actions
   - 2 steps: returns 2 multiAttack + 1 wait action, edges chain step1 → wait → step2
   - 3 steps: returns 3 multiAttack + 2 wait actions, correct edge chain
   - Step without UUID: verify UUID is auto-generated (non-empty string)
   - Verify action IDs: multiAttack ids are 1-indexed, wait ids start at 1001

2. **`_submit_to_queue` tests**:
   - Success: mock POST returns 200, verify returns parsed JSON
   - HTTP error (400+): verify logs error body, raises via `check_rbac_response`
   - Network error: verify `RequestException` propagates
   - Custom query_params: verify they're passed through (e.g., `retrySimulations=false`)
   - Default query_params: verify `enableFeedbackLoop=true`, `retrySimulations=true`

3. **Refactor verification**: Existing `run_scenario` and `run_studio_attack` tests must still
   pass after swapping inline code for helper calls

**Green — Implement helpers + refactor existing callers**:

1. **`_build_linear_dag(steps)`** in `studio_functions.py`:
   - Accept list of step dicts, auto-generate UUIDs for steps missing them
   - Generate multiAttack actions (id = step index + 1) referencing step UUIDs
   - Generate wait actions (id = 1001+i, seconds=0) between consecutive steps
   - Generate edges: entry `{to: 1}`, then `step_i → wait_i → step_{i+1}` chain
   - Return `(actions, edges)` tuple

2. **`_submit_to_queue(payload, console, query_params=None)`** in `studio_functions.py`:
   - Default query_params: `{"enableFeedbackLoop": "true", "retrySimulations": "true"}`
   - Construct URL, POST with headers + auth, timeout=120
   - Log and raise on HTTP errors, return `response.json()` on success
   - No rate limiting inside (callers manage their own gates)

3. **Refactor `sb_run_scenario`**: Replace inline DAG generation (~lines 2492-2530) and inline
   queue POST (~lines 2547-2567) with helper calls

4. **Refactor `sb_run_studio_attack`**: Replace inline queue POST (~lines 1179-1193) with
   `_submit_to_queue()` call, passing `{"retrySimulations": "false"}` as query_params

**Changes**:

| File | Change |
|------|--------|
| `safebreach_mcp_studio/tests/test_studio_functions.py` | Add tests for `_build_linear_dag` and `_submit_to_queue` |
| `safebreach_mcp_studio/studio_functions.py` | Add helpers, refactor existing callers |

**Git Commit**: `refactor: extract shared queue and DAG helpers with TDD (SAF-31295)`

---

### Phase 2: Input Validation & Step Construction (TDD)

**Semantic Change**: Implement attack ID validation and one-step-per-attack construction.

**Red — Write tests first**:

1. **Input parsing tests**:
   - `"8849,217,1071"` → parsed as `[8849, 217, 1071]`
   - `" 8849 , 217 "` → whitespace stripped, parsed correctly
   - `""` or `None` → raises ValueError ("attack_ids is required")
   - `"8849,abc,217"` → raises ValueError ("invalid integer")
   - `"8849,,217"` → handles empty segments gracefully

2. **Attack ID validation tests** (mock playbook cache):
   - All IDs valid: proceeds without error
   - Some IDs invalid: raises ValueError listing the invalid IDs
   - All IDs invalid: raises ValueError listing all
   - Playbook cache import failure: graceful degradation (names unavailable but IDs still work)

3. **Step construction tests**:
   - 3 valid attacks → 3 steps, each with correct `attacksFilter.playbook.values = [single_id]`
   - Each step has `name` = attack name from playbook (or "Attack {id}" fallback)
   - Each step has `uuid` (non-empty string)
   - Default `targetFilter` = `{connection: {operator: "is", values: [true], name: "connection"}}`
   - Default `attackerFilter` = same connection filter
   - Each step has empty `systemFilter: {}`

**Green — Implement the function skeleton**:

1. Create `sb_run_adhoc_scenario()` in `studio_functions.py` with input parsing, attack validation
   via playbook cache import, and step construction logic
2. Function returns steps at this point — later phases add statistics/queue logic
3. For now, if `dry_run=True` (default), return early with constructed steps for test verification

**Changes**:

| File | Change |
|------|--------|
| `safebreach_mcp_studio/tests/test_studio_functions.py` | Add validation and step construction tests |
| `safebreach_mcp_studio/studio_functions.py` | Add `sb_run_adhoc_scenario` skeleton with validation + step construction |

**Git Commit**: `feat: add attack validation and step construction with TDD (SAF-31295)`

---

### Phase 3: Simulator Overrides & all_connected (TDD)

**Semantic Change**: Add per-attack simulator override and global all_connected support.

**Red — Write tests first**:

1. **`simulator_overrides` tests**:
   - Single override: attack 8849 gets custom target + attacker filters, others keep defaults
   - Override with `target` only: attackerFilter inferred as same as targetFilter
   - Override with both `target` and `attacker`: both filters replaced
   - Multiple overrides: each attack's step gets its own filters
   - Override for non-existent attack ID: raises ValueError
   - Invalid JSON: raises ValueError
   - Verify filter structure: `{"simulators": {"operator": "is", "values": [...], "name": "simulators"}}`

2. **`all_connected=True` tests**:
   - All steps get connection filter (already default — verify no change)
   - `simulator_overrides` provided BUT `all_connected=True` → overrides ignored,
     connection filter on all steps
   - Verify precedence: `all_connected` wins over `simulator_overrides`

**Green — Implement override logic**:

1. Parse `simulator_overrides` JSON string (fail-fast on bad JSON)
2. After step construction, if `all_connected=True`: skip override application (defaults are
   already connection filter)
3. If `simulator_overrides` provided: iterate entries, find matching step by attack ID,
   replace targetFilter and attackerFilter. If only `target` in override, set
   attackerFilter = same as targetFilter. Validate override attack IDs exist in the attack list.

**Changes**:

| File | Change |
|------|--------|
| `safebreach_mcp_studio/tests/test_studio_functions.py` | Add override and all_connected tests |
| `safebreach_mcp_studio/studio_functions.py` | Add override application logic to `sb_run_adhoc_scenario` |

**Git Commit**: `feat: add simulator overrides and all_connected with TDD (SAF-31295)`

---

### Phase 4: Statistics, Dry-Run & Execution (TDD)

**Semantic Change**: Add statistics pre-flight, dry-run preview, queue submission, partial
execution, and rate limiting.

**Red — Write tests first**:

1. **Dry-run tests** (mock statistics API):
   - `dry_run=True` (default): statistics API called, queue API NOT called, rate limit NOT triggered
   - Response contains `status='dry_run'`, per-step simulation counts, total predicted,
     empty steps list, attack names
   - Statistics returns some 0-sim steps: flagged in response

2. **Execution tests** (mock statistics + queue APIs):
   - `dry_run=False`: statistics called, then queue API called, rate limit triggered
   - Response contains `status='queued'`, test_id, step_run_ids, predicted counts
   - Total predicted = 0: raises ValueError, queue NOT called
   - Partial execution: 3 attacks, 1 has 0 sims → queue payload contains only 2 steps,
     response lists skipped attack
   - DAG rebuilt for remaining steps via `_build_linear_dag`

3. **Rate limiting tests**:
   - `check_limit` called BEFORE queue POST
   - `record_action` called AFTER successful queue POST
   - `dry_run=True`: neither `check_limit` nor `record_action` called
   - Queue POST fails: `record_action` NOT called (exception propagates)

4. **Test name tests**:
   - Custom `test_name` provided: used in queue payload
   - No `test_name`: auto-generated default (e.g., "Ad-hoc Test - {timestamp}" or similar)

**Green — Implement remaining logic**:

1. Statistics pre-flight: call `_get_scenario_statistics(steps, console, include_constraints=dry_run)`
2. Dry-run path: return prediction dict without queuing
3. Execution path: validate total > 0, filter out 0-sim steps, rebuild DAG, rate-limit gates,
   call `_submit_to_queue`, extract test_id/step_run_ids from response
4. Build response dicts for both modes

**Changes**:

| File | Change |
|------|--------|
| `safebreach_mcp_studio/tests/test_studio_functions.py` | Add statistics, dry-run, execution, rate limiting tests |
| `safebreach_mcp_studio/studio_functions.py` | Complete `sb_run_adhoc_scenario` with statistics/queue/rate-limit logic |

**Git Commit**: `feat: add statistics, dry-run, execution and rate limiting with TDD (SAF-31295)`

---

### Phase 5: MCP Tool Wrapper (TDD)

**Semantic Change**: Register `run_adhoc_scenario` as an MCP tool with Markdown response formatting.

**Red — Write tests first**:

1. **Tool registration tests**:
   - Verify tool is registered with name `run_adhoc_scenario`
   - Verify annotations: `readOnlyHint=False`, `destructiveHint=True`
   - Verify all parameters are exposed (attack_ids, console, test_name, all_connected,
     simulator_overrides, dry_run)

2. **Markdown formatting tests** (mock `sb_run_adhoc_scenario`):
   - Dry-run response: contains "Dry Run Preview", per-step attack names + sim counts,
     0-sim warnings, "No test was queued" footer
   - Queued response: contains "Ad-hoc Scenario Queued", test_id, step count, predicted sims,
     next-steps guidance with `get_test_details`
   - Partial execution: contains list of skipped attacks
   - ValueError: returns "Error:" prefixed message
   - Exception: returns "Error running ad-hoc scenario:" prefixed message

3. **Single-tenant auto-resolve test**: verify console name resolution when `safebreach_envs`
   is empty (same pattern as `run_scenario` wrapper)

**Green — Implement wrapper**:

1. Tool registration with `@self.mcp.tool()` decorator, annotations, ~30-line description
2. Single-tenant auto-resolve (same pattern as `run_scenario`)
3. Call `sb_run_adhoc_scenario()`, format response as Markdown based on `status` field
4. Error handling: catch ValueError and Exception, return formatted error strings

**Changes**:

| File | Change |
|------|--------|
| `safebreach_mcp_studio/tests/test_studio_functions.py` | Add wrapper formatting and registration tests |
| `safebreach_mcp_studio/studio_server.py` | Add `run_adhoc_scenario` tool registration and Markdown formatting |
| `safebreach_mcp_studio/studio_server.py` | Add import for `sb_run_adhoc_scenario` |

**Git Commit**: `feat: register run_adhoc_scenario MCP tool with TDD (SAF-31295)`

---

### Phase 6: E2E Tests

**Semantic Change**: Add end-to-end tests against a real SafeBreach console.

**Deliverables**: E2E test file verifying real API integration. These tests are not TDD
(they validate the full stack against real infrastructure).

**Implementation Details**:

1. **Test setup**: Same pattern as `test_e2e_run_scenario.py` — use `E2E_CONSOLE` env var,
   `@skip_e2e` and `@pytest.mark.e2e` decorators, cleanup in `finally` blocks

2. **Attack IDs**: Use the following 5 verified attacks on pentest01:
   `11653, 11662, 7207, 11663, 11622` — all have applicable simulators that produce simulations.

3. **Test cases**:
   - Dry-run with all 5 attacks: verify `status='dry_run'`, `predicted_simulations > 0`
   - Dry-run with subset (2-3 attacks): verify per-step counts
   - Queue and cancel: call with `dry_run=False` using 2 attacks, verify test_id returned,
     cancel via orchestrator DELETE API
   - Invalid attack ID mixed with valid: verify ValueError raised

4. **Cleanup**: Cancel any queued tests, add comment via data API

**Changes**:

| File | Change |
|------|--------|
| `safebreach_mcp_studio/tests/test_e2e_run_adhoc_scenario.py` | New E2E test file |

**Git Commit**: `test: add E2E tests for run_adhoc_scenario (SAF-31295)`

---

### Phase 7: Documentation Updates

**Semantic Change**: Update CLAUDE.md and JIRA ticket with the new tool documentation.

**Deliverables**: Updated documentation reflecting the new tool.

**Implementation Details**:

1. **CLAUDE.md updates**:
   - Add `run_adhoc_scenario` to Studio Server tool list (tool #23)
   - Add tool description with parameters, interaction flow, examples
   - Update rate limiting table with new tool entry
   - Update "MCP Tools Available" count

2. **JIRA ticket**: Add comment confirming completion

**Changes**:

| File | Change |
|------|--------|
| `CLAUDE.md` | Add `run_adhoc_scenario` documentation |

**Git Commit**: `docs: add run_adhoc_scenario to CLAUDE.md (SAF-31295)`

---

## 10. Risks and Assumptions

### Technical Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Sequential DAG slower for many attacks | Medium | Acceptable for now; parallel DAG deferred as future optimization |
| Cross-server playbook import fails | Low | Graceful degradation (same as `_build_attack_name_map`) — names shown as IDs |
| Statistics API latency with many steps | Low | Each step is one attack — API handles multi-step payloads already |

### Assumptions

- The queue API accepts payloads with many single-attack steps (validated in experiments up to 3)
- The `playbook` key in `attacksFilter` accepts integer attack IDs (validated in `run_studio_attack`)
- Attack IDs from the playbook API are stable identifiers (not UUIDs that change)
- The statistics API `simulationCount` is an accurate predictor of actual execution

---

## 11. Future Enhancements

- **Parallel fan-out DAG**: Switch to concurrent step execution once completion is verified
  (API-level validation already done — see experiments/)
- **Persist as custom plan**: Save ad-hoc scenarios for future reuse
- **MITRE technique input**: Accept T1046-style IDs and resolve to playbook attack IDs
- **Criteria-based selection**: Accept attack type, tags, MITRE tactics instead of explicit IDs
- **Phase-based grouping**: Optionally group attacks by role for more targeted filters

---

## 12. Executive Summary

- **Issue/Feature Description**: AI agents cannot construct ad-hoc test scenarios from arbitrary
  attack combinations — they can only run pre-existing scenarios or single draft attacks
- **What Was Built**: A new `run_adhoc_scenario` MCP tool that constructs multi-step scenarios
  from explicit playbook attack IDs with mandatory dry-run preview, per-attack simulator overrides,
  and statistics-informed validation
- **Key Technical Decisions**: (1) Dedicated tool instead of extending `run_scenario` to avoid
  LLM complexity thresholds, (2) One attack per step for zero-classification simplicity,
  (3) Linear sequential DAG (proven pattern) with parallel DAG deferred,
  (4) Shared helper extraction to reduce ~150 lines of queue/DAG duplication
- **Business Value Delivered**: Fills the gap between single-attack and full-scenario execution,
  enables re-running historic simulations, and provides mandatory dry-run preview as a safety net

---

## 14. Change Log

| Date | Change Description |
|------|-------------------|
| 2026-05-19 14:30 | PRD created — initial draft |
| 2026-05-19 14:45 | Restructured implementation phases to TDD approach (Red-Green-Refactor) |
| 2026-05-19 15:00 | Added verified E2E attack IDs: 11653, 11662, 7207, 11663, 11622 |
| 2026-05-19 17:30 | All 7 phases implemented. Added tool disambiguation hints, hint_to_agent responses |
| 2026-05-19 17:45 | Improved simulator_overrides discoverability based on agent session feedback |
| 2026-05-19 18:10 | Fixed E2E simulator override for 11622 (NEDR01 offline, switched to pz-noedr) |
| 2026-05-19 18:15 | Fixed data server E2E fixtures: filter for completed tests + sims with logs |
