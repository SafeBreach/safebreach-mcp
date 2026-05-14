# Disable Actions Rate Limiter by Default — SAF-31054

## 1. Overview

- **Task Type**: Configuration change
- **Purpose**: Make the per-caller rate limiting mechanism opt-in rather than on-by-default, until
  content-based configuration is available
- **Target Consumer**: Internal — MCP server operators and AI agent consumers
- **Key Benefits**:
  - Prevents unexpected blocking of legitimate AI agent workflows
  - Rate limiting remains available for operators who explicitly enable it
  - Prepares for future content-based configuration (separate work item)
- **Business Alignment**: Follow-up to SAF-29871 rate limiting feature; aligns with incremental
  rollout approach
- **Originating Request**: [SAF-31054](https://safebreach.atlassian.net/browse/SAF-31054)

---

## 1.5. Document Status

| Field | Value |
|-------|-------|
| **PRD Status** | Draft |
| **Last Updated** | 2026-05-14 15:50 |
| **Owner** | Yossi Attas |
| **Current Phase** | N/A |

---

## 2. Solution Description

### Chosen Solution: Flip Default to Disabled

Change the default value of `SAFEBREACH_MCP_RATE_LIMIT_ENABLED` from `"true"` to `"false"` in the
`os.environ.get()` call in `rate_limiter.py`. This is a single-character change that makes rate
limiting opt-in. All rate limiting logic, gate placement, and configuration env vars remain
unchanged.

### Alternatives Considered

**Approach A — Remove rate limiting entirely**:
- Pros: Simplest, no dead code paths
- Cons: Loses the safety guardrail; would need to re-implement when content config is ready

**Approach B — Feature flag with server-side content config**:
- Pros: Content-managed, no env var needed
- Cons: Out of scope for this ticket; requires separate design and implementation

### Decision Rationale

Flipping the default preserves the entire rate limiting infrastructure for future use while
removing the risk of unexpected blocking. Operators who want rate limiting today can enable it
via environment variable. When content-based configuration is ready, the default can be revisited.

---

## 3. Core Feature Components

### Component A: Rate Limiter Default Change (`safebreach_mcp_core/rate_limiter.py`)

**Purpose**: Modify the existing rate limiter configuration to default to disabled.

**Key Features**:
- Change `os.environ.get("SAFEBREACH_MCP_RATE_LIMIT_ENABLED", "true")` default arg to `"false"`
- All other rate limiter logic, data structures, and gate placements remain unchanged
- Explicit `SAFEBREACH_MCP_RATE_LIMIT_ENABLED=true` still enables rate limiting

### Component B: Documentation Update (`CLAUDE.md`)

**Purpose**: Update env var documentation to reflect the new default.

**Key Features**:
- Change `default: true` to `default: false` for `SAFEBREACH_MCP_RATE_LIMIT_ENABLED`
- All other rate limiting documentation remains accurate

### Component C: Test Fixture Update (`safebreach_mcp_core/tests/test_rate_limiter.py`)

**Purpose**: Ensure unit tests continue to exercise rate limiting logic with an explicit enable.

**Key Features**:
- Add `enable_rate_limiter` autouse fixture that patches `_rate_limit_enabled` to `True`
- Existing `TestConfiguration.test_disabled_*` tests still work (their `@patch(False)` overrides
  the fixture)
- No changes to test logic, assertions, or test coverage

---

## 6. Non-Functional Requirements

### Technical Constraints

- **Backward Compatibility**: Deployments that already set `SAFEBREACH_MCP_RATE_LIMIT_ENABLED=true`
  are unaffected. Deployments that relied on the default being `true` will now have rate limiting
  disabled — this is the intended behavior change.
- **No migration needed**: Pure configuration default change with no data migration or deployment
  coordination required.

---

## 7. Definition of Done

- [ ] `_rate_limit_enabled` defaults to `False` when `SAFEBREACH_MCP_RATE_LIMIT_ENABLED` is unset
- [ ] Setting `SAFEBREACH_MCP_RATE_LIMIT_ENABLED=true` explicitly enables rate limiting
- [ ] All unit tests in `test_rate_limiter.py` pass with the `enable_rate_limiter` autouse fixture
- [ ] All gate integration tests in `test_rate_limiting.py` pass (unaffected)
- [ ] Full cross-server test suite passes (`uv run pytest ... -m "not e2e"`)
- [ ] `CLAUDE.md` documents `default: false` for `SAFEBREACH_MCP_RATE_LIMIT_ENABLED`

---

## 8. Testing Strategy

### Unit Testing

**Scope**: `safebreach_mcp_core/tests/test_rate_limiter.py`

**Key Scenarios**:
- All existing tests pass under the `enable_rate_limiter` autouse fixture (no logic changes)
- `TestConfiguration.test_disabled_*` tests still verify disabled behavior via explicit `@patch`
- No new test scenarios needed — the change is purely a default value flip

**Framework**: pytest with unittest.mock

### Integration Testing

**Scope**: `safebreach_mcp_studio/tests/test_rate_limiting.py`

**Key Scenarios**:
- Gate integration tests are unaffected (they mock `rate_limiter` directly, not `_rate_limit_enabled`)
- No changes required

### Verification

- Run: `uv run pytest safebreach_mcp_core/tests/test_rate_limiter.py -v`
- Run: `uv run pytest safebreach_mcp_studio/tests/test_rate_limiting.py -v`
- Run full suite: `uv run pytest safebreach_mcp_config/tests/ safebreach_mcp_data/tests/
  safebreach_mcp_utilities/tests/ safebreach_mcp_playbook/tests/ safebreach_mcp_studio/tests/
  -v -m "not e2e"`

---

## 9. Implementation Phases

| Phase | Status | Completed | Commit SHA | Notes |
|-------|--------|-----------|------------|-------|
| Phase 1: Flip default + test fixture + docs | ⏳ Pending | - | - | Single phase — all 3 changes |

---

### Phase 1: Flip Default, Update Tests, Update Docs

**Semantic Change**: Change rate limiter default from enabled to disabled, update test fixtures
and documentation to match.

**Deliverables**: Rate limiting disabled by default; tests pass; documentation accurate.

**Implementation Details**:

1. **`safebreach_mcp_core/rate_limiter.py`** (line 33):
   Change the second argument of `os.environ.get("SAFEBREACH_MCP_RATE_LIMIT_ENABLED", ...)` from
   `"true"` to `"false"`. This makes `_rate_limit_enabled` evaluate to `False` when the env var
   is not set.

2. **`safebreach_mcp_core/tests/test_rate_limiter.py`**:
   Add a new `autouse` fixture named `enable_rate_limiter` that patches
   `safebreach_mcp_core.rate_limiter._rate_limit_enabled` to `True` using `unittest.mock.patch`
   as a context manager. Place it at module level alongside the existing `reset_rate_limiter`
   fixture. Tests in `TestConfiguration` that explicitly patch `_rate_limit_enabled` to `False`
   will override this fixture because `@patch` decorators apply inside the fixture's context.

3. **`CLAUDE.md`**:
   Find all occurrences of `SAFEBREACH_MCP_RATE_LIMIT_ENABLED` documentation that say
   `default: true` or `default: \`true\`` and change them to `default: false` or
   `default: \`false\``.

**Changes**:

| File | Action | Description |
|------|--------|-------------|
| `safebreach_mcp_core/rate_limiter.py` | Modify | `"true"` → `"false"` default arg |
| `safebreach_mcp_core/tests/test_rate_limiter.py` | Modify | Add `enable_rate_limiter` autouse fixture |
| `CLAUDE.md` | Modify | Update default to `false` in rate limiting docs |

**Git Commit**: `feat: disable actions rate limiter by default (SAF-31054)`

---

## 10. Risks and Assumptions

### Technical Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Deployments relying on default-enabled rate limiting lose protection | Low — rate limiting
was recently introduced in SAF-29871 and not yet content-configurable | Document the change;
operators who want rate limiting can set `SAFEBREACH_MCP_RATE_LIMIT_ENABLED=true` |

### Assumptions

- No production deployments currently depend on the default-enabled rate limiting behavior
  (the feature was just shipped in SAF-29871)
- Content-based configuration will be implemented separately, at which point the default may
  be revisited

---

## 11. Future Enhancements

- **Content-based rate limit configuration**: A separate work item (to be opened by Tal) will
  allow configuring rate limiting thresholds and enable/disable state from within the SafeBreach
  platform. Once available, the default may be flipped back to enabled.

---

## 12. Executive Summary

- **Issue/Feature Description**: The rate limiter introduced in SAF-29871 defaults to enabled,
  which is premature until content-based configuration is available.
- **What Will Be Built**: A one-line default change, test fixture update, and documentation update.
- **Key Technical Decisions**: Flip default rather than removing rate limiting entirely, preserving
  the infrastructure for future content-based configuration.
- **Scope**: 3 files changed; no logic modifications, no gate placement changes, no API changes.
- **Business Value**: Prevents unexpected blocking of legitimate AI agent workflows while retaining
  the rate limiting guardrail for explicit opt-in use.

---

## 14. Change Log

| Date | Change Description |
|------|-------------------|
| 2026-05-14 15:50 | PRD created — initial draft |
