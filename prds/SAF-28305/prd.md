# PRD: Add MITRE ATT&CK Tags to Playbook Tools - SAF-28305

## 1. Overview

- **Title**: Add MITRE ATT&CK Tags to Playbook Tools - SAF-28305
- **Task Type**: Feature
- **Purpose**: Enable MITRE ATT&CK technique/tactic data extraction and filtering in the playbook MCP tools,
  allowing customers to compare MITRE ATT&CK TTPs against SafeBreach available TTPs programmatically.
- **Target Consumer**: Customer (Intuit - Efi), external MCP tool users
- **Key Benefits**:
  1. Customers can retrieve MITRE ATT&CK mappings in bulk via `get_playbook_attacks` instead of one-at-a-time
  2. MITRE-based filtering enables targeted queries (e.g., "all attacks for T1046" or "all Discovery attacks")
  3. Weekly TTP coverage comparison workflows become feasible via MCP tooling
- **Business Alignment**: Customer-requested enhancement for Intuit; improves MCP tool value for security teams
  doing ATT&CK coverage analysis
- **Originating Request**: JIRA SAF-28305, reported by Intuit (Efi)

## 1.5. Document Status

| Field | Value |
|-------|-------|
| **PRD Status** | Complete |
| **Last Updated** | 2026-02-16 |
| **Owner** | Yossi Attas |
| **Current Phase** | Complete |

## 2. Solution Description

### Chosen Solution

Add optional `include_mitre_techniques` parameter (default `False`) to both `get_playbook_attacks` and
`get_playbook_attack_details` tools, plus `mitre_technique_filter` and `mitre_tactic_filter` parameters
on the bulk listing tool. This follows the Data Server's existing pattern for optional MITRE inclusion.

**Key insight**: MITRE data is already present in the cached playbook API response, embedded within the
`tags` array under tag categories `MITRE_Tactic`, `MITRE_Technique`, and `MITRE_Sub_Technique`. No
additional API calls are required - we just need to extract and structure the data.

**MITRE data structure in API** (inside `tags` array):
- Tag name `MITRE_Tactic`: `values` contain `{value: "Discovery", displayName: "Discovery"}`
- Tag name `MITRE_Technique`: `values` contain `{value: "T1046", displayName: "(T1046) Network Service Discovery"}`
- Tag name `MITRE_Sub_Technique`: `values` contain
  `{value: "T1021.001", displayName: "(T1021.001) Remote Desktop Protocol"}`

**Coverage statistics** (from pentest01 console, 9,599 attacks):
- `MITRE_Tactic`: 42.6% (4,089 attacks), 12 unique tactics
- `MITRE_Technique`: 42.6% (4,088 attacks), 134 unique techniques
- `MITRE_Sub_Technique`: 22.2% (2,133 attacks), 223 unique sub-techniques
- Most attacks have 0-1 techniques; max 12 on a single attack

### Alternatives Considered

**Approach A - Uniform Transform (No Filtering)**: Add `include_mitre_techniques` to both transform
functions without filtering support. Simpler but insufficient for Intuit's TTP comparison use case,
which requires querying by specific technique or tactic.

**Approach B - Post-Pagination Enrichment**: Keep reduced transform lean, only extract MITRE for the
10 paginated results by looking up raw data. More performant but creates two different MITRE code paths
(listing vs details), adding maintenance complexity.

### Decision Rationale

Approach C was chosen because:
1. Filtering is essential for Intuit's weekly TTP comparison workflow
2. Performance difference is negligible (dict lookups for 9,599 cached items is milliseconds)
3. Single MITRE extraction function used everywhere keeps code consistent
4. Follows established Data Server pattern for `include_mitre_techniques`

## 3. Core Feature Components

### Component A: MITRE Data Extraction (`playbook_types.py`)

- **Purpose**: Extract and structure MITRE ATT&CK data from the playbook API `tags` array.
  This is a new component - no MITRE extraction exists in playbook types today.
- **Key Features**:
  - New `_extract_mitre_data(tags_data)` function that parses the tags array and returns structured
    MITRE data (tactics, techniques, sub-techniques)
  - ATT&CK URL construction from technique IDs
    (e.g., `T1046` -> `https://attack.mitre.org/techniques/T1046/`,
    `T1021.001` -> `https://attack.mitre.org/techniques/T1021/001/`)
  - Graceful handling of missing or malformed MITRE tags (return empty lists)
  - Integration with both `transform_reduced_playbook_attack` and `transform_full_playbook_attack`
    via new `include_mitre_techniques` parameter

### Component B: MITRE Filtering (`playbook_types.py`)

