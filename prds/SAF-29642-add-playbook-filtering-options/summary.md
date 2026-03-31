# Ticket Summary: SAF-29642

## Overview
**Mode**: Improving existing
**Project**: SAF
**Repositories**: safebreach-mcp

---

## Current State
**Summary**: [safebreach-mcp] Allow filtering the playbook attacks by the attacker platform and target platform attributes of the attacks
**Issues Identified**: No acceptance criteria defined, no technical details about field locations or valid values

---

## Investigation Summary

### safebreach-mcp (Playbook Server)
- Platform data lives at `content.nodes.{node_name}.constraints.os` in raw API responses
- No top-level platform field exists — must be **derived** from node structure
- Node-to-role mapping: `isSource=True` = attacker, `isDestination=True` = target
- 7 valid OS values discovered from pentest01: `AWS`, `AZURE`, `GCP`, `LINUX`, `MAC`, `WEBAPPLICATION`, `WINDOWS`
- Overall OS coverage: 32.3% (3,125 / 9,683 attacks)
- Host attacks have 93.8% OS coverage; network attacks only 3.7%
- MITRE filtering (recently added) provides the closest implementation pattern
- Relevant files:
  - `safebreach_mcp_playbook/playbook_types.py` — data transforms, filtering logic
  - `safebreach_mcp_playbook/playbook_functions.py` — business logic, parameters
  - `safebreach_mcp_playbook/playbook_server.py` — MCP tool definitions

---

## Problem Analysis

### Problem Description
The `get_playbook_attacks` MCP tool supports filtering by name, description, ID range, dates, and MITRE ATT&CK data, but lacks platform-based filtering. Users need to filter attacks by the OS/platform of the attacker and target nodes to narrow results (e.g., "show me all attacks targeting Windows" or "find attacks requiring a Linux attacker").

Platform data is embedded in the attack's `content.nodes` structure, with varying node naming conventions (gold, green/red, attacker/target). The role mapping (attacker vs target) is determined by `isSource`/`isDestination` boolean flags, not by node names.

### Impact Assessment
- **User value**: Enables platform-specific attack discovery, critical for environment-specific security assessments
- **Implementation scope**: 3 source files + 4 test files, following established MITRE filtering pattern

### Risks & Edge Cases
- Network attacks have very low OS coverage (~3.7%) — platform filtering will primarily match host attacks
- Green/Red node roles are not fixed — must use `isSource`/`isDestination` flags
- Some attacks have OS on only one node (attacker OR target, not both)
- 2 attacks use case-variant node names (`Green`/`Red` vs `green`/`red`) — extraction must be case-insensitive
- Single-node attacks (gold, local, target-only) have no attacker platform

---

## Proposed Ticket Content

### Summary (Title)
[safebreach-mcp] Add attacker_platform and target_platform filtering to get_playbook_attacks

### Description

**Background**
The `get_playbook_attacks` playbook MCP tool needs two new filtering parameters — `attacker_platform_filter` and `target_platform_filter` — to allow users to narrow playbook attacks by the OS/platform of the attacker and target nodes.

**Technical Context**
* Platform data lives at `content.nodes.{node_name}.constraints.os` in the SafeBreach API response
* Node-to-role mapping uses `isSource` (attacker) and `isDestination` (target) boolean flags
* 5 node patterns exist: `gold` (host), `green`/`red` (network), `attacker`/`target`, `target`-only, `local`-only
* 7 valid OS values: AWS, AZURE, GCP, LINUX, MAC, WEBAPPLICATION, WINDOWS
* OS coverage: 32.3% overall (93.8% for host attacks, 3.7% for network attacks)
* pentest01 console has 9,683 total attacks

**Problem Description**
* Currently no way to filter playbook attacks by platform/OS constraints
* Platform data extraction requires traversing `content.nodes` structure and mapping nodes to attacker/target roles
* Implementation should follow the established MITRE filtering pattern (comma-separated, OR logic, case-insensitive)

**Affected Areas**
* `safebreach_mcp_playbook/`: playbook_types.py, playbook_functions.py, playbook_server.py
* `safebreach_mcp_playbook/tests/`: test_playbook_functions.py, test_playbook_types.py, test_integration.py, test_e2e.py

### Acceptance Criteria

- [ ] `get_playbook_attacks` accepts `attacker_platform_filter` parameter (comma-separated, OR logic, case-insensitive)
- [ ] `get_playbook_attacks` accepts `target_platform_filter` parameter (comma-separated, OR logic, case-insensitive)
- [ ] Platform data extracted from `content.nodes.{node}.constraints.os` with correct role mapping via `isSource`/`isDestination`
- [ ] Reduced attack format includes `attacker_platform` and `target_platform` fields (always present, None when not available)
- [ ] Platform filters work in combination with all existing filters
- [ ] Applied filters tracked in response metadata
- [ ] Platform values rendered in MCP tool response output
- [ ] Node name matching is case-insensitive (handles `Green`/`Red` vs `green`/`red`)
- [ ] Unit tests for platform extraction from all 5 node patterns
- [ ] Unit tests for platform filtering (single value, comma-separated, combined filters)
- [ ] Integration tests for platform filtering across multi-attack datasets
- [ ] E2E tests for platform filtering against live console
- [ ] CLAUDE.md updated with new filter documentation

### Suggested Labels/Components
- Component: playbook-server
- Labels: enhancement, filtering

---

## Proposed Ticket Content

<!-- Markdown format for JIRA Cloud -->

**Description (Markdown for JIRA):**
```markdown
### Background
The `get_playbook_attacks` playbook MCP tool needs two new filtering parameters — `attacker_platform_filter` and `target_platform_filter` — to allow users to narrow playbook attacks by the OS/platform of the attacker and target nodes.

### Technical Context
* Platform data lives at `content.nodes.{node_name}.constraints.os` in the SafeBreach API response
* Node-to-role mapping uses `isSource` (attacker) and `isDestination` (target) boolean flags
* 5 node patterns: `gold` (host), `green`/`red` (network), `attacker`/`target`, `target`-only, `local`-only
* 7 valid OS values: AWS, AZURE, GCP, LINUX, MAC, WEBAPPLICATION, WINDOWS
* OS coverage: 32.3% overall (93.8% host, 3.7% network) from pentest01 (9,683 attacks)

### Problem Description
* No platform-based filtering exists for playbook attacks
* Platform data extraction requires traversing `content.nodes` and mapping nodes to attacker/target roles via `isSource`/`isDestination` flags
* Implementation follows established MITRE filtering pattern (comma-separated, OR logic, case-insensitive)

### Affected Areas
* `safebreach_mcp_playbook/`: playbook_types.py, playbook_functions.py, playbook_server.py + 4 test files
```

**Acceptance Criteria:**
```markdown
* `get_playbook_attacks` accepts `attacker_platform_filter` (comma-separated, OR logic, case-insensitive)
* `get_playbook_attacks` accepts `target_platform_filter` (comma-separated, OR logic, case-insensitive)
* Platform extracted from `content.nodes.{node}.constraints.os` with role mapping via `isSource`/`isDestination`
* Reduced format includes `attacker_platform` and `target_platform` fields (always present, None when N/A)
* Platform filters combine with all existing filters
* Applied filters tracked in response metadata
* Platform values rendered in MCP tool response
* Node name matching case-insensitive
* Unit tests for extraction from all 5 node patterns + filtering
* Integration and E2E tests for platform filtering
* CLAUDE.md updated
```
