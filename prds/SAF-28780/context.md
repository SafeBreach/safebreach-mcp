# Context: SAF-28780 - MITRE tactic filter does not support tactic IDs

## Status: Implementation Complete (Approach A — Static Mapping)

## JIRA Ticket Summary

- **ID**: SAF-28780
- **Title**: [safebreach-mcp] MITRE tactic filter cannot filter by tactic ID (TA0006) — API lacks tactic IDs
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

### E2E API Verification (2026-03-04)

Direct API testing against `pentest01` console (9,632 attacks) confirmed:

**The SafeBreach playbook API does NOT provide tactic IDs in the tag data.**

All 12 unique `MITRE_Tactic` values have identical `value` and `displayName` — both contain only
the tactic name:

```
value="Collection"         displayName="Collection"
value="Command And Control" displayName="Command And Control"
value="Credential Access"  displayName="Credential Access"
value="Defense Evasion"    displayName="Defense Evasion"
value="Discovery"          displayName="Discovery"
value="Execution"          displayName="Execution"
value="Exfiltration"       displayName="Exfiltration"
value="Impact"             displayName="Impact"
value="Initial Access"     displayName="Initial Access"
value="Lateral Movement"   displayName="Lateral Movement"
value="Persistence"        displayName="Persistence"
value="Privilege Escalation" displayName="Privilege Escalation"
```

Compare with `MITRE_Technique` where `value` = technique ID:
```json
{"value": "T1046", "displayName": "(T1046) Network Service Discovery"}
```

### Root Cause: Missing Data at API/Content Level

The MCP cannot filter by tactic ID because the upstream SafeBreach playbook API
(`/api/kb/vLatest/moves?details=true`) does not include tactic IDs in the `MITRE_Tactic` tag data.
The MCP implementation correctly exposes what the API provides.

### Current MCP Behavior (Correct)

- `mitre_tactic_filter="Credential Access"` — **works** (matches tactic name)
- `mitre_tactic_filter="Discovery"` — **works** (matches tactic name)
- `mitre_tactic_filter="TA0006"` — **returns zero results** (no tactic ID in data to match)

### Code References

- `safebreach_mcp_playbook/playbook_types.py` — `_extract_mitre_data()`: lines ~97-102
- `safebreach_mcp_playbook/playbook_types.py` — `_attack_matches_mitre_tactic()`: lines ~371-383
- `safebreach_mcp_playbook/playbook_server.py` — Tactic rendering in markdown

## Brainstorming Results

### Approaches Considered

**Approach A: Static Mapping Dict** — Add a `MITRE_TACTIC_MAPPING` dict in `playbook_types.py`
mapping 14 tactic names to their IDs (TA0001-TA0043) and ATT&CK URLs. Enrich tactic extraction
at transform time.
- Pros: Simple, fast, no external dependencies, easy to test
- Cons: Maintenance burden for new tactics, conflates MCP's data access role with enrichment

**Approach B: Dynamic MITRE ATT&CK Fetch** — Fetch tactic mappings from MITRE's STIX data at
server startup.
- Pros: Always up to date
- Cons: Network dependency, ~2MB download, startup latency, failure mode complexity

**Approach C: No MCP Change** — The playbook API should be enriched at the content/source level.
The MCP correctly exposes what the API provides.
- Pros: Clean architecture, zero MCP maintenance, fixes the problem at the root
- Cons: Requires content-manager team involvement, longer timeline

### Previously Chosen: Approach C — No MCP Change (Content-Level Fix)

Initially recommended, but reconsidered since the content-manager team fix has a longer timeline
and the customer needs a solution now.

### Final Decision: Approach A — Static Mapping Dict

**Rationale:**
1. Customer-facing issue needs a timely resolution
2. MITRE ATT&CK Enterprise tactics are extremely stable (14 tactics, last addition was 2020)
3. Minimal code change — only a translation layer before existing filter logic
4. Zero impact on existing name-based filtering behavior
5. Graceful fallback for unknown tactic IDs (passed through unchanged)

### Implementation Summary (2026-03-09)

**Files modified:**
- `safebreach_mcp_playbook/playbook_types.py` — Added `MITRE_TACTIC_ID_TO_NAME` mapping (14 tactics),
  `_resolve_tactic_filter_value()` helper with ID normalization (e.g. "TA6" → "TA0006" → "credential access"),
  and updated `filter_attacks_by_criteria()` to translate tactic IDs before filtering
- `safebreach_mcp_playbook/playbook_server.py` — Updated tool docstring to mention tactic ID support
- `safebreach_mcp_playbook/tests/test_playbook_types.py` — Added 13 new tests (7 filtering + 6 resolver unit tests)
- `safebreach_mcp_playbook/tests/test_playbook_functions.py` — Added 1 end-to-end test through `sb_get_playbook_attacks()`

**Test results:** 561 tests passing across all servers (111 playbook tests)

## References

- Original MITRE implementation: SAF-28305 (PRD at `prds/SAF-28305/prd.md`)
- Slack thread: #general, 2026-02-23, Jonathan Tillman
- E2E verification: pentest01 console, 9,632 attacks, 12 unique tactic names — none with IDs
- MITRE ATT&CK tactic reference: https://attack.mitre.org/tactics/TA0006/