- **Purpose**: Enable filtering playbook attacks by MITRE technique ID/name and tactic name.
  Extends the existing `filter_attacks_by_criteria` function.
- **Key Features**:
  - `mitre_technique_filter`: Comma-separated values with OR logic. Each value is a
    case-insensitive partial match against technique ID or display name in both
    `mitre_techniques` and `mitre_sub_techniques` arrays.
    Example: `"T1046,T1021"` matches attacks with T1046 **or** T1021.
    Example: `"Network Service,Remote"` matches attacks with techniques containing
    either term.
  - `mitre_tactic_filter`: Comma-separated values with OR logic. Each value is a
    case-insensitive partial match against tactic name in `mitre_tactics` array.
    Example: `"Discovery,Lateral Movement"` matches attacks with either tactic.
  - Combinable with all existing filters (name, description, ID range, date ranges)
  - Requires MITRE data to be present in attack objects (transform must include MITRE before filtering)

### Component C: Business Logic Integration (`playbook_functions.py`)

- **Purpose**: Wire MITRE parameters through the business logic layer. Modifies existing functions.
- **Key Features**:
  - `sb_get_playbook_attacks`: Add `include_mitre_techniques`, `mitre_technique_filter`,
    `mitre_tactic_filter` parameters. Auto-enable MITRE in transform when filters are active.
  - `sb_get_playbook_attack_details`: Add `include_mitre_techniques` parameter, pass through to transform.
  - Add MITRE filter info to `applied_filters` response metadata.

### Component D: MCP Tool Interface (`playbook_server.py`)

- **Purpose**: Expose MITRE parameters in the MCP tool definitions and render MITRE data in
  markdown output. Modifies existing tool registrations.
- **Key Features**:
  - `get_playbook_attacks` tool: Add three new optional parameters, update tool description,
    render MITRE data (tactics, techniques, sub-techniques) per attack in markdown
  - `get_playbook_attack_details` tool: Add one new optional parameter, update description,
    add MITRE section in markdown output

## 5. Example Customer Flow

### Scenario: Weekly MITRE ATT&CK Coverage Comparison

**Entry Point**: AI agent calls MCP `get_playbook_attacks` tool

**Flow**:
1. Agent calls `get_playbook_attacks(console="intuit", include_mitre_techniques=True, page_number=0)`
2. Tool returns page 1 of attacks with MITRE tactics, techniques, and sub-techniques per attack
3. Agent iterates through pages to collect all MITRE technique IDs
4. Agent compares collected technique IDs against the full MITRE ATT&CK framework
5. Agent produces a coverage report showing which TTPs SafeBreach covers

### Scenario: Find All Attacks for a Specific Technique

**Entry Point**: AI agent calls MCP `get_playbook_attacks` with MITRE filter

**Flow**:
1. Agent calls `get_playbook_attacks(console="intuit", mitre_technique_filter="T1046")`
2. Tool auto-enables MITRE data inclusion and filters attacks matching T1046
3. Returns paginated results with MITRE data showing matching attacks
4. Agent uses results to build a test plan targeting that specific technique

### Scenario: Filter by MITRE Tactic

**Entry Point**: AI agent queries attacks by tactic category

**Flow**:
1. Agent calls `get_playbook_attacks(console="intuit", mitre_tactic_filter="Lateral Movement")`
2. Tool returns all attacks mapped to the Lateral Movement tactic
3. Agent can further refine with existing filters
   (e.g., `name_filter="RDP"` + `mitre_tactic_filter="Lateral Movement"`)

## 6. Non-Functional Requirements

### Performance Requirements

- **Default behavior**: When `include_mitre_techniques=False` (default), zero additional processing.
  Existing performance characteristics unchanged.
- **MITRE enabled**: Dict lookups for 9,599 cached attacks adds ~milliseconds. No additional API calls.
  MITRE data is already in the cached response.
- **Memory**: MITRE data is extracted on-the-fly from cached tags, not stored separately.
  Memory overhead is proportional to the 10-item page size, not the full 9,599 attack dataset.
- **Pagination**: Only 10 attacks returned per page regardless of MITRE inclusion.
  Total response size increase is bounded.

### Technical Constraints

- **Backward Compatibility**: All existing parameters and default behaviors preserved.
  No breaking changes to existing MCP tool interfaces.
- **Consistency**: Follow the Data Server `include_mitre_techniques` pattern for parameter naming
  and behavior.
- **URL Construction**: ATT&CK URLs must be constructed from technique IDs since the playbook API
  does not provide URLs. Sub-technique IDs use `.` notation (e.g., `T1021.001`) which must be
  converted to `/` notation for URLs (e.g., `T1021/001`).

