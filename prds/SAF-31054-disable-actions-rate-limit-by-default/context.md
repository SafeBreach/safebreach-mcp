# SAF-31054 — Context File

## Ticket Info

| Field    | Value                                                              |
|----------|--------------------------------------------------------------------|
| ID       | SAF-31054                                                          |
| Title    | [safebreach-mcp] make the actions rate limiter disabled by default |
| Status   | To Do                                                              |
| Assignee | Yossi Attas                                                        |
| Type     | Task                                                               |
| Created  | May 13, 2026                                                       |

**Branch**: `SAF-31054-disable-actions-rate-limit-by-default`

## Ticket Description (verbatim)

> In the scope of SAF-29871 we introduced a rate limiting mechanism for non readOnly actions and it is enabled by default.
> We want to have the rate limiter disabled by default until it would be possible to configure it using content (a separate work item to be opened by Tal).

## Status

Phase 5: Problem Analysis Complete

---

## Investigation Findings

### Repository: safebreach-mcp

**Rate limiter configuration** (`safebreach_mcp_core/rate_limiter.py` lines 32–34):

```python
_rate_limit_enabled: bool = os.environ.get(
    "SAFEBREACH_MCP_RATE_LIMIT_ENABLED", "true"
).strip().lower() in ("true", "1", "yes")
```

The default is `"true"`. The fix is to change `"true"` → `"false"` in the default argument to `os.environ.get()`.

**Environment variable surface** (`CLAUDE.md`):
```
- `SAFEBREACH_MCP_RATE_LIMIT_ENABLED` — enable/disable (default: `true`)
```
Must be updated to `default: false`.

**Test impact** (`safebreach_mcp_core/tests/test_rate_limiter.py`):
- `record_action()` has `if not _rate_limit_enabled: return` → with `False` default, no timestamps are stored.
- `check_limit()` also short-circuits with `if not _rate_limit_enabled: return`.
- Tests in `TestCheckLimitBasic`, `TestRecordAction`, `TestSlidingWindow`, `TestErrorMessage`,
  `TestMultipleCallers`, `TestPerToolNameLimit`, and `get_caller_identity` tests
  that call `record_action()` and then expect `check_limit()` to raise would all fail silently
  (no-op instead of working).
- Fix: add an `autouse` fixture `enable_rate_limiter` that patches `_rate_limit_enabled` to `True`.
  Tests in `TestConfiguration` that explicitly patch to `False` still work because the `@patch`
  decorator applies after the fixture.
- `safebreach_mcp_studio/tests/test_rate_limiting.py`: unaffected — mocks `rate_limiter` directly.

**No other files reference `SAFEBREACH_MCP_RATE_LIMIT_ENABLED` default**.

---

## Problem Analysis

### What is the problem?

The rate limiter was introduced as a safety guardrail (SAF-29871) and shipped **enabled by default**
(`SAFEBREACH_MCP_RATE_LIMIT_ENABLED=true`). However, the limit thresholds and window sizes are
currently hardcoded via environment variables and are not configurable from within the SafeBreach
platform (content-side). This means customers and operators cannot tune or disable the rate limiter
without accessing the server's environment. Until content-based configuration is available
(separate future work item), having rate limiting **on by default** is premature and may
unexpectedly block legitimate AI agent workflows.

### Affected areas

| Area | File | Change |
|------|------|--------|
| Core rate limiter config | `safebreach_mcp_core/rate_limiter.py` | `"true"` → `"false"` default |
| Documentation | `CLAUDE.md` | Update `default: true` → `default: false` |
| Unit tests | `safebreach_mcp_core/tests/test_rate_limiter.py` | Add `enable_rate_limiter` autouse fixture |

### Risks

- **No behavioral regression risk**: the mechanism itself is unchanged; only the opt-in direction flips.
- **Test risk**: tests that rely on `_rate_limit_enabled` being `True` by default will fail unless
  an autouse fixture explicitly enables it. Well-understood and easy to fix.
- **Documentation clarity**: after this change, rate limiting must be explicitly opt-in via
  `SAFEBREACH_MCP_RATE_LIMIT_ENABLED=true`. CLAUDE.md must reflect this.

### Edge cases

- Tests that patch `_rate_limit_enabled` to `False` (i.e., `TestConfiguration.test_disabled_*`)
  will continue to work correctly because `@patch` decorators apply after autouse fixtures.
- No E2E impact — E2E tests already set explicit env var overrides.
