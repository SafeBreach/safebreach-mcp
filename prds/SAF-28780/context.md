# Context: SAF-28780 - MITRE tactic filter does not support tactic IDs

## Status: Phase 4: Investigation Complete

## JIRA Ticket Summary

- **ID**: SAF-28780
- **Title**: [safebreach-mcp] MITRE tactic filter does not support tactic IDs (e.g. TA0006)
- **Type**: Bug
- **Priority**: Medium
- **Status**: To Do
- **Assignee**: Yossi Attas
- **Sprint**: Saf sprint 84

## Customer Report

Reported by Jonathan Tillman via Slack (#general, 2026-02-23):
"MCP was unable to list attacks for the top-Level Tactic TA0006 Credential Access."
The AI agent suggested he do it manually in the UI instead.

## Investigation Findings

### Root Cause: Asymmetric Data Extraction

In `playbook_types.py`, the `_extract_mitre_data()` function treats tactics differently from techniques:

**Tactics (lines 97-102)** — stores only `{name}`:
```python
if tag_name == 'MITRE_Tactic':
    for val in values:
        if isinstance(val, dict):
            name = val.get('displayName') or val.get('value', '')
            if name:
                result['mitre_tactics'].append({'name': name})
```

**Techniques (lines 104-115)** — stores `{id, display_name, url}`:
```python
elif tag_name == 'MITRE_Technique':
    for val in values:
        if isinstance(val, dict):
            tech_id = val.get('value', '')
            display_name = val.get('displayName', '')
            if tech_id:
                url = f"https://attack.mitre.org/techniques/{tech_id}/"
                result['mitre_techniques'].append({
                    'id': tech_id,
                    'display_name': display_name,
                    'url': url
                })
```

### Filtering Asymmetry

**`_attack_matches_mitre_tactic()` (lines 371-383)** — only checks `name`:
```python
for fv in filter_values:
    for tactic in tactics:
        if fv in tactic.get('name', '').lower():
            return True
```

**`_attack_matches_mitre_technique()` (lines 352-368)** — checks both `id` and `display_name`:
```python
for fv in filter_values:
    for tech in techniques:
        if fv in tech.get('id', '').lower() or fv in tech.get('display_name', '').lower():
            return True
```

### Server Rendering

In `playbook_server.py`, tactic rendering only uses `name`:
- `get_playbook_attacks` (line ~115-127): `tactic_names = ', '.join(t.get('name', '') for t in mitre_tactics)`
- `get_playbook_attack_details` (line ~233-236): `f"- {t.get('name', 'Unknown')}"`

Techniques are rendered with IDs and URLs, tactics are not.

### Test Fixture Data Structure

Current test fixtures in `test_playbook_types.py` (lines 540-569):
```python
{
    "id": 10,
    "name": "MITRE_Tactic",
    "values": [
        {"id": 1, "sort": 1, "value": "Discovery", "displayName": "Discovery"}
    ]
}
```

**Note**: The test fixture stores the tactic name in both `value` and `displayName`. The real API
likely stores the tactic ID (e.g. "TA0007") in `value` and the name in `displayName`. This needs
E2E verification to confirm the real API structure before fixing.

### Existing Test Coverage (Gaps)

| Test File | Tests Tactic ID? | Tests Tactic Name? |
|-----------|------------------|--------------------|
| test_playbook_types.py - TestMitreExtraction | No | Yes |
| test_playbook_types.py - TestMitreFiltering | No | Yes ("Discovery") |
| test_playbook_functions.py - TestMitreGetPlaybookAttacks | No | Yes ("Discovery") |
| test_e2e.py - test_mitre_filtering_real_api | No | Yes ("Discovery") |

### Documentation

Both `playbook_server.py` and `playbook_types.py` docstrings say "tactic names" for the filter
parameter, not "tactic IDs or names".

### Files to Modify

1. `safebreach_mcp_playbook/playbook_types.py` — extraction + filtering
2. `safebreach_mcp_playbook/playbook_server.py` — rendering + docstrings
3. `safebreach_mcp_playbook/tests/test_playbook_types.py` — add tactic ID tests
4. `safebreach_mcp_playbook/tests/test_playbook_functions.py` — add tactic ID tests
5. `safebreach_mcp_playbook/tests/test_e2e.py` — add tactic ID E2E test
6. `CLAUDE.md` — update documentation

### Key Question: Real API Tactic Data Structure

The test fixtures currently have `"value": "Discovery"` for tactics, but for techniques they have
`"value": "T1046"`. The real API likely has `"value": "TA0006"` for tactics (matching the pattern).
This needs to be verified via E2E test or API call before we can confidently design the fix.

## Brainstorming Results

(Pending Phase 5)