## 7. Definition of Done

### Core Functionality
- [ ] `get_playbook_attacks` with `include_mitre_techniques=True` returns MITRE tactics,
  techniques, and sub-techniques for each attack
- [ ] `get_playbook_attack_details` with `include_mitre_techniques=True` returns MITRE data
- [ ] `mitre_technique_filter` supports single value (e.g., "T1046") and comma-separated
  multi-value (e.g., "T1046,T1021") with OR logic, case-insensitive partial match
- [ ] `mitre_tactic_filter` supports single value (e.g., "Discovery") and comma-separated
  multi-value (e.g., "Discovery,Lateral Movement") with OR logic, case-insensitive partial match
- [ ] MITRE filters combinable with all existing filters
- [ ] MITRE auto-included when MITRE filters are used
- [ ] ATT&CK URLs constructed correctly for both techniques and sub-techniques

### Quality Gates
- [ ] Default behavior unchanged - no performance impact when MITRE params not used
- [ ] All existing unit tests pass without modification
- [ ] New unit tests cover MITRE extraction, transformation, filtering, and edge cases
- [ ] E2E test confirms MITRE data returned from real SafeBreach API
- [ ] `CLAUDE.md` documentation updated

## 8. Testing Strategy

### Principle: Zero Manual Testing

Every implementation phase includes automated verification. No phase relies on manual
testing. All MITRE functionality is covered through extending existing test infrastructure.

### Test Codebase Analysis

**Existing test files to extend** (prefer extending over creating new files):

| File | Existing Tests | Extension Strategy |
|------|---------------|-------------------|
| `test_playbook_types.py` | `TestTagsTransformation` (7 tests), `TestTransformationFunctions` (4 tests), `TestFilteringFunctions` (8 tests), `TestPaginationFunction` (7 tests) | Add `TestMitreExtraction` class (new), extend `TestTransformationFunctions` with MITRE on/off tests, extend `TestFilteringFunctions` with MITRE filter tests |
| `test_playbook_functions.py` | `TestGetPlaybookAttacks` (8 tests), `TestGetPlaybookAttackDetails` (6 tests), `TestCacheFunctionality` (1 test) | Add `sample_attack_data_with_mitre` fixture alongside existing `sample_attack_data`, extend both test classes with MITRE tests |
| `test_e2e.py` | `TestPlaybookE2E` (9 tests including verbosity, filtering, pagination) | Extend `test_verbosity_levels_real_api` to include `include_mitre_techniques`, add `test_mitre_filtering_real_api` and `test_mitre_data_quality_real_api` |
| `test_playbook_server.py` | Server init + external config (5 tests) | No changes needed - server layer tested via functions + E2E |
| `test_integration.py` | Integration between components | No changes needed - covered by functions tests |

### Unit Tests: Types Layer (`test_playbook_types.py`)

**New class `TestMitreExtraction`** (in existing file):
- Complete MITRE tags (tactic + technique + sub-technique) -> correct structured output
- Partial MITRE tags (technique only, no sub-technique) -> partial output, empty lists for missing
- No MITRE tags in attack -> empty lists for all three categories
- Malformed tags data (None, empty list, wrong types) -> graceful empty result
- URL construction: technique `T1046` -> `https://attack.mitre.org/techniques/T1046/`
- URL construction: sub-technique `T1021.001` -> `https://attack.mitre.org/techniques/T1021/001/`
- Multiple techniques on one attack -> all extracted correctly

**Extend existing `TestTransformationFunctions`**:
- `test_transform_reduced_with_mitre_disabled` -> no MITRE keys in output (default behavior preserved)
- `test_transform_reduced_with_mitre_enabled` -> MITRE keys present, existing fields unchanged
- `test_transform_full_with_mitre_enabled` -> MITRE keys alongside tags/params/fix_suggestions
- `test_transform_with_mitre_and_no_mitre_tags` -> MITRE enabled but attack has no MITRE tags -> empty lists

**Extend existing `TestFilteringFunctions`**:
- `test_filter_by_mitre_technique_id` -> "T1046" matches attack with that technique
- `test_filter_by_mitre_technique_name` -> "Network Service" matches technique display name
- `test_filter_by_mitre_sub_technique` -> "T1021.001" matches sub-technique
- `test_filter_by_mitre_tactic` -> "Discovery" matches tactic name
- `test_filter_mitre_multi_technique` -> "T1046,T1021" matches attacks with either (OR logic)
- `test_filter_mitre_multi_tactic` -> "Discovery,Lateral Movement" matches attacks with either
- `test_filter_mitre_multi_with_spaces` -> "T1046, T1021" (spaces after comma) still works
- `test_filter_mitre_combined_with_name` -> MITRE + name filter combined
- `test_filter_mitre_no_matches` -> filter returns empty list
- `test_filter_mitre_excludes_attacks_without_mitre_data` -> attacks without MITRE excluded

