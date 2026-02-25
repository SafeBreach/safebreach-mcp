# SAF-28615: [safebreach-mcp] requirements.txt does not reference cachetools

## JIRA Ticket Details

| Field       | Value                                                                   |
|-------------|-------------------------------------------------------------------------|
| Ticket ID   | SAF-28615                                                               |
| Type        | Bug                                                                     |
| Status      | To Do                                                                   |
| Assignee    | Yossi Attas                                                             |
| Priority    | Medium                                                                  |
| Created     | Feb 25, 2026                                                            |
| Sprint      | SAF Sprint 83 (Active: Feb 17 - Mar 3, 2026)                           |

## Problem Statement

A caching implementation was recently introduced to the MCP servers using the `cachetools` library, but the dependency was not added to `requirements.txt`.

- **Environment affected**: Shared MCP hosting server
- **Current behavior**:
  - mcp-proxy runs successfully (likely has cachetools installed separately or via transitive dependency)
  - Standalone MCP server deployments fail with ImportError for cachetools
- **Root cause**: Missing dependency in requirements.txt
- **Required fix**: Add `cachetools==7.0.1` to requirements.txt

## Acceptance Criteria

- [ ] `cachetools==7.0.1` is added to requirements.txt
- [ ] No duplicate entries or conflicts with existing versions
- [ ] Standalone MCP server can be deployed and starts without ImportError
- [ ] Requirements are in alphabetical order (if maintained)

## Investigation Findings

### Current State
- **File checked**: `/Users/yossiattas/Public/safebreach-mcp/requirements.txt`
- **Current length**: 45 lines (no cachetools entry)
- **Alphabetical order**: Maintained (fastapi, h11, httpcore, httpx, httpx-sse, etc.)
- **Entry to add**: `cachetools==7.0.1` (should be inserted between `boto3` and `certifi`)

### Git Status
- **Current branch**: SAF-28615-requirements-missing-cachetools
- **Status**: Up to date with remote
- **Working tree**: Clean (no uncommitted changes)

### Recent Context
From previous work (SAF-28585 and related caching PRs):
- Caching was introduced via cachetools library
- Used in multiple servers: Config (8000), Data (8001), Playbook (8003), Studio (8004)
- Cachetools enables TTL-based caching with LRU eviction
- Current implementation uses SafeBreachCache wrapper around cachetools.TTLCache

## Status

**Current Phase**: Phase 3: PRD Context Created
**Next Phase**: Complete fix and verify

## Notes

This is a straightforward dependency addition. The fix is minimal and low-risk:
- Single line addition to requirements.txt
- Entry point: between botocore (line 5) and certifi (line 6) in alphabetical order
- No code changes needed
- Should be tested with: `uv sync && uv run -m safebreach_mcp_*.{*_server}` to verify standalone server startup
