# Simplify Cache Enablement — SAF-28525

## 1. Overview

| Field | Value |
|-------|-------|
| **Task Type** | Refactor |
| **Purpose** | Eliminate redundant master cache flag, simplifying configuration from 5 env vars to 4 |
| **Target Consumer** | Internal — DevOps deploying MCP servers, developers maintaining cache config |
| **Key Benefits** | Simpler configuration, less code to maintain, clearer per-server intent |
| **Originating Request** | [SAF-28525](https://safebreach.atlassian.net/browse/SAF-28525) |

## 1.5 Document Status

| Field | Value |
|-------|-------|
| **PRD Status** | Approved |
| **Last Updated** | 2026-02-22 |
| **Owner** | Yossi Attas |
| **Current Phase** | N/A |

## 2. Solution Description

### Chosen Solution

Remove the `SB_MCP_ENABLE_LOCAL_CACHING` master flag entirely (breaking change). Simplify `is_caching_enabled()`
to check only per-server flags (`SB_MCP_CACHE_{SERVER}`). When called without a server name, return `False`.
Keep per-server result caching with explicit `None` check for unset env vars.

### Alternatives Considered

| Option | Description | Why Not Chosen |
|--------|-------------|----------------|
| Deprecate with warnings | Keep master flag but log deprecation warnings | Adds complexity instead of reducing it |
| Server constants enum | Define known servers in a validated set | Over-engineering for 4 known servers |

### Decision Rationale

Per-server flags already take precedence over the master flag. The master flag only serves as a fallback for
unset per-server flags — a shortcut that adds code complexity without clear value. Removing it forces explicit
per-server opt-in, which is safer and clearer.

## 3. Core Feature Components

### Component A: Simplified `cache_config.py`

**Purpose**: Modify existing `safebreach_mcp_core/cache_config.py` to remove all master flag logic.

**Key Changes**:
- Remove `CACHE_ENV_VAR` constant (`"SB_MCP_ENABLE_LOCAL_CACHING"`)
- Remove `_caching_enabled` global variable
- Simplify `is_caching_enabled()` to only check per-server env vars via `_SERVER_ENV_PREFIX`
- When called with `server_name=None`, return `False` (no global toggle)
- Keep `_per_server_cache` dict for caching resolved per-server values
- Simplify `reset_cache_config()` to only clear `_per_server_cache`
- Update module docstring to document only 4 per-server flags

### Component B: Updated Tests

**Purpose**: Modify existing `safebreach_mcp_core/tests/test_cache_config.py` to reflect the simplified logic.

**Key Changes**:
- Remove `TestGlobalToggle` class (5 tests that test the master flag)
- Update `TestPerServerToggle` to remove references to `SB_MCP_ENABLE_LOCAL_CACHING`
- Update `TestEnvVarParsing` to test per-server parsing only
- Update `TestResetCacheConfig` to test per-server reset only
- Add test: `is_caching_enabled()` with no args returns `False`
- Add test: unknown server name returns `False` (no global fallback)

### Component C: Documentation Updates

**Purpose**: Update `CLAUDE.md` and `README.md` to remove all references to the master flag.

**Key Changes**:
- Remove `SB_MCP_ENABLE_LOCAL_CACHING` from env var documentation in CLAUDE.md
- Remove the "Global toggle" line and "Per-server overrides take precedence" note
- Update README.md references to cache configuration
- Keep documentation for the 4 per-server flags

## 6. Non-Functional Requirements

### Technical Constraints

- **Breaking Change**: Users currently setting `SB_MCP_ENABLE_LOCAL_CACHING=true` must switch to per-server flags
- **Backward Compatibility**: `is_caching_enabled()` (no args) will return `False` instead of checking the
  master flag — callers in `safebreach_base.py` already pass server names, so impact is minimal

## 7. Definition of Done

- [ ] `SB_MCP_ENABLE_LOCAL_CACHING` env var is no longer read or referenced in code
- [ ] `CACHE_ENV_VAR` constant and `_caching_enabled` global removed from `cache_config.py`
- [ ] `is_caching_enabled("config")` returns `True` only when `SB_MCP_CACHE_CONFIG=true`
- [ ] `is_caching_enabled()` (no args) returns `False`
- [ ] All 4 per-server flags work independently: CONFIG, DATA, PLAYBOOK, STUDIO
- [ ] Default behavior remains: caching disabled when env vars not set
- [ ] Unit tests updated; no test regressions across all 539 tests
- [ ] CLAUDE.md and README.md updated to remove master flag documentation

## 8. Testing Strategy

### Unit Testing

- **Scope**: `safebreach_mcp_core/cache_config.py` — all exported functions
- **Key Scenarios**:
  - Each per-server flag independently enables/disables caching
  - Unset per-server flag defaults to `False`
  - Unknown server name defaults to `False`
  - `is_caching_enabled()` with no args returns `False`
  - Truthy values (`true`, `1`, `yes`, `on`) and falsy values parsed correctly
  - `reset_cache_config()` clears per-server cached state
  - Whitespace trimming on env var values
- **Framework**: pytest
- **Coverage Target**: Maintain current coverage level

### Cross-Server Regression

- Run full test suite: `uv run pytest safebreach_mcp_config/tests/ safebreach_mcp_data/tests/
  safebreach_mcp_utilities/tests/ safebreach_mcp_playbook/tests/ safebreach_mcp_studio/tests/ -v -m "not e2e"`
- All 539 tests must pass with no regressions

## 9. Implementation Phases

| Phase | Status | Completed | Commit SHA | Notes |
|-------|--------|-----------|------------|-------|
| Phase 1: Simplify cache_config.py | :hourglass: Pending | - | - | |
| Phase 2: Update tests | :hourglass: Pending | - | - | |
| Phase 3: Update documentation | :hourglass: Pending | - | - | |

### Phase 1: Simplify `cache_config.py`

**Semantic Change**: Remove master flag logic from cache configuration module

**Deliverables**: Simplified `is_caching_enabled()` that only checks per-server env vars

**Implementation Details**:

1. **Update module docstring**: Remove the "Global toggle" section. Document only the 4 per-server flags
   (`SB_MCP_CACHE_CONFIG`, `SB_MCP_CACHE_DATA`, `SB_MCP_CACHE_PLAYBOOK`, `SB_MCP_CACHE_STUDIO`).

2. **Remove master flag artifacts**:
   - Delete the `CACHE_ENV_VAR` constant (line 25)
   - Delete the `_caching_enabled: bool | None = None` global (line 31)

3. **Simplify `is_caching_enabled(server_name)`**:
   - Remove the `global _caching_enabled` statement
   - Remove the entire global toggle resolution block (lines 57-73)
   - When `server_name is None`: return `False` immediately
   - When `server_name` is provided: check `_per_server_cache` dict first (cached result).
     If not cached, look up `SB_MCP_CACHE_{SERVER_NAME_UPPER}` via `os.environ.get()`.
     If the env var is set (not `None`), parse it with `_parse_bool_env()` and cache the result.
     If the env var is not set (`None`), cache and return `False`.
   - Log per-server enablement status on first lookup (INFO level)

4. **Simplify `reset_cache_config()`**:
   - Remove the `global _caching_enabled` statement and `_caching_enabled = None` line
   - Keep only `_per_server_cache.clear()`

**Changes**:

| File | Action | Description |
|------|--------|-------------|
| `safebreach_mcp_core/cache_config.py` | Modify | Remove master flag, simplify to per-server only |

**Test Plan**: Run existing tests (expect failures in Phase 1 — tests updated in Phase 2)

**Git Commit**: `refactor(core): remove master cache flag, simplify to per-server toggles (SAF-28525)`

---

### Phase 2: Update Tests

**Semantic Change**: Align test suite with simplified per-server-only cache configuration

**Deliverables**: Updated test file with no master flag references, new tests for simplified behavior

**Implementation Details**:

1. **Remove `TestGlobalToggle` class entirely** (lines 13-50, 5 tests):
   - `test_global_on_enables_all_servers` — no longer applicable
   - `test_global_off_disables_all_servers` — no longer applicable
   - `test_global_unset_disables_all_servers` — covered by per-server tests
   - `test_backward_compat_no_args` — behavior changed to always return `False`
   - `test_backward_compat_no_args_disabled` — behavior changed

2. **Update `TestPerServerToggle`** (lines 53-111):
   - Remove `SB_MCP_ENABLE_LOCAL_CACHING` from `setup_method` and `teardown_method`
   - `test_server_specific_on_with_global_off`: Remove global flag setup. Set only `SB_MCP_CACHE_DATA=true`,
     assert data is `True`, others are `False`
   - `test_server_specific_off_with_global_on`: Remove global flag. Set `SB_MCP_CACHE_PLAYBOOK=false`,
     assert playbook is `False`
   - `test_server_specific_takes_precedence`: Simplify — just test multiple servers with different values
   - `test_unknown_server_falls_back_to_global`: Change expectation — unknown server returns `False`
   - `test_unknown_server_global_off`: Merge with above or simplify
   - `test_multiple_servers_independently_controlled`: Remove global flag, keep independent assertions

3. **Update `TestEnvVarParsing`** (lines 114-159):
   - Remove all `SB_MCP_ENABLE_LOCAL_CACHING` references from setup/teardown
   - Convert `test_truthy_values_global` and `test_falsy_values_global` to test per-server values instead
   - Keep `test_truthy_values_per_server` and `test_falsy_values_per_server` with simplified setup
   - Keep `test_whitespace_trimmed` but use per-server flag instead of global

4. **Update `TestResetCacheConfig`** (lines 162-201):
   - Remove `SB_MCP_ENABLE_LOCAL_CACHING` from setup/teardown
   - `test_reset_clears_global_cache`: Replace with test that `reset` clears per-server cached values
   - `test_reset_clears_per_server_cache`: Simplify — remove global flag reference
   - `test_reset_allows_reeval_with_new_env`: Simplify — test per-server fallback to `False` after removing override

5. **Add new tests**:
   - `test_no_args_returns_false`: Assert `is_caching_enabled()` returns `False` regardless of env state
   - `test_unknown_server_returns_false`: Assert unknown server name returns `False` (no global fallback)

**Changes**:

| File | Action | Description |
|------|--------|-------------|
| `safebreach_mcp_core/tests/test_cache_config.py` | Modify | Remove global toggle tests, update per-server tests |

**Test Plan**: Run `uv run pytest safebreach_mcp_core/tests/test_cache_config.py -v` — all tests must pass.
Then run full suite to verify no regressions.

**Git Commit**: `test(core): update cache config tests for per-server-only toggles (SAF-28525)`

---

### Phase 3: Update Documentation

**Semantic Change**: Remove master flag references from project documentation

**Deliverables**: Updated CLAUDE.md and README.md with per-server-only cache documentation

**Implementation Details**:

1. **Update CLAUDE.md** (lines 254-260):
   - Remove `SB_MCP_ENABLE_LOCAL_CACHING=true|false — Global toggle (default: false)` line
   - Remove `Per-server overrides take precedence over the global toggle` line
   - Keep the 4 per-server env var lines
   - Update surrounding text to say "Per-server cache toggles" instead of "Cache Configuration Environment Variables"

2. **Update README.md**:
   - Search for all references to `SB_MCP_ENABLE_LOCAL_CACHING` and remove them
   - Update any cache configuration sections to list only per-server flags

**Changes**:

| File | Action | Description |
|------|--------|-------------|
| `CLAUDE.md` | Modify | Remove master flag from cache env var docs |
| `README.md` | Modify | Remove master flag references |

**Test Plan**: Grep for `SB_MCP_ENABLE_LOCAL_CACHING` across entire repo — should return zero matches.

**Git Commit**: `docs: remove master cache flag from documentation (SAF-28525)`

## 12. Executive Summary

- **Issue**: 5 env vars control MCP caching (1 redundant master + 4 per-server), creating unnecessary complexity
- **What Will Be Built**: Simplified cache config with only 4 per-server flags
- **Key Technical Decision**: Breaking change (immediate removal) over gradual deprecation
- **Business Value**: Simpler deployment configuration, less code to maintain, clearer per-server intent