### Unit Tests: Functions Layer (`test_playbook_functions.py`)

**New fixture `sample_attack_data_with_mitre`** (alongside existing `sample_attack_data`):
- Attack 1027: includes `MITRE_Tactic` (Discovery), `MITRE_Technique` (T1046),
  `MITRE_Sub_Technique` (none) in tags array
- Attack 2048: includes `MITRE_Tactic` (Lateral Movement), `MITRE_Technique` (T1021),
  `MITRE_Sub_Technique` (T1021.001) in tags array
- Uses real API tag structure: `{id, name, values: [{id, sort, value, displayName}]}`

**Extend existing `TestGetPlaybookAttacks`**:
- `test_mitre_inclusion` -> `include_mitre_techniques=True` returns MITRE in results
- `test_mitre_technique_filter` -> filters by technique, results contain matching attacks
- `test_mitre_tactic_filter` -> filters by tactic, results contain matching attacks
- `test_mitre_auto_enable_with_filter` -> MITRE filter + `include_mitre_techniques=False`
  -> MITRE still present (auto-enable)
- `test_mitre_filter_in_applied_filters` -> MITRE filter values appear in `applied_filters`

**Extend existing `TestGetPlaybookAttackDetails`**:
- `test_with_mitre_techniques` -> `include_mitre_techniques=True` returns MITRE data
- `test_without_mitre_techniques` -> default (False) -> no MITRE keys (preserved behavior)

### E2E Tests (`test_e2e.py`)

**Extend existing `TestPlaybookE2E`** class:

- **Extend `test_verbosity_levels_real_api`**: Add `include_mitre_techniques=True` to the
  verbosity combinations list. Assert `mitre_techniques` key present in result.

- **New `test_mitre_data_real_api`**: Call `sb_get_playbook_attacks` with
  `include_mitre_techniques=True`. Verify at least some attacks have non-empty
  `mitre_techniques` arrays. Verify MITRE data structure (id, display_name, url fields).

- **New `test_mitre_filtering_real_api`**: Test `mitre_tactic_filter="Discovery"` returns
  results. Verify all returned attacks have Discovery in their `mitre_tactics`.
  Test `mitre_technique_filter="T1046"` returns results matching that technique.

### Automated Coverage Per Phase

| Phase | Automated Verification | Run Command |
|-------|----------------------|-------------|
| Phase 1: MITRE Extraction | `TestMitreExtraction` + extended `TestTransformationFunctions` | `uv run pytest safebreach_mcp_playbook/tests/test_playbook_types.py -v -k "mitre or Mitre"` |
| Phase 2: MITRE Filtering | Extended `TestFilteringFunctions` | `uv run pytest safebreach_mcp_playbook/tests/test_playbook_types.py -v -k "filter"` |
| Phase 3: Business Logic | Extended `TestGetPlaybookAttacks` + `TestGetPlaybookAttackDetails` | `uv run pytest safebreach_mcp_playbook/tests/test_playbook_functions.py -v -k "mitre"` |
| Phase 4: MCP Tool Interface | Full regression + E2E | `uv run pytest safebreach_mcp_playbook/tests/ -v -m "not e2e"` |
| Phase 5: Types Tests | Types test suite (all) | `uv run pytest safebreach_mcp_playbook/tests/test_playbook_types.py -v` |
| Phase 6: Functions Tests | Functions test suite (all) | `uv run pytest safebreach_mcp_playbook/tests/test_playbook_functions.py -v` |
| Phase 7: E2E + Docs | E2E suite | `source .vscode/set_env.sh && uv run pytest safebreach_mcp_playbook/tests/test_e2e.py -v -m "e2e"` |

**Final validation**: Full cross-server test suite
```
uv run pytest safebreach_mcp_config/tests/ safebreach_mcp_data/tests/ safebreach_mcp_utilities/tests/ \
  safebreach_mcp_playbook/tests/ safebreach_mcp_studio/tests/ -v -m "not e2e"
```

## 9. Implementation Phases

