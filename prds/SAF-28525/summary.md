# Ticket Summary: SAF-28525

## Overview
**Mode**: Improving existing
**Project**: SAF
**Repositories**: safebreach-mcp

---

## Current State
**Summary**: Simplify the enablement control for the MCP cache by dropping the master flag
**Issues Identified**: The current description is accurate but lacks technical detail on what changes are needed, affected files, and acceptance criteria.

---

## Investigation Summary

### safebreach-mcp
- **5 env vars** currently control caching: 1 master (`SB_MCP_ENABLE_LOCAL_CACHING`) + 4 per-server (`SB_MCP_CACHE_CONFIG/DATA/PLAYBOOK/STUDIO`)
- Master flag logic centralized in `safebreach_mcp_core/cache_config.py` (~100 lines)
- Per-server flags already take precedence over master flag
- 4 server function files call `is_caching_enabled(server_name)`: config_functions.py, data_functions.py, playbook_functions.py, studio_functions.py
- Base class `safebreach_base.py` has backward-compatible `is_caching_enabled()` calls (no server_name)
- Tests: `safebreach_mcp_core/tests/test_cache_config.py` (201 lines) covers global toggle, per-server overrides, env var parsing, reset utility
- Documentation: CLAUDE.md (lines 254-260), README.md reference the master flag

---

## Recommended Approach

Remove the master flag `SB_MCP_ENABLE_LOCAL_CACHING` entirely (breaking change). Simplify `is_caching_enabled()` to only check per-server flags (`SB_MCP_CACHE_{SERVER}`). When called without a server name, return `False` (disabled by default). Keep the per-server caching pattern with explicit `None` check for unset env vars.

### Key Decisions
- **Breaking change over deprecation**: Cleaner code, no migration period complexity. Users setting the master flag will need to switch to per-server flags.
- **Default disabled**: Maintain current safety-first approach where caching must be explicitly opted into per-server.

### Alternatives Considered
| Option | Description | Why Not Chosen |
|--------|-------------|----------------|
| Deprecate with warnings | Keep master flag but log warnings | Adds complexity instead of reducing it |
| Server constants enum | Define known servers in a set with validation | Over-engineering for 4 known servers |

---

## Proposed Ticket Content

### Summary (Title)
Simplify the enablement control for the MCP cache by dropping the master flag

### Description

**Background**
The MCP cache system uses 5 environment variables: 1 master flag (`SB_MCP_ENABLE_LOCAL_CACHING`) and 4 per-server flags (`SB_MCP_CACHE_CONFIG`, `SB_MCP_CACHE_DATA`, `SB_MCP_CACHE_PLAYBOOK`, `SB_MCP_CACHE_STUDIO`). The master flag adds redundant complexity since per-server flags already override it. Removing the master flag simplifies configuration to 4 clear, purpose-specific env vars.

**Technical Context**
- Master flag logic is in `safebreach_mcp_core/cache_config.py` (constant `CACHE_ENV_VAR`, global `_caching_enabled`, fallback logic in `is_caching_enabled()`)
- Per-server flags already take precedence over the master flag when set
- `safebreach_base.py` calls `is_caching_enabled()` without server_name (backward compat path)
- 4 server function files use `is_caching_enabled("server_name")` pattern

**Proposed Approach**
1. Remove `CACHE_ENV_VAR` constant and `_caching_enabled` global from `cache_config.py`
2. Simplify `is_caching_enabled()` to check only per-server env vars; return `False` when called without server_name
3. Update `reset_cache_config()` to only clear `_per_server_cache`
4. Update module docstring to reflect 4-flag-only system
5. Update tests in `test_cache_config.py` to remove global toggle tests, update per-server tests
6. Update CLAUDE.md and README.md to remove `SB_MCP_ENABLE_LOCAL_CACHING` references

**Affected Areas**
- `safebreach_mcp_core/cache_config.py`: Main logic changes
- `safebreach_mcp_core/tests/test_cache_config.py`: Test updates
- `CLAUDE.md`: Documentation updates
- `README.md`: Documentation updates

### Acceptance Criteria

- [ ] `SB_MCP_ENABLE_LOCAL_CACHING` env var is no longer read or referenced in code
- [ ] `is_caching_enabled("config")` returns True only when `SB_MCP_CACHE_CONFIG=true`
- [ ] `is_caching_enabled()` (no args) returns False
- [ ] All 4 per-server flags work independently: CONFIG, DATA, PLAYBOOK, STUDIO
- [ ] Default behavior remains: caching disabled when env vars not set
- [ ] Existing unit tests updated; no test regressions across all servers
- [ ] CLAUDE.md and README.md updated to remove master flag documentation

---

## JIRA-Ready Content

<!-- Markdown format for JIRA Cloud -->

**Description (Markdown for JIRA):**
```markdown
### Background
The MCP cache system uses 5 environment variables: 1 master flag (`SB_MCP_ENABLE_LOCAL_CACHING`) and 4 per-server flags (`SB_MCP_CACHE_CONFIG`, `SB_MCP_CACHE_DATA`, `SB_MCP_CACHE_PLAYBOOK`, `SB_MCP_CACHE_STUDIO`). The master flag adds redundant complexity since per-server flags already override it. Removing the master flag simplifies configuration to 4 clear, purpose-specific env vars.

### Technical Context
* Master flag logic is in `safebreach_mcp_core/cache_config.py` (constant `CACHE_ENV_VAR`, global `_caching_enabled`, fallback logic)
* Per-server flags already take precedence over the master flag when set
* `safebreach_base.py` calls `is_caching_enabled()` without server_name (backward compat path)
* 4 server function files use `is_caching_enabled("server_name")` pattern

### Proposed Approach
1. Remove `CACHE_ENV_VAR` constant and `_caching_enabled` global from `cache_config.py`
2. Simplify `is_caching_enabled()` to check only per-server env vars; return `False` when called without server_name
3. Update `reset_cache_config()` to only clear `_per_server_cache`
4. Update module docstring, tests, CLAUDE.md, and README.md

### Affected Areas
* `safebreach_mcp_core/cache_config.py`: Main logic changes
* `safebreach_mcp_core/tests/test_cache_config.py`: Test updates
* `CLAUDE.md` and `README.md`: Documentation updates
```

**Acceptance Criteria:**
```markdown
* `SB_MCP_ENABLE_LOCAL_CACHING` env var is no longer read or referenced in code
* `is_caching_enabled("config")` returns True only when `SB_MCP_CACHE_CONFIG=true`
* `is_caching_enabled()` (no args) returns False
* All 4 per-server flags work independently: CONFIG, DATA, PLAYBOOK, STUDIO
* Default behavior remains: caching disabled when env vars not set
* Existing unit tests updated; no test regressions across all servers
* CLAUDE.md and README.md updated to remove master flag documentation
```
