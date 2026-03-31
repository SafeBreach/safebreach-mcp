# Ticket Context: SAF-29642

## Status
Phase 6: PRD Created

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

### RESOLVED: Platform Field Names (from pentest01 live API)
- **Field location**: `content.nodes.{node_name}.constraints.os`
- **No top-level platform field** — must be derived from node structure
- **Role mapping**: `isSource=True` = attacker, `isDestination=True` = target
- **Valid OS values**: AWS, AZURE, GCP, LINUX, MAC, WEBAPPLICATION, WINDOWS
- **Node patterns**: gold (2985), green/red (6446), attacker/target (21), target-only (138), local-only (43)
- **OS coverage**: 32.3% overall (93.8% host, 3.7% network)

### Implementation Pattern (from MITRE filtering reference)
The existing MITRE filtering provides the exact pattern to follow:
1. **Extract**: `_extract_platform_data(nodes)` → `{'attacker_platform': str|None, 'target_platform': str|None}`
2. **Transform**: Conditionally include in `transform_reduced_playbook_attack()` (always include, unlike MITRE)
3. **Filter**: Comma-separated OR logic via `_attack_matches_attacker_platform()` helper
4. **Auto-enable**: Not needed — platform data always extracted (simple string, not heavy like MITRE)
5. **Track**: Add to `applied_filters` metadata
6. **Render**: Add `**Attacker Platform:**` / `**Target Platform:**` lines in response

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

## Brainstorming Results

### Chosen Approach: Platform as First-Class Fields (Always Extracted)
- Always extract `attacker_platform` and `target_platform` in reduced transform — no conditional flag
- `_extract_platform_data(content)` traverses `content.nodes`, maps roles via `isSource`/`isDestination`
- Returns `{'attacker_platform': str|None, 'target_platform': str|None}`

### Design Decisions
| Decision | Choice | Rationale |
|----------|--------|-----------|
| Extraction | Always | Lightweight (2 strings), no include_platform flag needed |
| Matching | Case-insensitive partial match | Consistent with name_filter and MITRE filters |
| None handling | `None` for N/A | Clean, explicit "not applicable" for single-node attacks |
| No OS data + filter | Include in results | Avoids hiding 67.7% of attacks; documented in tool description |
| Response rendering | Always show | Platform data always visible in output |

### Alternatives Considered
- **Approach B (Conditional extraction)**: Add include_platform flag like MITRE. Rejected — unnecessary
  complexity for lightweight string data.

## Proposed Improvements
See summary.md for complete proposed ticket content.