| Phase | Status | Completed | Commit SHA | Notes |
|-------|--------|-----------|------------|-------|
| Phase 1: MITRE Data Extraction | ✅ Complete | 2026-02-16 | f13ea9d | |
| Phase 2: MITRE Filtering | ✅ Complete | 2026-02-16 | 8959c49 | |
| Phase 3: Business Logic Integration | ✅ Complete | 2026-02-16 | d117103 | |
| Phase 4: MCP Tool Interface | ✅ Complete | 2026-02-16 | 4f0c9f3 | |
| Phase 5: Tests - Types Layer | ✅ Complete | 2026-02-16 | 596f13b | 21 new tests |
| Phase 6: Tests - Functions Layer | ✅ Complete | 2026-02-16 | fd1d4de | 7 new tests |
| Phase 7: Documentation & E2E | ✅ Complete | 2026-02-16 | 18578f4 | 3 E2E tests |

---

### Phase 1: MITRE Data Extraction

**Semantic Change**: Add MITRE ATT&CK data extraction from playbook tags to the types layer.

**Deliverables**:
- New `_extract_mitre_data` function
- Updated `transform_reduced_playbook_attack` with `include_mitre_techniques` parameter
- Updated `transform_full_playbook_attack` with `include_mitre_techniques` parameter

**Implementation Details**:

1. **`_extract_mitre_data(tags_data)` function**:
   - Accept the raw `tags` list from the playbook API response
   - Iterate through the tags array looking for tag items where `name` matches
     `MITRE_Tactic`, `MITRE_Technique`, or `MITRE_Sub_Technique`
   - For each matching tag, iterate through its `values` array
   - For `MITRE_Tactic`: extract `{name: value.displayName or value.value}`
   - For `MITRE_Technique`: extract `{id: value.value, display_name: value.displayName,
     url: constructed_url}`. URL format: `https://attack.mitre.org/techniques/{id}/`
   - For `MITRE_Sub_Technique`: extract same structure as technique.
     URL format: replace `.` with `/` in the ID, e.g., `T1021.001` becomes
     `https://attack.mitre.org/techniques/T1021/001/`
   - Return dict with keys `mitre_tactics`, `mitre_techniques`, `mitre_sub_techniques`
     (each a list, empty if no matching tags found)
   - Handle edge cases: None tags, empty list, non-list tags, missing value/displayName fields

2. **Update `transform_reduced_playbook_attack`**:
   - Add `include_mitre_techniques: bool = False` parameter
   - When True, call `_extract_mitre_data(attack_data.get('tags', []))` and merge result into output dict
   - When False (default), behavior unchanged - return same 5 fields as before

3. **Update `transform_full_playbook_attack`**:
   - Add `include_mitre_techniques: bool = False` parameter
   - When True, call `_extract_mitre_data(attack_data.get('tags', []))` and merge result into output dict
   - When False (default), behavior unchanged

| File | Change |
|------|--------|
| `safebreach_mcp_playbook/playbook_types.py` | Add `_extract_mitre_data`, update both transform functions |

**Automated Verification**:
- Run: `uv run pytest safebreach_mcp_playbook/tests/test_playbook_types.py -v -k "mitre or Mitre or transform"`
- Expected: All existing transform tests pass (no regressions), new MITRE tests added in Phase 5

**Git Commit**: `feat(playbook): add MITRE ATT&CK data extraction from tags (SAF-28305)`

---

### Phase 2: MITRE Filtering

**Semantic Change**: Add MITRE-based filtering to the attack filter function.

**Deliverables**:
- Updated `filter_attacks_by_criteria` with `mitre_technique_filter` and `mitre_tactic_filter` parameters

**Implementation Details**:

1. **Update `filter_attacks_by_criteria`**:
   - Add `mitre_technique_filter: Optional[str] = None` parameter
   - Add `mitre_tactic_filter: Optional[str] = None` parameter
   - For `mitre_technique_filter`: Split the input by comma, strip whitespace from each value,
     convert each to lowercase. For each attack, check if **any** filter value matches **any**
     item in `mitre_techniques` or `mitre_sub_techniques` (OR logic across values). Each value
     is matched as a case-insensitive partial match against both `id` and `display_name` fields.
     Attacks without MITRE data (missing keys or empty lists) are excluded when this filter
     is active. Single values work identically to previous behavior (no comma = one value).
   - For `mitre_tactic_filter`: Same comma-separated OR logic. Split by comma, strip whitespace,
     lowercase. For each attack, check if **any** filter value partially matches **any** tactic
     `name` in `mitre_tactics` (case-insensitive). Attacks without MITRE data are excluded.
   - Both filters integrate into the existing sequential filtering chain
     (applied after existing filters)

| File | Change |
|------|--------|
| `safebreach_mcp_playbook/playbook_types.py` | Update `filter_attacks_by_criteria` with MITRE filter params |

