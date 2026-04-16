# Ticket Summary: SAF-29966

## Overview
**Mode**: Improving existing
**Project**: SAF
**Repository**: safebreach-mcp

---

## Current State
**Summary**: [safebreach-mcp] Create tools to allow listing of all available scenarios and drilling in into a specific one
**Issues Identified**: Ticket lacks API details, field mapping, filter specification, and readiness criteria

---

## Investigation Summary

### safebreach-mcp
- **API endpoints confirmed**: `GET /api/content-manager/vLatest/scenarios` (list) and
  `GET /api/content-manager/vLatest/scenarioCategories` (category metadata)
- **Auth**: `x-apitoken` header works (same as all other MCP servers)
- **Data volume**: 443 scenarios on pentest01 console — **pagination required** (PAGE_SIZE=10)
- **Categories**: 15 categories, referenced by integer ID in scenarios, need client-side join
- **Ready-to-run definition**: ALL steps must have both `targetFilter` AND `attackerFilter` with
  at least one key containing non-empty `values` (e.g., `os`, `role` criteria). Empty
  `simulators.values` arrays do NOT qualify. Currently 4 of 443 are ready.
- **OOB vs custom**: `createdBy` field — "SafeBreach" = OOB, anything else = custom
- **Server placement**: Config Server (port 8000) per user decision
- Relevant files: `config_types.py`, `config_functions.py`, `config_server.py`, tests/

### Scenario Data Structure
Top-level fields: `id` (UUID), `name`, `description`, `createdBy`, `recommended`, `categories`
(int[]), `tags` (str[] or null), `createdAt`, `updatedAt`, `steps` (step objects with
attacksFilter/targetFilter/attackerFilter/systemFilter), `order`, `actions`, `edges`, `phases`,
`minApiVer`, `maxApiVer`

---

## Problem Analysis

### Problem Description
The SafeBreach MCP platform lacks tools for AI agents to discover and inspect scenarios.
Scenarios are a core SafeBreach concept — pre-built or custom multi-step attack workflows
that chain multiple attacks. Without MCP tools, agents cannot list available scenarios,
filter by category/readiness/type, or inspect scenario details.

### Impact Assessment
- AI agents cannot assist users with scenario selection or management
- Users must use the web UI to browse scenarios, breaking the MCP-driven workflow
- Scenario readiness (ready-to-run vs needs-configuration) is not exposed to AI agents

### Risks & Edge Cases
- **Category join**: Scenarios reference categories by integer ID; categories endpoint must
  be fetched and joined client-side for human-readable names
- **Large payloads**: Full scenario details include step structures with nested filters;
  reduced view for list endpoint is essential
- **Ready-to-run logic**: Complex — requires checking all steps for non-empty targetFilter AND
  attackerFilter with real criteria values (not just empty simulators arrays)
- **Tag filtering**: 206 of 443 scenarios have tags; tags can be null, need null-safe handling

---

## Proposed Ticket Content

### Summary (Title)
[safebreach-mcp] Add scenario listing and detail tools to Config Server with filtering and pagination

### Description

**Background**
SafeBreach scenarios are multi-step attack workflows that chain attacks for comprehensive
security testing. AI agents need MCP tools to list, filter, and inspect scenarios.

**Technical Context**
* Two API endpoints: `GET /api/content-manager/vLatest/scenarios` (all scenarios) and
  `GET /api/content-manager/vLatest/scenarioCategories` (category metadata)
* Authentication via `x-apitoken` header (same as all MCP servers)
* Config Server (port 8000) hosts the new tools
* 443 scenarios on pentest01 — pagination required (PAGE_SIZE=10)
* Categories referenced by integer ID; need client-side join with categories endpoint

**Problem Description**
* No MCP tools exist for scenario discovery or inspection
* Agents cannot filter by OOB/custom, category, readiness, or search by name/tag
* "Ready to run" requires checking all steps have both targetFilter AND attackerFilter
  with non-empty criteria values (os, role, etc.)

