# JIRA Update for SAF-28780

## Updated Title

[safebreach-mcp] MITRE tactic filter cannot filter by tactic ID (TA0006) — API lacks tactic IDs

## Updated Description

### Bug Summary

The `mitre_tactic_filter` parameter in `get_playbook_attacks` does not support filtering by MITRE
ATT&CK tactic IDs (e.g. "TA0006"). When a user or AI agent queries by tactic ID, the filter returns
zero results and the agent falls back to telling the user to "do it manually" in the UI.

### Customer Report

Reported by Jonathan Tillman via Slack (`#general`, 2026-02-23): "MCP was unable to list attacks
for the top-Level Tactic TA0006 Credential Access." The AI agent suggested he do it manually in the
UI instead.

### E2E API Verification (2026-03-04)

Direct API testing against `pentest01` console (9,632 attacks) confirmed:

**The SafeBreach playbook API does NOT provide tactic IDs in the tag data.** For `MITRE_Tactic`
tags, both `value` and `displayName` contain the tactic name only:

```
MITRE_Tactic:    {"value": "Credential Access", "displayName": "Credential Access"}
MITRE_Technique: {"value": "T1046", "displayName": "(T1046) Network Service Discovery"}
```

All 12 unique tactic values follow this pattern — none contain a tactic ID like "TA0006".

### Root Cause: Missing Data at API/Content Level

The MCP cannot filter by tactic ID because the upstream playbook API
(`/api/kb/vLatest/moves?details=true`) does not include tactic IDs in the `MITRE_Tactic` tag data.
The MCP implementation correctly exposes what the API provides.

**This is not an MCP gap** — the MCP layer should expose and filter the data the API provides, not
compensate for missing data. The tactic-to-ID mapping (e.g., "Credential Access" → "TA0006") is
content/domain knowledge that belongs in the playbook data source.

### Current MCP Behavior (Correct)

- `mitre_tactic_filter="Credential Access"` — works (matches tactic name)
- `mitre_tactic_filter="Discovery"` — works (matches tactic name)
- `mitre_tactic_filter="TA0006"` — returns zero results (no tactic ID in data to match)

### Recommendation

The proper fix should be at the **content/playbook API level**:

1. **Content-manager team** should enrich `MITRE_Tactic` tag values to include the tactic ID — either
   in the `value` field (like techniques store "T1046") or in the `displayName` field (like techniques
   store "(T1046) Network Service Discovery")
2. Once the API provides tactic IDs, the MCP extraction (`_extract_mitre_data()`) will automatically
   pick them up and enable ID-based filtering with **zero MCP code changes**

### Alternative (if API change is not feasible)

If enriching the playbook API is out of scope, the MCP could add a static mapping of the 14 MITRE
Enterprise tactic names to their IDs. However:
- Adds maintenance burden (new tactics, though rare — last was 2020)
- Conflates the MCP's role as a data access layer with data enrichment
- Should be a conscious architectural decision, not a default

### References

- Original MITRE implementation: SAF-28305 (PRD at `prds/SAF-28305/prd.md`)
- Slack thread: #general, 2026-02-23, Jonathan Tillman
- E2E verification: pentest01 console, 9,632 attacks, 12 unique tactic names — none with tactic IDs
- MITRE ATT&CK tactic reference: https://attack.mitre.org/tactics/TA0006/
