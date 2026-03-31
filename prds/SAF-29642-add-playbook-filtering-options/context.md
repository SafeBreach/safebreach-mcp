# Ticket Context: SAF-29642

## Status
Phase 4: Investigation Complete

## Mode
Improving

## Original Ticket
- **Summary**: [safebreach-mcp] Allow filtering the playbook attacks by the attacker platform and target platform attributes of the attacks
- **Description**: Currently the playbook MCP tool for fetching attacks supports filtering by various options like name filter, description filter, id ranges, published date etc. We want to add the ability to filter the attacks by two additional attributes: attacker platform, target platform. The optional values for attacker platform and target platform should be automatically researched from the live console pentest01.
- **Acceptance Criteria**: None defined yet
- **Status**: To Do

## Task Scope
Full ticket preparation - investigate the playbook server codebase to understand current filtering, the attack data model (attacker/target platform fields), and how to add new platform-based filtering options.

## Repositories Under Investigation
- /Users/yossiattas/Public/safebreach-mcp

## Investigation Findings

### Playbook Server Architecture
- **playbook_types.py**: Data transformations, filtering logic, pagination
- **playbook_functions.py**: Business logic, cache management, API calls
- **playbook_server.py**: MCP tool definitions and response formatting

### Current Filtering Capabilities
The `get_playbook_attacks` tool supports:
- `name_filter` — case-insensitive partial match on attack name
- `description_filter` — case-insensitive partial match on description
- `id_min` / `id_max` — integer ID range (inclusive)
- `modified_date_start` / `modified_date_end` — ISO date range
- `published_date_start` / `published_date_end` — ISO date range
- `mitre_technique_filter` — comma-separated technique IDs/names (OR logic)
- `mitre_tactic_filter` — comma-separated tactic names/IDs (OR logic)

### Data Flow
1. `_get_all_attacks_from_cache_or_api()` fetches from `/api/kb/vLatest/moves?details=true`
2. `transform_reduced_playbook_attack()` extracts: name, id, description, modifiedDate, publishedDate (+ MITRE if requested)
3. `filter_attacks_by_criteria()` applies all active filters
4. `paginate_attacks()` handles 10-per-page pagination

### MITRE Filtering (Reference Pattern)
Recently added via SAF-28305. Pattern:
- Fields extracted from `tags` array in raw API data via `_extract_mitre_data()`
- Filter uses comma-separated OR logic with `_attack_matches_mitre_technique()` helper
- Auto-enables MITRE data extraction when MITRE filters are active
- Applied filters tracked in response metadata

### Critical Unknown: Platform Field Names
The raw API response from `/api/kb/vLatest/moves?details=true` has NOT been documented in the codebase for platform-related fields. Test mocks don't include platform data. The ticket explicitly requires discovering the field names and valid values from the live pentest01 console.

Likely field locations (to be confirmed):
- Top-level: `attack['attackerPlatform']`, `attack['targetPlatform']`
- Content nested: `attack['content']['attackerPlatform']`
- Tags-based: similar to MITRE data in the `tags` array

### Test Infrastructure
- **test_playbook_functions.py**: Unit tests with mock data, organized by feature (TestGetPlaybookAttacks, TestMitreGetPlaybookAttacks)
- **test_playbook_types.py**: Transform function tests
- **test_integration.py**: Cross-component integration tests
- **test_e2e.py**: E2E tests against real consoles (requires environment setup)
- Pattern: each filter has dedicated test verifying results + `applied_filters` tracking

### Files to Modify
1. `safebreach_mcp_playbook/playbook_types.py` — add platform extraction + filter logic
2. `safebreach_mcp_playbook/playbook_functions.py` — add parameters, validation, filter pass-through
3. `safebreach_mcp_playbook/playbook_server.py` — add tool parameters + response rendering
4. `safebreach_mcp_playbook/tests/test_playbook_functions.py` — add filter tests
5. `safebreach_mcp_playbook/tests/test_playbook_types.py` — add transform tests
6. `safebreach_mcp_playbook/tests/test_integration.py` — add integration tests
7. `safebreach_mcp_playbook/tests/test_e2e.py` — add E2E platform filter tests

## Problem Analysis

### Problem Scope
Add `attacker_platform` and `target_platform` filtering to `get_playbook_attacks` MCP tool.

### Platform Data Location
- Field: `content.nodes.{node_name}.constraints.os`
- No top-level platform field — must be derived from node structure
- Node-to-role mapping uses `isSource` (attacker) / `isDestination` (target) flags
- Valid OS values: AWS, AZURE, GCP, LINUX, MAC, WEBAPPLICATION, WINDOWS

### Node Patterns
| Pattern | Count | Attacker | Target |
|---------|-------|----------|--------|
| gold (host) | 2985 | N/A | gold |
| green/red (network) | 6446 | isSource=True | isDestination=True |
| attacker/target | 21 | attacker | target |
| target only | 138 | N/A | target |
| local only | 43 | N/A | local |

### Coverage
- Overall: 32.3% (3,125 / 9,683)
- Host (gold): 93.8% (2,801 / 2,985)
- Network (green/red): 3.7% (237 / 6,446)

### Risks
- Low OS coverage on network attacks
- Green/Red roles not fixed — must use isSource/isDestination
- Case variations in node names (Green/Red vs green/red)

## Proposed Improvements
See summary.md for complete proposed ticket content.
