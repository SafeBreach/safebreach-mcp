# Ticket Preparation Context: SAF-28305

## Status: Phase 6: PRD Created

## Ticket Info
- **Key**: SAF-28305
- **Summary**: [intuit][safebreach-mdp] Add MITRE tags to responses of the playbook tools
- **Priority**: High
- **Status**: To Do
- **Assignee**: Yossi Attas
- **Created**: 2026-02-16

## Original Description
Intuit (Efi) request: `get_playbook_attacks` (bulk listing of 9,492 attacks) does not return MITRE tactic/technique mappings/tags. Only `get_playbook_attack_details` (single attack) returns them.

Use case: Compare MITRE ATT&CK TTPs vs SafeBreach available TTPs on a weekly cadence.

## Repositories
- safebreach-mcp (`/Users/yossiattas/Public/safebreach-mcp`)

## Investigation Findings

### Current Architecture
- **Playbook Types** (`playbook_types.py`): Reduced format (listing) has 5 fields: name, id, description, modifiedDate, publishedDate. Full format adds fix_suggestions, tags, params. **No MITRE fields in either mapping.**
- **Playbook Functions** (`playbook_functions.py`): API endpoint `GET /api/kb/vLatest/moves?details=true` fetches all attacks with caching. Current code does not extract or check for MITRE data in raw response.
- **Playbook Server** (`playbook_server.py`): `get_playbook_attacks` has no MITRE parameter. `get_playbook_attack_details` has `include_tags` but tags are categorization tags (sector, approach), NOT MITRE techniques.

### Reference Implementations
- **Data Server** (`data_types.py` lines 216-224): MITRE extracted from `MITRE_Technique` field as `[{"value": "T1234", "displayName": "...", "url": "..."}]`. Uses optional `include_mitre_techniques=True` parameter.
- **Studio Server** (`studio_types.py` line 326): Includes `MITRE_Tactic` field directly (always).

### Critical Unknowns
1. Does `/api/kb/vLatest/moves?details=true` include MITRE data in the raw API response?
2. What field name does the playbook API use for MITRE data?
3. How many MITRE techniques per attack on average?
4. Are `tags` (categorization) separate from MITRE mappings?

### Performance Considerations
- 9,492 attacks in cache. If each has 1-5 MITRE techniques, that's potentially 50K+ objects.
- Pagination is at PAGE_SIZE=10, so individual page responses are manageable.
- Optional parameter pattern (default False) avoids bloat for non-MITRE queries.

### Key Files
- `safebreach_mcp_playbook/playbook_types.py` - Data transformations
- `safebreach_mcp_playbook/playbook_functions.py` - Business logic
- `safebreach_mcp_playbook/playbook_server.py` - MCP tool definitions
- `safebreach_mcp_playbook/tests/` - Unit tests
- `safebreach_mcp_data/data_types.py` (lines 216-224) - Reference MITRE pattern

## Brainstorming Results

### API Discovery
MITRE data is embedded within the `tags` array (not a separate top-level field):
- `MITRE_Tactic`: 42.6% coverage, 12 unique tactics
- `MITRE_Technique`: 42.6% coverage, 134 unique techniques
- `MITRE_Sub_Technique`: 22.2% coverage, 223 unique sub-techniques
- `MITRE Software`: 23.7% coverage (out of scope for now)
- No URL field in API - construct ATT&CK URLs from technique IDs

### Chosen Approach: C (MITRE with Filtering)
- Add `include_mitre_techniques=False` to both tools (consistent with Data Server)
- Add `mitre_technique_filter` and `mitre_tactic_filter` to bulk listing
- Extract MITRE_Tactic, MITRE_Technique, MITRE_Sub_Technique from tags
- Construct ATT&CK URLs from IDs
- Auto-enable MITRE when filters are active

### Alternatives Considered
- **Approach A (Uniform Transform)**: Simple but no filtering - insufficient for Intuit use case
- **Approach B (Post-Pagination Enrichment)**: Optimized but two code paths for MITRE
