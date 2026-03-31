# Platform Filtering for Playbook Attacks — SAF-29642

## 1. Overview

- **Title**: Attacker/Target Platform Filtering for `get_playbook_attacks`
- **Task Type**: Feature
- **Purpose**: Enable filtering playbook attacks by the OS/platform of attacker and target nodes,
  allowing users to narrow results for environment-specific security assessments
  (e.g., "show me all attacks targeting Windows")
- **Target Consumer**: Internal — AI agents and MCP tool users querying the SafeBreach playbook
- **Key Benefits**:
  - Platform-specific attack discovery for targeted security assessments
  - Consistent filtering experience alongside existing name, MITRE, and date filters
  - Always-visible platform metadata for every attack in results
- **Business Alignment**: Improves MCP tool usability and attack discoverability for SafeBreach users
- **Originating Request**: [SAF-29642](https://safebreach.atlassian.net/browse/SAF-29642)

---

## 1.5. Document Status

| Field | Value |
|-------|-------|
| **PRD Status** | Draft |
| **Last Updated** | 2026-03-31 14:10 |
| **Owner** | AI Agent |
| **Current Phase** | N/A |

---

## 2. Solution Description

### Chosen Solution: Platform as First-Class Fields (Always Extracted)

Always extract `attacker_platform` and `target_platform` from the raw API response during the
transform step. Platform data is lightweight (two optional strings per attack), so no conditional
`include_platform` flag is needed — unlike MITRE data which is complex and optionally included.

Platform data is derived from `content.nodes.{node_name}.constraints.os` in the SafeBreach API
response. Node-to-role mapping uses `isSource` (attacker) and `isDestination` (target) boolean flags.

Filtering uses comma-separated values with OR logic and case-insensitive partial matching,
consistent with existing `name_filter` and `mitre_technique_filter` patterns.

**Key design decision**: When a platform filter is active, attacks with `None` platform values
(no OS data) are **included** in results rather than excluded. This avoids hiding 67.7% of attacks
that lack OS constraints. This behavior must be documented in the tool description.

### Alternatives Considered

**Approach B — Conditional Extraction (MITRE-like)**: Add `include_platform: bool = False` flag
with auto-enable logic when filters are active. Rejected because platform data is just two optional
strings — the overhead of conditional extraction adds complexity without meaningful performance gain.

### Decision Rationale

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Extraction | Always | Lightweight (2 strings), no include_platform flag needed |
| Matching | Case-insensitive partial match | Consistent with name_filter and MITRE filters |
| None handling | `None` for N/A | Clean, explicit "not applicable" for single-node attacks |
| No OS data + filter | Include in results | Avoids hiding 67.7% of attacks; documented in tool description |
| Response rendering | Always show | Platform data always visible in output |

---

## 3. Core Feature Components

### Component A: Platform Data Extraction (`playbook_types.py`)

**Purpose**: New function to extract attacker/target platform from the raw attack node structure.

**Key Features**:
- Traverse `content.nodes` to find all nodes and their roles
- Map each node to attacker (isSource=True) or target (isDestination=True) role
- Extract `constraints.os` from the mapped nodes
- Handle all 5 node patterns: gold, green/red, attacker/target, target-only, local-only
- Case-insensitive node name matching (handles `Green`/`Red` vs `green`/`red`)
- For single-node patterns (gold, local, target-only): target_platform = node OS, attacker_platform = None

### Component B: Platform Filtering (`playbook_types.py`)

**Purpose**: Add platform filter parameters to the existing `filter_attacks_by_criteria()` function.

**Key Features**:
- Two new parameters: `attacker_platform_filter` and `target_platform_filter`
- Comma-separated values with OR logic (e.g., "WINDOWS,LINUX" matches either)
- Case-insensitive partial matching (e.g., "win" matches "WINDOWS")
- Attacks with `None` platform values pass through the filter (not excluded)
- Helper functions `_attack_matches_attacker_platform()` and `_attack_matches_target_platform()`

### Component C: Parameter Pass-Through (`playbook_functions.py`)

**Purpose**: Wire new filter parameters through the business logic layer.

**Key Features**:
- Add `attacker_platform_filter` and `target_platform_filter` to `sb_get_playbook_attacks()` signature
- Pass parameters to `filter_attacks_by_criteria()`
- Track in `applied_filters` response metadata

### Component D: MCP Tool Interface (`playbook_server.py`)

**Purpose**: Expose platform filters as MCP tool parameters with proper documentation.

**Key Features**:
- Add parameters to `get_playbook_attacks` tool signature
- Update tool description to document platform filter behavior, including None pass-through
- Render `**Attacker Platform:**` and `**Target Platform:**` in response output for each attack

---

## 4. API Endpoints and Integration

### Existing API Consumed

- **API Name**: SafeBreach Playbook Moves API
- **URL**: `GET {base_url}/api/kb/vLatest/moves?details=true`
- **Headers**: `x-apitoken`, `Content-Type: application/json`
- **Relevant Response Fields** (per attack in `data` array):
  - `content.nodes` — dict of node objects keyed by node name
  - `content.nodes.{name}.isSource` — boolean, True = attacker role
  - `content.nodes.{name}.isDestination` — boolean, True = target role
  - `content.nodes.{name}.constraints.os` — string OS value (optional)
- **Valid OS Values**: `AWS`, `AZURE`, `GCP`, `LINUX`, `MAC`, `WEBAPPLICATION`, `WINDOWS`

### Node Pattern Reference

| Pattern | Node Names | Attacker Node | Target Node | Count |
|---------|-----------|---------------|-------------|-------|
| Host | `gold` | N/A | `gold` | 2,985 |
| Network | `green`, `red` | `isSource=True` | `isDestination=True` | 6,446 |
| Explicit | `attacker`, `target` | `attacker` | `target` | 21 |
| Target-only | `target` | N/A | `target` | 138 |
| Local-only | `local` | N/A | `local` | 43 |
| Case variant | `Green`, `Red` | `isSource=True` | `isDestination=True` | 2 |

---

## 6. Non-Functional Requirements

### Technical Constraints

- **Backward Compatibility**: No breaking changes. New fields (`attacker_platform`, `target_platform`)
  are added to the reduced format. Existing responses gain two new fields set to None when unavailable.
- **Performance**: Platform extraction is O(n) where n = number of nodes per attack (typically 1-2).
  No additional API calls required — data comes from the same `/moves?details=true` response.
- **Caching**: No cache changes needed. Platform data is extracted from already-cached raw attack data.

---

## 7. Definition of Done

- [ ] `_extract_platform_data()` correctly extracts platform from all 5 node patterns
- [ ] `attacker_platform` and `target_platform` always present in reduced attack format
- [ ] `attacker_platform_filter` and `target_platform_filter` parameters accepted by `get_playbook_attacks`
- [ ] Comma-separated OR logic with case-insensitive partial matching works correctly
- [ ] Attacks with None platform pass through filters (not excluded)
- [ ] Applied filters tracked in response metadata
- [ ] Platform values rendered in MCP tool response output
- [ ] Node name matching is case-insensitive (handles Green/Red vs green/red)
- [ ] Unit tests for platform extraction from all 5 node patterns
- [ ] Unit tests for platform filtering (single value, comma-separated, combined with other filters)
- [ ] Unit tests for None pass-through behavior
- [ ] Integration tests for platform filtering across multi-attack datasets
- [ ] E2E tests for platform filtering against live console
- [ ] Tool description documents None pass-through behavior
- [ ] CLAUDE.md updated with new filter documentation
- [ ] All existing tests continue to pass

---

## 8. Testing Strategy

### Unit Testing (`test_playbook_types.py`) — Phase 5

- **Scope**: `_extract_platform_data()` function and platform filter helpers
- **Key Scenarios**:
  - Extract from gold node (single node, target only)
  - Extract from green/red nodes (dual node, role-mapped via isSource/isDestination)
  - Extract from attacker/target nodes (explicit names)
  - Extract from target-only and local-only patterns
  - Handle missing `content.nodes` gracefully (return None/None)
  - Handle missing `constraints.os` (return None for that role)
  - Case-insensitive node name handling (Green vs green)
  - Filter by single platform value
  - Filter by comma-separated values (OR logic)
  - Filter partial match (e.g., "win" matches "WINDOWS")
  - Filter with None platform values passes through
  - Combined platform filter with other filters
- **Framework**: pytest
- **Coverage Target**: Maintain existing coverage level

### Unit Testing (`test_playbook_functions.py`) — Phase 6

- **Scope**: `sb_get_playbook_attacks()` with platform parameters
- **Key Scenarios**:
  - Platform fields always present in response (without filter)
  - `attacker_platform_filter` filters correctly
  - `target_platform_filter` filters correctly
  - Combined platform + name/MITRE filters
  - Applied filters metadata includes platform filters
  - Attacks with None platform included when filter active
- **Class**: New `TestPlatformGetPlaybookAttacks` class following `TestMitreGetPlaybookAttacks` pattern

### Integration Testing (`test_integration.py`) — Phase 7

- **Scope**: End-to-end flow from function call through transform, filter, and pagination
- **Key Scenarios**:
  - Platform filtering across dataset with mixed node patterns
  - Platform + MITRE + name combined filtering
  - Pagination with platform filters applied

### E2E Testing (`test_e2e.py`) — Phase 7 (Zero Mocks)

All E2E tests run against the live console with **zero mocks**. They call `sb_get_playbook_attacks()`
and `sb_get_playbook_attack_details()` which hit the real SafeBreach API.

- **Scope**: Full real API calls against live console for every filtering option
- **Test Cases**:

  **Platform fields presence**:
  - `test_platform_fields_real_api`: Verify `attacker_platform` and `target_platform` keys exist
    in every attack returned by the real API (values can be None or a valid OS string)

  **Single platform filter — attacker**:
  - `test_attacker_platform_filter_windows`: Filter `attacker_platform_filter="WINDOWS"`,
    verify all returned attacks with non-None attacker_platform contain "WINDOWS"
  - `test_attacker_platform_filter_linux`: Filter `attacker_platform_filter="LINUX"`,
    verify matches

  **Single platform filter — target**:
  - `test_target_platform_filter_windows`: Filter `target_platform_filter="WINDOWS"`,
    verify all returned attacks with non-None target_platform contain "WINDOWS"
  - `test_target_platform_filter_linux`: Same for LINUX

  **Multi-value comma-separated filter (OR logic)**:
  - `test_target_platform_filter_multi_value`: Filter `target_platform_filter="WINDOWS,LINUX"`,
    verify returned attacks match either WINDOWS or LINUX (or have None platform)
  - Verify total_attacks >= individual filter counts (OR expands results)

  **Partial match**:
  - `test_platform_filter_partial_match`: Filter `target_platform_filter="win"`,
    verify matches WINDOWS attacks

  **Case insensitivity**:
  - `test_platform_filter_case_insensitive`: Filter `target_platform_filter="windows"` (lowercase),
    verify matches WINDOWS attacks

  **None pass-through verification**:
  - `test_platform_filter_none_pass_through`: Filter by a platform, verify result includes attacks
    where the filtered platform field is None. Compare total with filter vs count of matching +
    count of None to confirm None attacks are preserved.

  **Combined filters**:
  - `test_platform_plus_name_filter`: Combine `target_platform_filter="WINDOWS"` with
    `name_filter="registry"`, verify results satisfy both conditions
  - `test_platform_plus_mitre_filter`: Combine `target_platform_filter="WINDOWS"` with
    `mitre_tactic_filter="Discovery"`, verify results satisfy both conditions

  **Applied filters metadata**:
  - `test_platform_filter_metadata_real_api`: Verify `applied_filters` dict contains
    `attacker_platform_filter` and/or `target_platform_filter` when set

  **No matches**:
  - `test_platform_filter_no_match`: Filter by a nonexistent platform value
    (e.g., "NONEXISTENT_OS"), verify total_attacks equals the count of attacks with None platform
    (since None passes through, but no real matches exist)

  **Pagination with platform filter**:
  - `test_platform_filter_pagination`: Apply platform filter, verify pagination metadata is correct
    (total_pages, page_number) and page 0 and page 1 have disjoint attack IDs

---

## 9. Implementation Phases

| Phase | Status | Completed | Commit SHA | Notes |
|-------|--------|-----------|------------|-------|
| Phase 1: Platform extraction | Pending | - | - | |
| Phase 2: Platform filtering | Pending | - | - | |
| Phase 3: Business logic wiring | Pending | - | - | |
| Phase 4: MCP tool interface | Pending | - | - | |
| Phase 5: Unit tests (types) | Pending | - | - | |
| Phase 6: Unit tests (functions) | Pending | - | - | |
| Phase 7: Integration + E2E tests | Pending | - | - | |
| Phase 8: Documentation | Pending | - | - | |

### Phase 1: Platform Data Extraction

**Semantic Change**: Add platform extraction function to `playbook_types.py`

**Deliverables**: `_extract_platform_data()` function that derives attacker/target platform
from the raw attack data's `content.nodes` structure.

**Implementation Details**:

1. Create `_extract_platform_data(content_data: Dict) -> Dict[str, Optional[str]]` function:
   - Accept the `content` dict from the raw attack data
   - Initialize result as `{'attacker_platform': None, 'target_platform': None}`
   - Get `nodes` dict from content_data, return defaults if missing or not a dict
   - Iterate over all node entries (case-insensitive key handling)
   - For each node that is a dict:
     - Check `isSource` flag — if True, extract `constraints.os` as `attacker_platform`
     - Check `isDestination` flag — if True, extract `constraints.os` as `target_platform`
   - **Special case for single-node patterns** (gold, local, target-only):
     When only one node exists and neither `isSource` nor `isDestination` is True,
     assign the node's OS to `target_platform` (single-node attacks are target-centric)
   - Return the result dict

2. Update `transform_reduced_playbook_attack()`:
   - After the existing mapping loop, call `_extract_platform_data(attack_data.get('content', {}))`
   - Merge the returned dict into `result` using `result.update(platform_data)`
   - This runs unconditionally (no boolean flag)

**Changes**:

| File | Change |
|------|--------|
| `safebreach_mcp_playbook/playbook_types.py` | Add `_extract_platform_data()` function |
| `safebreach_mcp_playbook/playbook_types.py` | Update `transform_reduced_playbook_attack()` to call it |

**Git Commit**: `feat(playbook): extract attacker/target platform from attack nodes (SAF-29642)`

---

### Phase 2: Platform Filtering Logic

**Semantic Change**: Add platform filter parameters and helpers to `filter_attacks_by_criteria()`

**Deliverables**: Platform filtering with comma-separated OR logic, case-insensitive partial match,
and None pass-through behavior.

**Implementation Details**:

1. Add two new parameters to `filter_attacks_by_criteria()`:
   - `attacker_platform_filter: Optional[str] = None`
   - `target_platform_filter: Optional[str] = None`

2. Create `_attack_matches_platform(platform_value: Optional[str], filter_values: List[str]) -> bool`:
   - If `platform_value` is None, return True (None pass-through — attacks without OS data are included)
   - For each filter value, check if it appears as a substring in `platform_value.lower()`
   - Return True if any filter value matches (OR logic)
   - Return False if no matches

3. Add filtering blocks at the end of `filter_attacks_by_criteria()`, after the MITRE filter blocks:
   - If `attacker_platform_filter` is set:
     Parse comma-separated values: `[v.strip().lower() for v in filter.split(',') if v.strip()]`
     Filter using list comprehension with `_attack_matches_platform(attack.get('attacker_platform'), values)`
   - Same pattern for `target_platform_filter` using `attack.get('target_platform')`

**Changes**:

| File | Change |
|------|--------|
| `safebreach_mcp_playbook/playbook_types.py` | Add `_attack_matches_platform()` helper |
| `safebreach_mcp_playbook/playbook_types.py` | Add parameters and filter blocks to `filter_attacks_by_criteria()` |

**Git Commit**: `feat(playbook): add platform filtering logic with None pass-through (SAF-29642)`

---

### Phase 3: Business Logic Wiring

**Semantic Change**: Wire platform filter parameters through `sb_get_playbook_attacks()`

**Deliverables**: Platform filters passed from business logic to types layer, tracked in metadata.

**Implementation Details**:

1. Add parameters to `sb_get_playbook_attacks()` function signature:
   - `attacker_platform_filter: Optional[str] = None`
   - `target_platform_filter: Optional[str] = None`
   - Place after `mitre_tactic_filter` to maintain parameter grouping

2. Pass new parameters to `filter_attacks_by_criteria()` call (around line 165-177):
   - Add `attacker_platform_filter=attacker_platform_filter`
   - Add `target_platform_filter=target_platform_filter`

3. Add to applied_filters tracking (around line 183-203):
   - `if attacker_platform_filter: applied_filters['attacker_platform_filter'] = attacker_platform_filter`
   - `if target_platform_filter: applied_filters['target_platform_filter'] = target_platform_filter`

**Changes**:

| File | Change |
|------|--------|
| `safebreach_mcp_playbook/playbook_functions.py` | Add parameters, pass-through, applied_filters tracking |

**Git Commit**: `feat(playbook): wire platform filters through business logic (SAF-29642)`

---

### Phase 4: MCP Tool Interface

**Semantic Change**: Expose platform filters as MCP tool parameters with response rendering

**Deliverables**: Platform filter parameters in tool definition, updated description,
platform rendering in response.

**Implementation Details**:

1. Update tool description string to include new parameters:
   - Add to the description: `attacker_platform_filter` and `target_platform_filter`
     with documentation that they use comma-separated OR logic, case-insensitive partial match
   - Document that attacks without platform data are included in results when filters are active

2. Add parameters to `get_playbook_attacks()` MCP handler:
   - `attacker_platform_filter: Optional[str] = None`
   - `target_platform_filter: Optional[str] = None`

3. Pass parameters to `sb_get_playbook_attacks()` call

4. Add platform rendering in the response loop (after MITRE rendering, before `response_parts.append("")`):
   - Get `attacker_platform` and `target_platform` from the attack dict
   - If `attacker_platform` is not None, append `**Attacker Platform:** {value}`
   - If `target_platform` is not None, append `**Target Platform:** {value}`

**Changes**:

| File | Change |
|------|--------|
| `safebreach_mcp_playbook/playbook_server.py` | Add parameters, update description, add response rendering |

**Git Commit**: `feat(playbook): expose platform filters in MCP tool interface (SAF-29642)`

---

### Phase 5: Unit Tests — Types Layer

**Semantic Change**: Add unit tests for platform extraction and filtering in `playbook_types.py`

**Deliverables**: Comprehensive test coverage for `_extract_platform_data()`,
`_attack_matches_platform()`, and platform-aware `filter_attacks_by_criteria()`.

**Implementation Details**:

1. Add test fixtures with platform data:
   - `sample_attack_gold_with_os`: Single gold node with `constraints.os = "WINDOWS"`
   - `sample_attack_green_red_with_os`: Green/red nodes with different OS values
   - `sample_attack_attacker_target`: Explicit attacker/target node names
   - `sample_attack_target_only`: Single target node
   - `sample_attack_no_os`: Node without constraints.os
   - `sample_attack_case_variant`: Green/Red with capital case node names
   - `sample_attacks_with_platform_list`: Mixed list of attacks with various platform patterns
     (already transformed with `attacker_platform`/`target_platform` fields for filter testing)

2. Add `TestExtractPlatformData` class:
   - Test gold node extraction (target only, attacker=None)
   - Test green/red node extraction with isSource/isDestination mapping
   - Test attacker/target explicit node names
   - Test target-only and local-only patterns
   - Test missing content.nodes (returns None/None)
   - Test missing constraints.os (returns None for that role)
   - Test case-insensitive node names (Green vs green)

3. Add `TestAttackMatchesPlatform` class:
   - Test None platform value returns True (pass-through)
   - Test exact match (case-insensitive)
   - Test partial match ("win" matches "WINDOWS")
   - Test no match returns False
   - Test multiple filter values (OR logic)

4. Add `TestPlatformFiltering` class:
   - Test `filter_attacks_by_criteria()` with `attacker_platform_filter`
   - Test with `target_platform_filter`
   - Test comma-separated values
   - Test combined with name_filter
   - Test None pass-through (attacks without platform included)

**Changes**:

| File | Change |
|------|--------|
| `safebreach_mcp_playbook/tests/test_playbook_types.py` | Add fixtures and 3 test classes |

**Git Commit**: `test(playbook): add unit tests for platform extraction and filtering (SAF-29642)`

---

### Phase 6: Unit Tests — Functions Layer

**Semantic Change**: Add unit tests for platform parameters in `sb_get_playbook_attacks()`

**Deliverables**: Tests verifying platform filter pass-through, applied_filters metadata,
and always-present platform fields.

**Implementation Details**:

1. Add `sample_attack_data_with_platform` fixture:
   - Two attacks with different platform configurations from raw API format
   - First attack: gold node with `constraints.os = "WINDOWS"` (host attack)
   - Second attack: green/red nodes, green has `constraints.os = "LINUX"` (network attack)

2. Add `TestPlatformGetPlaybookAttacks` class (following `TestMitreGetPlaybookAttacks` pattern):
   - `test_platform_fields_always_present`: Verify `attacker_platform` and `target_platform`
     in response without any filter
   - `test_attacker_platform_filter`: Filter by attacker platform, verify correct results
   - `test_target_platform_filter`: Filter by target platform, verify correct results
   - `test_platform_filter_combined_with_name`: Platform + name filter combination
   - `test_platform_filter_applied_filters_metadata`: Verify filters appear in `applied_filters`
   - `test_platform_filter_none_pass_through`: Attacks without OS data included in results

**Changes**:

| File | Change |
|------|--------|
| `safebreach_mcp_playbook/tests/test_playbook_functions.py` | Add fixture and test class |

**Git Commit**: `test(playbook): add unit tests for platform filter business logic (SAF-29642)`

---

### Phase 7: Integration + E2E Tests

**Semantic Change**: Add integration tests and comprehensive E2E tests (zero mocks) for platform filtering

**Deliverables**: Cross-component integration tests with mocked data and comprehensive E2E tests
against the live SafeBreach API with zero mocks.

**Implementation Details**:

#### Integration Tests (`test_integration.py`)

1. Update `comprehensive_attack_dataset` fixture:
   - Add `content.nodes` with platform data to existing attacks
   - Attack 1027: gold node with `constraints.os = "WINDOWS"` (host attack)
   - Attack 2048: green/red nodes, green `isSource=True` with `constraints.os = "LINUX"`,
     red `isDestination=True` with `constraints.os = "WINDOWS"` (network attack)
   - Attack 3141: no OS constraints in nodes (tests None pass-through)
   - Attack 4096: gold node with `constraints.os = "MAC"` (another host attack)

2. Add integration test methods:
   - `test_platform_filtering_integration`: Filter by `target_platform_filter="WINDOWS"`,
     verify attacks 1027 and 2048 match (both have WINDOWS target) plus 3141 (None pass-through)
   - `test_platform_combined_filtering`: Combine `target_platform_filter="WINDOWS"` with
     `name_filter="DNS"`, verify only attack 1027 matches
   - `test_platform_pagination`: Apply filter resulting in >10 matches, verify pagination metadata

#### E2E Tests (`test_e2e.py`) — Zero Mocks

All E2E tests call the real SafeBreach API. No mocking of any kind.

3. Add E2E test class `TestPlatformE2E`:

   **a. Platform fields presence** (`test_platform_fields_real_api`):
   - Call `sb_get_playbook_attacks(console=E2E_CONSOLE)` with no filters
   - Verify every attack in result has `attacker_platform` and `target_platform` keys
   - Verify values are either None or a string from the valid OS set

   **b. Single target platform filter** (`test_target_platform_filter_windows`):
   - Call with `target_platform_filter="WINDOWS"`
   - Verify `total_attacks > 0`
   - For each attack in page: if `target_platform` is not None, assert "WINDOWS" in value
   - Verify `applied_filters['target_platform_filter'] == 'WINDOWS'`

   **c. Single attacker platform filter** (`test_attacker_platform_filter_linux`):
   - Call with `attacker_platform_filter="LINUX"`
   - Verify returned attacks: those with non-None attacker_platform contain "LINUX"

   **d. Multi-value OR filter** (`test_platform_filter_multi_value`):
   - Call with `target_platform_filter="WINDOWS,LINUX"`
   - Verify returned attacks: non-None target_platform matches either "WINDOWS" or "LINUX"
   - Call individually with "WINDOWS" and "LINUX", verify combined total >= max(individual totals)

   **e. Partial match** (`test_platform_filter_partial_match`):
   - Call with `target_platform_filter="win"`
   - Verify matches — all non-None target_platform values contain "win" (case-insensitive)
   - Total should equal the WINDOWS filter result total

   **f. Case insensitivity** (`test_platform_filter_case_insensitive`):
   - Call with `target_platform_filter="windows"` (lowercase)
   - Call with `target_platform_filter="WINDOWS"` (uppercase)
   - Verify both return identical `total_attacks`

   **g. None pass-through** (`test_platform_filter_none_pass_through`):
   - Call with `target_platform_filter="WINDOWS"`
   - Scan multiple pages to find at least one attack where `target_platform` is None
   - This confirms None attacks are not excluded by the filter

   **h. Combined platform + name** (`test_platform_plus_name_filter`):
   - Call with `target_platform_filter="WINDOWS"` and `name_filter="registry"`
   - Verify all returned attacks: name contains "registry" (case-insensitive) AND
     (target_platform contains "WINDOWS" OR target_platform is None)
   - Verify total_attacks <= WINDOWS-only total AND <= registry-only total

   **i. Combined platform + MITRE** (`test_platform_plus_mitre_filter`):
   - Call with `target_platform_filter="WINDOWS"` and `mitre_tactic_filter="Discovery"`
   - Verify all returned attacks: have Discovery tactic AND
     (target_platform contains "WINDOWS" OR target_platform is None)

   **j. Applied filters metadata** (`test_platform_filter_metadata`):
   - Call with both `attacker_platform_filter="LINUX"` and `target_platform_filter="WINDOWS"`
   - Verify `applied_filters` contains both keys with correct values

   **k. No real matches** (`test_platform_filter_nonexistent`):
   - Call with `target_platform_filter="NONEXISTENT_OS"`
   - Verify total_attacks > 0 (None pass-through means attacks without OS data still appear)
   - Verify no attack in results has a non-None target_platform

   **l. Pagination with filter** (`test_platform_filter_pagination`):
   - Call with `target_platform_filter="WINDOWS"`, page_number=0
   - If total_pages > 1, call page_number=1
   - Verify pages have disjoint attack IDs
   - Verify consistent total_attacks across pages

   **m. Platform in attack details** (`test_platform_in_attack_details`):
   - Get a WINDOWS attack ID from filtered list
   - Call `sb_get_playbook_attack_details()` for that attack
   - Verify the detail response is valid (basic fields present)

**Changes**:

| File | Change |
|------|--------|
| `safebreach_mcp_playbook/tests/test_integration.py` | Update fixture, add 3 integration test methods |
| `safebreach_mcp_playbook/tests/test_e2e.py` | Add `TestPlatformE2E` class with 13 E2E test methods |

**Git Commit**: `test(playbook): add integration and comprehensive E2E tests for platform filtering (SAF-29642)`

---

### Phase 8: Documentation

**Semantic Change**: Update CLAUDE.md with platform filter documentation

**Deliverables**: Updated tool documentation reflecting new filtering capabilities.

**Implementation Details**:

1. Update CLAUDE.md sections:
   - In "MCP Tools Available > Playbook Server" section: Add `attacker_platform_filter` and
     `target_platform_filter` to the `get_playbook_attacks` tool description
   - In "Filtering and Search Capabilities" section: Add a new subsection documenting
     platform filtering behavior, valid OS values, and None pass-through
   - Note that attacks without platform data are included when filters are active

**Changes**:

| File | Change |
|------|--------|
| `CLAUDE.md` | Update playbook tool docs and filtering section |

**Git Commit**: `docs: document platform filtering for playbook attacks (SAF-29642)`

---

## 10. Risks and Assumptions

### Technical Risks

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Low OS coverage on network attacks (3.7%) | Medium — platform filter less useful for network attacks | Document coverage limitation; None pass-through ensures no attacks hidden |
| New node patterns in future API versions | Low — extraction handles unknown patterns gracefully | Default to None/None for unrecognized patterns |
| Performance with always-on extraction | Low — extraction is O(1-2) per attack | Platform data is two strings, negligible overhead |

### Assumptions

- The SafeBreach API's `content.nodes` structure is stable and the `isSource`/`isDestination` role
  mapping convention will be maintained
- The 7 discovered OS values (AWS, AZURE, GCP, LINUX, MAC, WEBAPPLICATION, WINDOWS) represent the
  complete set; partial matching handles future additions gracefully
- Single-node attacks should map their node OS to `target_platform` (since host attacks are
  target-centric by nature)

---

## 12. Executive Summary

- **Issue**: The `get_playbook_attacks` MCP tool lacked platform-based filtering, preventing users
  from narrowing attacks by OS/platform
- **What Was Built**: Two new filter parameters (`attacker_platform_filter`, `target_platform_filter`)
  with always-on platform extraction from attack node data
- **Key Technical Decisions**: Always extract (no conditional flag); None pass-through to avoid
  hiding attacks without OS data; case-insensitive partial matching consistent with existing filters
- **Business Value**: Enables environment-specific attack discovery, critical for targeted security
  assessments on specific platforms

---

## 14. Change Log

| Date | Change Description |
|------|-------------------|
| 2026-03-31 14:10 | PRD created — initial draft |
