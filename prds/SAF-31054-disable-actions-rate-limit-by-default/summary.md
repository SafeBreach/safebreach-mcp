# SAF-31054 — Ticket Summary

## Proposed Title

[safebreach-mcp] Make the actions rate limiter disabled by default

## Problem Statement

The rate limiting mechanism introduced in SAF-29871 is **enabled by default**. Because rate limit
thresholds and windows are not yet configurable from within the SafeBreach platform (content-side
configuration is a separate future work item), enabling rate limiting by default is premature and
may unexpectedly block legitimate AI agent workflows. The limiter should be **opt-in** until
content-based configuration is available.

## Proposed Description

In SAF-29871 we introduced a per-caller sliding-window rate limiting mechanism for all non-readOnly
MCP tools. It is currently enabled by default.

We want to change the default to **disabled** (`SAFEBREACH_MCP_RATE_LIMIT_ENABLED=false`) so rate
limiting is opt-in until it can be configured via the SafeBreach platform content
(separate work item tracked by Tal).

**Operators who want rate limiting** can enable it explicitly:
```bash
export SAFEBREACH_MCP_RATE_LIMIT_ENABLED=true
```

## Implementation

### Files to Change

| File | Change |
|------|--------|
| `safebreach_mcp_core/rate_limiter.py` | Line 33: `"true"` → `"false"` in `os.environ.get()` default |
| `CLAUDE.md` | Update rate limiting env var doc: `default: true` → `default: false` |
| `safebreach_mcp_core/tests/test_rate_limiter.py` | Add `enable_rate_limiter` autouse fixture |

### Code Change Detail

**`safebreach_mcp_core/rate_limiter.py` (line 32–34):**
```python
# Before
_rate_limit_enabled: bool = os.environ.get(
    "SAFEBREACH_MCP_RATE_LIMIT_ENABLED", "true"
).strip().lower() in ("true", "1", "yes")

# After
_rate_limit_enabled: bool = os.environ.get(
    "SAFEBREACH_MCP_RATE_LIMIT_ENABLED", "false"
).strip().lower() in ("true", "1", "yes")
```

**`safebreach_mcp_core/tests/test_rate_limiter.py` — add fixture:**
```python
@pytest.fixture(autouse=True)
def enable_rate_limiter():
    """Enable rate limiting for unit tests (overrides the disabled-by-default config)."""
    with patch("safebreach_mcp_core.rate_limiter._rate_limit_enabled", True):
        yield
```

## Acceptance Criteria

- [ ] `SAFEBREACH_MCP_RATE_LIMIT_ENABLED` defaults to `false` (rate limiting disabled by default)
- [ ] Rate limiting can be explicitly enabled via `SAFEBREACH_MCP_RATE_LIMIT_ENABLED=true`
- [ ] All existing unit tests pass (with `enable_rate_limiter` autouse fixture)
- [ ] `CLAUDE.md` documents the new default as `false`
- [ ] No changes to the rate limiting logic or gate placement

## Out of Scope

- Changing rate limiting thresholds, windows, or gate placement (no logic changes)
- Content-based configuration (separate future work item)
- E2E test changes (tests use explicit env var overrides already)