**Automated Verification**:
- Run: `uv run pytest safebreach_mcp_playbook/tests/test_playbook_types.py -v -k "filter"`
- Expected: All existing filter tests pass (no regressions), new MITRE filter tests added in Phase 5

**Git Commit**: `feat(playbook): add MITRE technique and tactic filtering (SAF-28305)`

---

### Phase 3: Business Logic Integration

**Semantic Change**: Wire MITRE parameters through the business logic layer with auto-enable behavior.

**Deliverables**:
- Updated `sb_get_playbook_attacks` with MITRE params and auto-enable logic
- Updated `sb_get_playbook_attack_details` with `include_mitre_techniques` param

**Implementation Details**:

1. **Update `sb_get_playbook_attacks`**:
   - Add three new parameters: `include_mitre_techniques: bool = False`,
     `mitre_technique_filter: Optional[str] = None`, `mitre_tactic_filter: Optional[str] = None`
   - Compute `needs_mitre = include_mitre_techniques or bool(mitre_technique_filter)
     or bool(mitre_tactic_filter)`. This determines whether MITRE data is needed
     for filtering or output.
   - In the transform step, pass `include_mitre_techniques=needs_mitre` to
     `transform_reduced_playbook_attack` for each attack
   - Pass `mitre_technique_filter` and `mitre_tactic_filter` to `filter_attacks_by_criteria`
   - Add MITRE filter values to `applied_filters` dict when active
   - Add input validation: no new validation needed beyond existing patterns

2. **Update `sb_get_playbook_attack_details`**:
   - Add `include_mitre_techniques: bool = False` parameter
   - Pass through to `transform_full_playbook_attack` call

| File | Change |
|------|--------|
| `safebreach_mcp_playbook/playbook_functions.py` | Update both `sb_get_*` functions with MITRE params |

**Automated Verification**:
- Run: `uv run pytest safebreach_mcp_playbook/tests/test_playbook_functions.py -v`
- Expected: All existing function tests pass (no regressions), new MITRE tests added in Phase 6

**Git Commit**: `feat(playbook): integrate MITRE params into business logic (SAF-28305)`

---

### Phase 4: MCP Tool Interface

**Semantic Change**: Expose MITRE parameters in MCP tool definitions and render MITRE in markdown output.

**Deliverables**:
- Updated `get_playbook_attacks` tool with MITRE params and rendering
- Updated `get_playbook_attack_details` tool with MITRE param and rendering

**Implementation Details**:

1. **Update `get_playbook_attacks` tool registration**:
   - Add three parameters to function signature: `include_mitre_techniques: bool = False`,
     `mitre_technique_filter: Optional[str] = None`, `mitre_tactic_filter: Optional[str] = None`
   - Update tool description string to document the new parameters including multi-value
     comma-separated support with OR logic
   - Pass new params through to `sb_get_playbook_attacks` call
   - In the markdown rendering loop, after the existing fields (name, description, dates),
     add MITRE section when present:
     - `**MITRE Tactics:** Discovery, Lateral Movement` (comma-separated tactic names)
     - `**MITRE Techniques:** (T1046) Network Service Discovery, (T1021) Remote Services`
       (comma-separated technique display names)
     - `**MITRE Sub-Techniques:** (T1021.001) Remote Desktop Protocol`
       (comma-separated sub-technique display names)
     - Only render each subsection if the list is non-empty

2. **Update `get_playbook_attack_details` tool registration**:
   - Add `include_mitre_techniques: bool = False` parameter
   - Update tool description string
   - Pass through to `sb_get_playbook_attack_details` call
   - In markdown rendering, add MITRE section after existing content when present:
     - Section header `## MITRE ATT&CK Mapping`
     - Render tactics, techniques (with URLs), and sub-techniques (with URLs) as bullet lists

| File | Change |
|------|--------|
| `safebreach_mcp_playbook/playbook_server.py` | Update both tool registrations with MITRE params and rendering |

**Automated Verification**:
- Run: `uv run pytest safebreach_mcp_playbook/tests/ -v -m "not e2e"`
- Expected: Full playbook unit test suite passes (server init tests + all types/functions tests)
- No server-level tool tests needed: server layer is thin pass-through, covered by
  functions unit tests + E2E tests in Phase 7

**Git Commit**: `feat(playbook): expose MITRE params in MCP tool interface (SAF-28305)`

---

### Phase 5: Tests - Types Layer

**Semantic Change**: Add comprehensive unit tests for MITRE extraction, transformation, and filtering.

**Deliverables**:
- Tests for `_extract_mitre_data`
- Tests for MITRE in transform functions
- Tests for MITRE filtering

