# SAF-28525: Simplify the enablement control for the MCP cache

**Status**: Phase 6: PRD Created

## Ticket Information

| Field | Value |
|-------|-------|
| ID | SAF-28525 |
| Title | Simplify the enablement control for the MCP cache by dropping the master flag |
| Status | To Do |
| Assignee | Yossi Attas |
| Type | Task |
| Priority | Medium |
| Created | Feb 22, 2026 |
| Sprint | Saf sprint 83 (active) |
| Time Estimate | 2h |

## Description

Currently there are 5 environment variables that control the enablement of the caching for the 4 MCP servers:
1. One environment variable per cache enabled MCP server
2. One master variable that controls all together

This creates redundant complexity. The task is to drop the master flag and keep just the four specific ones.

## Investigation Focus

- Current cache enablement logic across all servers (Config, Data, Utilities, Playbook, Studio)
- Environment variable configuration and defaults
- Testing implications for removing the master flag
- Documentation updates needed

## Investigation Findings

**Phase 4: Investigation Complete**

### Current Cache Configuration System

**Master Flag:**
- `SB_MCP_ENABLE_LOCAL_CACHING` - Global toggle controlling all servers (default: false)
- Location: `safebreach_mcp_core/cache_config.py` line 25

**Per-Server Flags (4):**
- `SB_MCP_CACHE_CONFIG` - Config server caching
- `SB_MCP_CACHE_DATA` - Data server caching
- `SB_MCP_CACHE_PLAYBOOK` - Playbook server caching
- `SB_MCP_CACHE_STUDIO` - Studio server caching

### Enable/Disable Logic
- Centralized in `is_caching_enabled(server_name)` function (lines 40-88 in cache_config.py)
- **Precedence rule**: Per-server flags override global flag if set
- Per-server flags always take precedence over global flag
- Default behavior: Caching disabled

### Usage Pattern Across Servers
- Config server: Lines 133, 168 in config_functions.py
- Data server: 8 cache check points in data_functions.py
- Playbook server: Lines 49, 84 in playbook_functions.py
- Studio server: Lines 699, 954, 1425 in studio_functions.py
- Base server: Lines 93-94 in safebreach_base.py

### Tests
- Comprehensive test file: `safebreach_mcp_core/tests/test_cache_config.py` (201 lines)
- Coverage includes:
  - Global toggle behavior
  - Per-server override behavior
  - Precedence testing
  - Environment variable parsing (truthy: true, 1, yes, on)
  - Configuration reset utility

### Documentation
- CLAUDE.md lines 254-260: Lists all 5 environment variables
- README.md: References `SB_MCP_ENABLE_LOCAL_CACHING` usage
- PRD documentation: SAF-28428 related caching specification

## Brainstorming Results

_To be filled during Phase 5_
