# SAF-28543: MCP cache logging is too verbose and spamming

## Status
Phase 6: PRD Created

## JIRA Ticket Summary

| Field       | Value              |
|-------------|--------------------|
| Status      | To Do              |
| Assignee    | Yossi Attas        |
| Reporter    | Yossi Attas        |
| Priority    | Low                |
| Type        | Bug                |
| Created     | Feb 23, 2026       |
| Sprint      | Saf sprint 83      |

**Problem**: Cache monitoring logs ~13 INFO lines every 5 minutes per server process, filling Docker log buffers and
drowning out meaningful logs. Proposed fix: single summary line at INFO, per-cache details at DEBUG, warnings preserved.

## Investigation Findings

### Core Implementation: `safebreach_mcp_core/safebreach_cache.py`

**Registry system (lines 18-19, 45)**:
- Global `_cache_registry` list tracks all `SafeBreachCache` instances
- Each cache auto-registers in `__init__`
- `get_all_cache_stats()` (lines 122-124) returns stats for all registered caches

**Current `log_cache_stats()` (lines 127-138)**:
- Iterates ALL registered caches, logs each at INFO level
- WARNING for caches at capacity (3+ consecutive checks) — this is appropriate and should stay

**`start_cache_monitoring()` (lines 141-148)**:
- Runs every 300 seconds (5 min) as asyncio background task
- Called from `safebreach_base.py:172` in `run_server()`

### Cache Instances Across All Servers (13 total)

| Server | Cache Name | maxsize | TTL |
|--------|-----------|---------|-----|
| Config | simulators | 5 | 3600s |
| Data | simulations | 3 | 600s |
| Data | security_control_events | 3 | 600s |
| Data | findings | 3 | 600s |
| Data | full_simulation_logs | 2 | 300s |
| Playbook | playbook_attacks | 5 | 1800s |
| Studio | studio_drafts | 5 | 1800s |
| All (5x) | {server_name}_base | 10 | 3600s |

**Note**: Each server process sees only its own caches (separate processes), not all 13.
The `_cache_registry` is per-process. So the actual volume is per-server, not global.

### Callers
- Single caller: `safebreach_base.py:172` — `asyncio.create_task(start_cache_monitoring())`
- Each server process runs its own monitoring task independently

### Existing Tests: `safebreach_mcp_core/tests/test_safebreach_cache.py`

**Tests that need updating (lines 436-469)**:
- `test_log_cache_stats_produces_info_log()` — asserts INFO-level per-cache messages
- `test_capacity_warning_after_3_consecutive()` — WARNING tests, should remain
- `test_capacity_warning_resets_when_below_capacity()` — WARNING tests, should remain

### Logging Configuration
- Root level: INFO (`start_all_servers.py:25-29`)
- No mechanism to selectively suppress cache logs without changing root level
- Servers use `log_level="info"` in uvicorn config

### Files to Change

| File | Lines | Change |
|------|-------|--------|
| `safebreach_mcp_core/safebreach_cache.py` | 127-138 | Rewrite `log_cache_stats()` |
| `safebreach_mcp_core/tests/test_safebreach_cache.py` | 436-469 | Update tests for new format |