**Affected Areas**
* `safebreach_mcp_config/config_types.py` — Scenario transform functions (reduced/full mapping)
* `safebreach_mcp_config/config_functions.py` — API calls, caching, filtering, pagination logic
* `safebreach_mcp_config/config_server.py` — Two new MCP tool registrations
* `safebreach_mcp_config/tests/` — Unit tests for types, functions, and server
* `CLAUDE.md` — Tool documentation update

### Acceptance Criteria

- [ ] `get_scenarios` tool returns paginated scenario list (PAGE_SIZE=10, 0-based pages)
- [ ] Each scenario in list includes: id, name, description (truncated), createdBy,
  category names (resolved from categories endpoint), step_count, recommended, tags,
  is_ready_to_run, createdAt, updatedAt
- [ ] Supports `name_filter` (case-insensitive partial match)
- [ ] Supports `creator_filter` ("safebreach" for OOB, "custom" for user-created)
- [ ] Supports `category_filter` (case-insensitive partial match on category name)
- [ ] Supports `recommended_filter` (boolean)
- [ ] Supports `tag_filter` (case-insensitive partial match on tags)
- [ ] Supports `ready_to_run_filter` (boolean — all steps have both targetFilter AND
  attackerFilter with at least one key containing non-empty values)
- [ ] Supports ordering by name, step_count, created_at, updated_at (asc/desc)
- [ ] Returns `hint_to_agent` for pagination navigation
- [ ] Returns `applied_filters` metadata
- [ ] `get_scenario_details` tool returns full scenario payload by UUID
- [ ] Scenario details include full step definitions with attack filters
- [ ] Categories cached separately with appropriate TTL (shared cache)
- [ ] Scenarios cached with `SB_MCP_CACHE_CONFIG` env var control
- [ ] Unit tests cover: transform functions, API call mocking, filtering logic,
  pagination, ready-to-run computation, category join, error handling
- [ ] Single-tenant mode auto-resolve works for both new tools

### Suggested Labels/Components
- Component: safebreach_mcp_config
- Labels: mcp, scenarios, enhancement

---

## Proposed Ticket Content

<!-- Markdown format for JIRA Cloud -->

**Description (Markdown for JIRA):**
```markdown
### Background
SafeBreach scenarios are multi-step attack workflows that chain attacks for comprehensive
security testing. AI agents need MCP tools to list, filter, and inspect scenarios.

### Technical Context
* Two API endpoints: `GET /api/content-manager/vLatest/scenarios` and
  `GET /api/content-manager/vLatest/scenarioCategories`
* Authentication via `x-apitoken` header
* Config Server (port 8000) hosts the new tools
* 443+ scenarios — pagination required (PAGE_SIZE=10)
* Categories referenced by integer ID; need client-side join

### Problem Description
* No MCP tools exist for scenario discovery or inspection
* Agents cannot filter scenarios by OOB/custom, category, readiness, name, or tags
* "Ready to run" = all steps have both targetFilter AND attackerFilter with non-empty
  criteria values (os, role, etc.)

### Affected Areas
* `safebreach_mcp_config/` — types, functions, server, tests
* `CLAUDE.md` — documentation update
```

**Acceptance Criteria:**
```markdown
* `get_scenarios` tool with pagination (PAGE_SIZE=10), filtering (name, creator,
  category, recommended, tag, ready_to_run), and ordering
* Each scenario includes: id, name, description, createdBy, category names, step_count,
  recommended, tags, is_ready_to_run, createdAt, updatedAt
* `get_scenario_details` tool returns full scenario payload by UUID
* Caching via SB_MCP_CACHE_CONFIG env var with SafeBreachCache
* Unit tests for transforms, filtering, pagination, ready-to-run logic, category join
* Single-tenant mode auto-resolve for both tools
```