**Implementation Details**:

1. **Add test fixtures** with MITRE tag data:
   - `sample_attack_with_mitre`: Raw attack with `MITRE_Tactic`, `MITRE_Technique`,
     `MITRE_Sub_Technique` in tags array (using the real API structure discovered)
   - `sample_attack_no_mitre`: Raw attack without any MITRE tags
   - `sample_attacks_with_mitre_list`: List of 3+ attacks with varying MITRE data for filter tests

2. **`TestMitreExtraction` class**:
   - Test complete MITRE extraction (all three categories present)
   - Test partial extraction (technique only, no sub-technique)
   - Test empty/None/malformed tags
   - Test URL construction for techniques (e.g., `T1046` -> correct URL)
   - Test URL construction for sub-techniques (e.g., `T1021.001` -> URL with `/` not `.`)

3. **Update `TestTransformationFunctions`**:
   - Test `transform_reduced_playbook_attack` with `include_mitre_techniques=False` -> no MITRE keys
   - Test `transform_reduced_playbook_attack` with `include_mitre_techniques=True` -> MITRE keys present
   - Test `transform_full_playbook_attack` with `include_mitre_techniques=True` -> MITRE keys present
   - Verify existing fields unchanged when MITRE is enabled

4. **`TestMitreFiltering` class**:
   - Filter by technique ID: `mitre_technique_filter="T1046"` matches attack with that technique
   - Filter by technique name: `mitre_technique_filter="Network Service"` matches display name
   - Filter by sub-technique: `mitre_technique_filter="T1021.001"` matches sub-technique
   - Filter by tactic: `mitre_tactic_filter="Discovery"` matches tactic name
   - Combined: MITRE filter + name filter
   - No matches: filter that matches nothing returns empty list
   - Attacks without MITRE data excluded when MITRE filter active

| File | Change |
|------|--------|
| `safebreach_mcp_playbook/tests/test_playbook_types.py` | Add `TestMitreExtraction` class, extend `TestTransformationFunctions`, extend `TestFilteringFunctions` |

**Automated Verification**:
- Run: `uv run pytest safebreach_mcp_playbook/tests/test_playbook_types.py -v`
- Expected: All tests pass (existing 26 + ~14 new MITRE tests = ~40 total)

**Git Commit**: `test(playbook): add unit tests for MITRE extraction and filtering (SAF-28305)`

---

### Phase 6: Tests - Functions Layer

**Semantic Change**: Add unit tests for MITRE parameter integration in business logic functions.

**Deliverables**:
- Updated mock data with MITRE tags
- Tests for MITRE pass-through in both functions
- Tests for auto-enable behavior

**Implementation Details**:

1. **Update existing mock API response data** in test fixtures:
   - Add MITRE tags to the `tags` array in mock attack objects (following the real API structure:
     tag dicts with `id`, `name`, `values` containing `id`, `sort`, `value`, `displayName`)
   - Ensure at least one mock attack has MITRE tags and one does not

2. **Test `sb_get_playbook_attacks` with MITRE**:
   - Call with `include_mitre_techniques=True`: verify MITRE data in results
   - Call with `mitre_technique_filter="T1046"`: verify filtered results and auto-enable
   - Call with `mitre_tactic_filter="Discovery"`: verify filtered results
   - Call with MITRE filter + `include_mitre_techniques=False`:
     verify MITRE still present (auto-enable)
   - Verify `applied_filters` metadata includes MITRE filter values

3. **Test `sb_get_playbook_attack_details` with MITRE**:
   - Call with `include_mitre_techniques=True`: verify MITRE data in result
   - Call with `include_mitre_techniques=False` (default): verify no MITRE data

| File | Change |
|------|--------|
| `safebreach_mcp_playbook/tests/test_playbook_functions.py` | Add `sample_attack_data_with_mitre` fixture, extend `TestGetPlaybookAttacks` (5 tests), extend `TestGetPlaybookAttackDetails` (2 tests) |

**Automated Verification**:
- Run: `uv run pytest safebreach_mcp_playbook/tests/test_playbook_functions.py -v`
- Expected: All tests pass (existing 15 + ~7 new MITRE tests = ~22 total)

**Git Commit**: `test(playbook): add MITRE integration tests for business logic (SAF-28305)`

---

### Phase 7: Documentation & E2E

**Semantic Change**: Update documentation and add E2E test confirming real API MITRE data.

**Deliverables**:
- Updated `CLAUDE.md` tool descriptions
- E2E test for MITRE data from real SafeBreach API

**Implementation Details**:

