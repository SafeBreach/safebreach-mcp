# Improve run_scenario Tool Usability — SAF-30319

## 1. Overview

- **Task Type**: Feature improvement + documentation
- **Purpose**: Improve the `run_scenario` MCP tool's usability for LLM agents by addressing
  undocumented filter schemas, unreliable default key behavior, missing attack count data,
  and opaque API error messages.
- **Target Consumer**: LLM agents (Helm in-console AI agent, Claude, and other MCP clients)
- **Key Benefits**:
  - Agents discover correct filter format on first attempt instead of 5+ dry-run iterations
  - API errors include actionable context instead of generic "400 Client Error"
  - Scenario listing includes attack count for informed scenario selection
- **Business Alignment**: Improves AI agent efficiency and reduces time-to-value for
  SafeBreach MCP integrations
- **Originating Request**: SAF-30319 — candid feedback from Helm (in-console AI agent)

---

## 1.5. Document Status

| Field | Value |
|-------|-------|
| **PRD Status** | Draft |
| **Last Updated** | 2026-04-23 14:45 |
| **Owner** | Yossi Attas |
| **Current Phase** | N/A |

---

## 2. Solution Description

### Chosen Solution

Address 4 of the 5 reported usability issues (issue #3 deferred) through documentation
improvements, error handling enhancements, and data enrichment:

1. **Documentation improvement** (Issues #1+#2): Add complete filter schema with all valid
   values in both the tool description and diagnostic `hint_to_agent` responses. Document
   the "default" key feature including its limitations.
2. **Error propagation** (Issue #5): Mirror the queue API's error handling pattern — log
   `response.text` before `raise_for_status()` and include API response body in propagated
   error messages.
3. **Data enrichment** (Issue #4): Add `total_attack_count` field to scenario listing with
   a conditional `hint_to_agent` explaining that accurate counts require `dry_run=True`.

### Alternatives Considered

| Alternative | Pros | Cons | Decision |
|------------|------|------|----------|
| Add pre-flight filter validation (Issue #1) | Catches errors before API call | May reject valid formats we don't know about; adds maintenance burden | Deferred — docs-only approach chosen |
| Fix default key partial-step behavior (Issue #2) | More intuitive behavior | Risk of breaking existing workflows; complex merge logic | Document current behavior instead |
| Enrich simulator UUIDs with connection status (Issue #3) | Prevents stale UUID usage | Extra API call per request; cross-server enrichment challenge | Deferred to separate ticket |
| Parse and translate statistics errors (Issue #5) | Better UX | Fragile if API error format changes | Mirror queue API pattern instead — simpler, proven |

### Decision Rationale

Docs-only for filter schema avoids the risk of being too strict with validation while still
solving the core problem (agents don't know the format). Mirroring the queue API error pattern
is minimal code change with proven reliability. Deferring issue #3 keeps scope focused.

---

## 3. Core Feature Components

### Component A: step_overrides Documentation Enhancement

**Purpose**: Update existing tool description and diagnostic responses to include complete
filter schema documentation, including the "default" key feature.

**Key Features**:
- Add concise filter schema reference to the `run_scenario` tool description in `studio_server.py`
  with all valid filter types, operator, values, and the `name` field requirement
- Add the "default" key documentation to the tool description, explaining that it applies
  overrides to all steps identified as missing filters (with limitation note about partially-ready steps)
- Enhance diagnostic `hint_to_agent` in not-ready responses to include detailed filter examples
  with all valid values per filter type (OS, role, simulators, connection)
- Include valid role values: isInfiltration, isExfiltration, isAWSAttacker, isAzureAttacker,
  isGCPAttacker, isWebApplicationAttacker
- Include valid OS values: WINDOWS, MAC, LINUX, DOCKER, NETWORK (target); WINDOWS, MAC, LINUX,
  DOCKER (attacker)

### Component B: Statistics API Error Propagation

**Purpose**: Modify existing error handling to propagate API response body in error messages,
following the queue API's proven pattern.

**Key Features**:
- Add `response.text` logging before `raise_for_status()` in `_get_scenario_statistics()`
- Wrap statistics API call in try/except to capture and log response body on HTTP errors
- Include response body content in the error message propagated to the user
- Apply the same pattern to other API calls in `studio_functions.py` that use raw
  `raise_for_status()` (scenario fetch at line 1932, plan fetch at line 1958)

### Component C: Attack Count in Scenario Listing

**Purpose**: Add `total_attack_count` field to scenario listing to enable attack-count-based
scenario selection without requiring full detail fetches.

**Key Features**:
- Add `total_attack_count` field to `get_reduced_scenario_mapping()` in `config_types.py`
- Compute by summing `len(step.attacksFilter.playbook.values)` across all steps
- For criteria-based steps (no explicit playbook IDs), mark count as indeterminate (None or -1)
- Add conditional `hint_to_agent` in `get_scenarios` response when any scenario has
  indeterminate count, explaining that accurate counts can be determined via
  `run_scenario` with `dry_run=True`

---

## 4. API Endpoints and Integration

*Omitted — no new API creation. Changes affect MCP tool descriptions and internal error
handling for existing SafeBreach backend API calls.*

---

## 6. Non-Functional Requirements

### Technical Constraints

- **No inter-server communication**: Studio and Config servers call backend APIs independently.
  Changes to scenario listing (Component C) are in config server; changes to error handling
  (Component B) and docs (Component A) are in studio server.
- **Backward compatibility**: All changes are additive — new fields in responses, improved
  error messages, expanded documentation. No breaking changes to existing MCP tool signatures.
- **Caching**: Scenario listing cache (30-min TTL) will include the new `total_attack_count`
  field. No cache invalidation changes needed.

---

## 7. Definition of Done

- [ ] `run_scenario` tool description includes complete filter schema with all valid filter types,
  operators, values, and the `name` field requirement
- [ ] `run_scenario` tool description documents the "default" key feature with behavior explanation
  and limitation note about partially-ready steps
- [ ] Diagnostic `hint_to_agent` for not-ready scenarios includes detailed filter examples with
  all valid values per filter type
- [ ] Statistics API errors log `response.text` and include response body in user-facing error messages
- [ ] Same error handling pattern applied to scenario fetch and plan fetch API calls
- [ ] Scenario listing includes `total_attack_count` field
- [ ] Conditional `hint_to_agent` added for indeterminate attack counts
- [ ] All existing unit tests pass
- [ ] New unit tests cover: error propagation from statistics API, `total_attack_count` computation
  (playbook-based and criteria-based scenarios)
- [ ] CLAUDE.md updated to reflect new `total_attack_count` field and improved error handling

---

## 8. Testing Strategy

### Approach: TDD with E2E Tests (Zero Mocks)

Each implementation phase includes its own E2E tests written BEFORE the implementation code.
Tests run against real SafeBreach environments using the existing E2E infrastructure
(`E2E_CONSOLE` env var, `@pytest.mark.e2e` decorator).

### E2E Test Scenarios

**Phase 2 — Error Propagation**:
- Call `run_scenario` with intentionally malformed step_overrides → verify error response
  contains API error body details (not just "400 Client Error")
- Call with invalid scenario ID → verify error contains API-originated details
- Verify error string contains specific content from the backend API response

**Phase 3 — Attack Count**:
- Call `get_scenarios` → verify each scenario has `total_attack_count` field (int or None)
- Cross-validate: fetch scenario detail, sum playbook_ids, compare with listing count
- Verify conditional `hint_to_agent` appears when indeterminate counts exist

**Framework**: pytest with `@pytest.mark.e2e` (existing project standard)
**Test Environment**: Real SafeBreach console via `E2E_CONSOLE` env var
**Coverage**: Tests delivered with each phase, not batched separately

---

## 9. Implementation Phases

| Phase | Status | Completed | Commit SHA | Notes |
|-------|--------|-----------|------------|-------|
| Phase 1: step_overrides documentation | ⏳ Pending | - | - | |
| Phase 2: Statistics API error propagation (TDD) | ⏳ Pending | - | - | |
| Phase 3: Attack count in scenario listing (TDD) | ⏳ Pending | - | - | |
| Phase 4: CLAUDE.md update | ⏳ Pending | - | - | |

### Phase 1: step_overrides Documentation Enhancement

**Semantic Change**: Improve filter schema documentation in tool description and diagnostic responses

**Deliverables**:
- Updated `run_scenario` tool description with complete filter schema
- "default" key documentation in tool description
- Enhanced `hint_to_agent` in diagnostic responses with detailed filter examples

**Implementation Details**:

1. **Update tool description in `studio_server.py`** (around lines 1009-1131):
   - In the `step_overrides` parameter documentation section, add a complete filter schema
     reference block that shows the required structure:
     `{filter_type: {operator: "is", values: [...], name: "filter_type"}}`
   - List all valid filter types: `os`, `role`, `simulators`, `connection`
   - For each filter type, list valid values:
     - `os`: WINDOWS, MAC, LINUX, DOCKER, NETWORK (target) / WINDOWS, MAC, LINUX, DOCKER (attacker)
     - `role`: isInfiltration, isExfiltration, isAWSAttacker, isAzureAttacker, isGCPAttacker,
       isWebApplicationAttacker
     - `simulators`: array of simulator UUID strings
     - `connection`: boolean true/false
   - Add a "default" key section explaining: the "default" key applies overrides to all steps
     that are identified as missing filters. Steps with explicit per-number overrides take
     precedence. Note that "default" does not merge with partially-ready steps — it only applies
     to steps that are fully missing the relevant filter.

2. **Enhance diagnostic `hint_to_agent`** in `studio_functions.py` (around lines 2320-2328):
   - When the scenario is not ready and no step_overrides are provided, include a `hint_to_agent`
     field with a complete filter example block showing all filter types with valid values
   - Include a note about the "default" key feature as a shortcut for applying the same
     override to all missing steps
   - Include a reference to `get_console_simulators` for discovering simulator UUIDs

**Changes**:

| File | Change |
|------|--------|
| `safebreach_mcp_studio/studio_server.py` | Update `run_scenario` tool description with filter schema and default key docs |
| `safebreach_mcp_studio/studio_functions.py` | Enhance diagnostic `hint_to_agent` with detailed filter examples |

**Git Commit**: `docs(studio): add complete filter schema and default key docs to run_scenario`

---

### Phase 2: Statistics API Error Propagation (TDD)

**Semantic Change**: Propagate API response body in error messages for statistics and related API calls

**TDD Approach**: Write E2E tests first, then implement.

**Deliverables**:
- E2E tests verifying error messages contain API response body details
- Statistics API call captures and propagates response body in error messages
- Same pattern applied to scenario fetch and plan fetch API calls

**Implementation Details**:

**Step 1: Write E2E tests first** (in `safebreach_mcp_studio/tests/`):
- E2E test for `run_scenario` with intentionally malformed step_overrides filter
  (e.g., missing `name` field or invalid role value) → verify the error response contains
  details from the API error body (not just generic "400 Client Error")
- E2E test for scenario fetch with invalid scenario ID → verify error contains API details
- Tests should assert that the error string contains specific API-originated content
  (not just HTTP status code)

**Step 2: Implement the fix**:

1. **Update `_get_scenario_statistics()` in `studio_functions.py`** (around lines 2173-2176):
   - Replace the bare `response.raise_for_status()` with an error-aware pattern:
     - Check `if response.status_code >= 400`
     - Capture the response body text
     - Log it for server observability:
       `logger.error(f"Statistics API error {response.status_code}: {response.text}")`
     - Raise a `ValueError` whose message includes the response body text, so it propagates
       through the server wrapper's except block and reaches the LLM agent as an actionable
       error message
       (e.g., `ValueError(f"Statistics API error ({response.status_code}): {response.text}")`)
   - The server wrapper (`studio_server.py` lines 1335-1340) already catches ValueError and
     returns `f"Run Scenario Error: {str(e)}"` — so the API error details will now be visible
     to the LLM agent, allowing it to learn from the error and adjust its next attempt

2. **Apply same pattern to scenario fetch** (around line 1932 in `studio_functions.py`):
   - The `_fetch_all_scenarios()` function's `response.raise_for_status()` call should follow
     the same pattern: check status, log body, raise ValueError with body text

3. **Apply same pattern to plan fetch** (around line 1958 in `studio_functions.py`):
   - The `_fetch_all_plans()` function's `response.raise_for_status()` call should follow
     the same pattern

**Step 3: Verify** — Run E2E tests to confirm they pass with the implementation.

**Changes**:

| File | Change |
|------|--------|
| `safebreach_mcp_studio/tests/test_e2e_run_scenario.py` | Add E2E tests for error propagation |
| `safebreach_mcp_studio/studio_functions.py` | Add response body capture and propagation in 3 API call sites |

**Git Commit**: `fix(studio): propagate API response body in error messages (TDD + E2E tests)`

---

### Phase 3: Attack Count in Scenario Listing (TDD)

**Semantic Change**: Add `total_attack_count` field to scenario listing and conditional hint_to_agent

**TDD Approach**: Write E2E tests first, then implement.

**Deliverables**:
- E2E tests verifying `total_attack_count` field in scenario listing
- `total_attack_count` field in reduced scenario mapping
- Conditional `hint_to_agent` for indeterminate counts

**Implementation Details**:

**Step 1: Write E2E tests first** (in `safebreach_mcp_config/tests/`):
- E2E test for `get_scenarios` → verify each scenario in the response has a
  `total_attack_count` field (integer or None)
- E2E test that `total_attack_count` is consistent with scenario detail view's
  playbook_ids (fetch detail for a known scenario, sum playbook_ids, compare with listing count)
- E2E test that when scenarios with indeterminate counts exist, the response includes
  a `hint_to_agent` about using `dry_run=True`

**Step 2: Implement**:

1. **Add attack count computation in `config_types.py`** (in `get_reduced_scenario_mapping()`
   around lines 149-178):
   - Create a helper function that iterates over scenario steps and sums attack counts
   - For each step, check `step.get('attacksFilter', {}).get('playbook', {}).get('values', [])`
   - If playbook values exist, add their count to the total
   - If any step has no playbook values (criteria-based), set the total to None to indicate
     indeterminate count
   - Add `total_attack_count` to the returned mapping dictionary

2. **Add the same computation for custom plans** (in `get_reduced_plan_mapping()` if it exists,
   or in the equivalent function):
   - Apply the same logic for custom plan listings

3. **Add conditional `hint_to_agent` in `config_server.py`** (in the `get_scenarios` tool wrapper):
   - After building the response, check if any scenario in the current page has
     `total_attack_count` set to None
   - If so, add a `hint_to_agent` note: "Some scenarios have criteria-based attack selection.
     Use `run_scenario` with `dry_run=True` to determine the exact attack count for those
     scenarios."

**Step 3: Verify** — Run E2E tests to confirm they pass with the implementation.

**Changes**:

| File | Change |
|------|--------|
| `safebreach_mcp_config/tests/test_e2e_scenarios.py` | Add E2E tests for total_attack_count |
| `safebreach_mcp_config/config_types.py` | Add `total_attack_count` computation to scenario listing |
| `safebreach_mcp_config/config_server.py` | Add conditional `hint_to_agent` for indeterminate counts |

**Git Commit**: `feat(config): add total_attack_count to scenario listing (TDD + E2E tests)`

---

### Phase 4: CLAUDE.md Update

**Semantic Change**: Update project documentation to reflect all changes

**Deliverables**:
- Updated CLAUDE.md with new `total_attack_count` field
- Updated CLAUDE.md with improved error handling notes
- Updated CLAUDE.md with "default" key documentation

**Changes**:

| File | Change |
|------|--------|
| `CLAUDE.md` | Update MCP tools documentation with new field, error handling, default key |

**Git Commit**: `docs: update CLAUDE.md for SAF-30319 improvements`

---

## 10. Risks and Assumptions

### Technical Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Statistics API error body format varies or is empty | Medium — error message may not be helpful | Log raw text regardless; any info is better than "400 Client Error" |
| Criteria-based attack count is misleading | Low — agents may assume count is accurate | Use None for indeterminate + hint_to_agent explanation |
| Tool description becomes too long for some MCP clients | Low — most clients handle long descriptions | Keep inline docs concise; put detail in hint_to_agent |

### Assumptions

- The statistics API response body contains useful error context when returning 400 errors
- The `attacksFilter.playbook.values` field is present and correctly populated for
  playbook-based scenarios at listing time
- Existing tool description formatting conventions (markdown-style) work well for LLM agents

---

## 11. Future Enhancements

- **Issue #3: Stale simulator UUID annotation** — Cross-reference scenario simulator UUIDs with
  connected simulator status. Requires separate API call and potentially a new parameter
  (e.g., `enrich_simulators=True`) on `get_scenario_details`.
- **Pre-flight filter validation** — Validate filter structure before calling statistics API
  to catch malformed filters earlier with specific error messages.
- **Default key partial-step merging** — Enhance the "default" key to merge with partially-ready
  steps, filling in only the missing filter side.

---

## 12. Executive Summary

- **Issue/Feature Description**: The `run_scenario` MCP tool has usability issues that cause
  LLM agents to waste multiple iterations on filter format discovery, receive opaque API errors,
  and lack attack count data for scenario selection.
- **What Was Built**: Documentation improvements for filter schema and default key, API error
  propagation following proven queue API pattern, and attack count enrichment in scenario listing.
- **Key Technical Decisions**: Docs-only approach for filter schema (no runtime validation);
  mirror queue API error pattern; defer simulator UUID enrichment to separate ticket.
- **Scope Changes**: Issue #3 (stale simulator UUIDs) deferred; Issue #2 scoped to documentation
  only (no behavior change); Issue #1 scoped to documentation only (no validation).
- **Business Value Delivered**: Agents discover correct filter format on first attempt, get
  actionable error messages, and can evaluate scenario complexity from listing.

---

## 14. Change Log

| Date | Change Description |
|------|-------------------|
| 2026-04-23 14:45 | PRD created — initial draft |
