# Ticket Summary: SAF-28305

## Title
Add MITRE ATT&CK tactic/technique tags to playbook tools with filtering support

## Description
Add MITRE ATT&CK technique and tactic data to both `get_playbook_attacks` (bulk listing) and `get_playbook_attack_details` (single attack) tools, plus MITRE-based filtering capabilities. This addresses Intuit's need to compare MITRE ATT&CK TTPs vs SafeBreach available TTPs on a weekly cadence.

### Key Discovery
MITRE data is embedded within the `tags` array in the playbook API response (`/api/kb/vLatest/moves?details=true`), under tag categories `MITRE_Tactic`, `MITRE_Technique`, `MITRE_Sub_Technique`, and `MITRE Software`. Coverage: ~42.6% of 9,599 attacks have MITRE technique/tactic mappings.

### Implementation Approach
Follow Approach C: Uniform transform enhancement + MITRE filtering support. Add optional `include_mitre_techniques` parameter (default `False`) to both tools for consistency with the Data Server pattern, plus `mitre_technique_filter` and `mitre_tactic_filter` for bulk search.

## Changes Required

### 1. `playbook_types.py` - Data Transformations

**New function: `_extract_mitre_data(tags_data)`**
- Extracts `MITRE_Tactic`, `MITRE_Technique`, `MITRE_Sub_Technique` from the tags array
- Returns structured dict:
  ```python
  {
      'mitre_tactics': [{'name': 'Discovery'}],
      'mitre_techniques': [
          {'id': 'T1046', 'display_name': '(T1046) Network Service Discovery',
           'url': 'https://attack.mitre.org/techniques/T1046/'}
      ],
      'mitre_sub_techniques': [
          {'id': 'T1021.001', 'display_name': '(T1021.001) Remote Desktop Protocol',
           'url': 'https://attack.mitre.org/techniques/T1021/001/'}
      ]
  }
  ```
- Construct ATT&CK URLs from technique IDs (replace `.` with `/` for sub-techniques)

**Update `transform_reduced_playbook_attack(attack_data, include_mitre_techniques=False)`**
- When `include_mitre_techniques=True`, extract MITRE data from `attack_data['tags']` and add to result

**Update `transform_full_playbook_attack(attack_data, ..., include_mitre_techniques=False)`**
- Same MITRE extraction when enabled

**Update `filter_attacks_by_criteria(attacks, ..., mitre_technique_filter=None, mitre_tactic_filter=None)`**
- `mitre_technique_filter`: Case-insensitive partial match on technique ID or display name in `mitre_techniques` + `mitre_sub_techniques` (e.g., "T1046" or "Network Service")
- `mitre_tactic_filter`: Case-insensitive partial match on tactic name in `mitre_tactics` (e.g., "Discovery", "Lateral")
- Note: MITRE data must be present in attack objects for filtering to work

### 2. `playbook_functions.py` - Business Logic

**Update `sb_get_playbook_attacks(...)`**
- Add params: `include_mitre_techniques: bool = False`, `mitre_technique_filter: Optional[str] = None`, `mitre_tactic_filter: Optional[str] = None`
- When MITRE filters are active, auto-enable `include_mitre_techniques` in the transform step (filter needs MITRE data to match against)
- Pass MITRE filters to `filter_attacks_by_criteria`
- Add MITRE filter info to `applied_filters` metadata

**Update `sb_get_playbook_attack_details(...)`**
- Add param: `include_mitre_techniques: bool = False`
- Pass through to `transform_full_playbook_attack`

### 3. `playbook_server.py` - MCP Tool Definitions

**Update `get_playbook_attacks` tool**
- Add parameters:
  - `include_mitre_techniques: bool = False` - Include MITRE ATT&CK tactics, techniques, and sub-techniques
  - `mitre_technique_filter: Optional[str] = None` - Filter by MITRE technique ID or name (partial, case-insensitive). Matches against both techniques and sub-techniques
  - `mitre_tactic_filter: Optional[str] = None` - Filter by MITRE tactic name (partial, case-insensitive)
- Update tool description to document new params
- Add MITRE rendering in markdown output (tactics, techniques, sub-techniques per attack)

**Update `get_playbook_attack_details` tool**
- Add parameter: `include_mitre_techniques: bool = False`
- Update tool description
- Add MITRE section in markdown output

### 4. Tests

**Update `test_playbook_types.py`**
- Test `_extract_mitre_data` with:
  - Complete MITRE tags (tactic + technique + sub-technique)
  - Partial MITRE tags (technique only, no sub-technique)
  - No MITRE tags (empty result)
  - Malformed/missing tags data
- Test MITRE in `transform_reduced_playbook_attack` (on/off)
- Test MITRE in `transform_full_playbook_attack` (on/off)
- Test MITRE filtering in `filter_attacks_by_criteria`:
  - Filter by technique ID (e.g., "T1046")
  - Filter by technique name (e.g., "Network Service")
  - Filter by tactic name (e.g., "Discovery")
  - Combined MITRE + existing filters
  - No matches

**Update `test_playbook_functions.py`**
- Update mock API response data to include MITRE tags in the tags array
- Test `sb_get_playbook_attacks` with `include_mitre_techniques=True`
- Test `sb_get_playbook_attacks` with MITRE filters
- Test auto-enable MITRE when MITRE filter is used
- Test `sb_get_playbook_attack_details` with `include_mitre_techniques=True`

**Update `test_playbook_server.py`** (if exists)
- Test new parameters in tool invocations

### 5. Documentation Updates

**Update `CLAUDE.md`**
- Update `get_playbook_attacks` tool description to mention MITRE support
- Update `get_playbook_attack_details` tool description
- Add MITRE filtering capabilities section

## Acceptance Criteria

1. `get_playbook_attacks` with `include_mitre_techniques=True` returns MITRE tactics, techniques, and sub-techniques for each attack in the paginated results
2. `get_playbook_attack_details` with `include_mitre_techniques=True` returns MITRE data for a specific attack
3. `mitre_technique_filter` filters attacks by technique ID (e.g., "T1046") or name (e.g., "Network Service Discovery") - case-insensitive partial match
4. `mitre_tactic_filter` filters attacks by tactic name (e.g., "Discovery") - case-insensitive partial match
5. MITRE filters can be combined with all existing filters
6. When MITRE filter is used but `include_mitre_techniques=False`, MITRE data is auto-included (needed for filtering)
7. Default behavior (without MITRE params) is unchanged - no performance impact
8. ATT&CK URLs are constructed from technique IDs (e.g., `https://attack.mitre.org/techniques/T1046/`)
9. All existing unit tests pass without modification
10. New unit tests cover MITRE extraction, transformation, filtering, and edge cases
11. E2E test confirms MITRE data is returned from real SafeBreach API

## Performance Impact
- Minimal: MITRE data is already in the cached API response (tags array)
- When `include_mitre_techniques=False` (default), no extra processing
- When enabled, dict lookups for 9,599 attacks during transform is ~milliseconds
- No additional API calls required

## Out of Scope
- MITRE Software extraction (could be a follow-up)
- NIST Control mapping
- CVE extraction from tags
- Restructuring the filter/transform pipeline flow