1. **Update `CLAUDE.md`**:
   - In the Playbook Server tools section, update `get_playbook_attacks` description to mention
     MITRE support (`include_mitre_techniques`, `mitre_technique_filter`, `mitre_tactic_filter`)
   - Update `get_playbook_attack_details` description to mention `include_mitre_techniques`
   - Add a brief note under "Filtering and Search Capabilities" about MITRE filtering

2. **E2E test**:
   - Add test with `@pytest.mark.e2e` and `@skip_e2e` decorators
   - Call `sb_get_playbook_attacks` with `include_mitre_techniques=True` against real console
   - Assert that at least some attacks in the result have non-empty `mitre_techniques` arrays
   - Optionally test MITRE filtering with a known technique ID

| File | Change |
|------|--------|
| `CLAUDE.md` | Update playbook tool descriptions and MITRE filtering section |
| `safebreach_mcp_playbook/tests/test_e2e.py` | Extend `test_verbosity_levels_real_api`, add `test_mitre_data_real_api`, add `test_mitre_filtering_real_api` |

**Automated Verification**:
- Unit regression: `uv run pytest safebreach_mcp_playbook/tests/ -v -m "not e2e"`
- E2E: `source .vscode/set_env.sh && uv run pytest safebreach_mcp_playbook/tests/test_e2e.py -v -m "e2e"`
- Cross-server regression: `uv run pytest safebreach_mcp_config/tests/ safebreach_mcp_data/tests/ safebreach_mcp_utilities/tests/ safebreach_mcp_playbook/tests/ safebreach_mcp_studio/tests/ -v -m "not e2e"`
- Expected: All unit tests pass, E2E confirms MITRE data from real API, zero cross-server regressions

**Git Commit**: `docs: update CLAUDE.md with MITRE playbook support (SAF-28305)`

## 10. Risks and Assumptions

### Assumptions

| Assumption | Impact if Wrong | Mitigation |
|------------|----------------|------------|
| MITRE data is always in the `tags` array for all consoles | MITRE extraction returns empty for some consoles | Graceful empty-list handling already in design |
| Tag category names (`MITRE_Tactic`, etc.) are stable across API versions | Extraction breaks silently | Use constants for tag names, log warnings if expected tags missing |
| ATT&CK URL format is stable (`/techniques/{id}/`) | Broken links in output | URLs are constructed, not hardcoded - easy to update |
| Sub-technique IDs always use `.` notation (e.g., `T1021.001`) | URL construction breaks | Validate format before URL construction, fall back to ID-only |

### Technical Risks

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| New MITRE tag categories added to API in future | Missing data | Low | Design is extensible - add new tag names to extraction |
| Existing tests break due to mock data changes | Test failures | Low | Only add MITRE to new fixtures, don't modify existing ones |

## 11. Future Enhancements

- **Separate `mitre_sub_technique_filter`**: Currently `mitre_technique_filter` searches both
  techniques and sub-techniques. A dedicated sub-technique filter could be added for precise
  sub-technique-only queries if customers need it. The internal data extraction already
  separates the lists, so adding this filter would be a ~10-line change.
- **MITRE Software extraction**: The `tags` array also contains `MITRE Software` data
  (23.7% coverage) with software IDs like `S0414`. Could be added as
  `include_mitre_software` parameter.
- **NIST Control mapping**: `NIST_Control` tag category exists in the API but is out of scope.
- **CVE extraction**: `CVE` tag category exists in the API. Could enable vulnerability-based queries.
- **MITRE ATT&CK Navigator export**: Generate Navigator layer JSON for visual coverage mapping.
- **Pipeline restructuring**: Filter on raw data before transform for better efficiency at scale.

## 12. Executive Summary

- **Issue/Feature Description**: Intuit customer needs MITRE ATT&CK technique/tactic data in bulk
  playbook attack listings, not just one-at-a-time via attack details.
- **What Will Be Built**: Optional MITRE data inclusion (`include_mitre_techniques`) for both
  `get_playbook_attacks` and `get_playbook_attack_details` tools, plus MITRE-based filtering
  (`mitre_technique_filter`, `mitre_tactic_filter`) for the bulk listing tool.
- **Key Technical Decisions**: Extract MITRE from existing `tags` array in cached API response
  (no new API calls). Follow Data Server's `include_mitre_techniques` pattern. Construct ATT&CK
  URLs from technique IDs. Auto-enable MITRE when filters are active.
- **Scope**: 4 source files + tests + documentation. 7 implementation phases.
- **Business Value**: Enables weekly MITRE ATT&CK TTP coverage comparison for Intuit and
  all MCP users. Adds powerful MITRE-based search to playbook tools.
