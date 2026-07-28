# MCP: Comment Out Playbook Attack Tag Write Tools — SAF-34168

## Section 1: Overview

**Ticket**: SAF-34168 (Task) — parent epic SAF-29873 "MCP and BG Actions and Guardrails"
**Sprint**: Saf sprint 94
**Repo**: `safebreach-mcp`
**Branch**: `feature/SAF-34168-withdraw-tag-write-tools` (cut from `origin/main`)

### Driver

There is a **backend bug in how tags are treated for cloned moves**. As a result, the ability to
change tags is being **removed on the backend for now**.

The MCP playbook server exposes six tag *write* tools that call the backend move-tags endpoints.
Since the backend capability they depend on is going away, those tools must be withdrawn in step with
the backend change. This is **not** an MCP-side defect — the MCP implementation is being *parked*,
not fixed, so it can be restored once the cloned-move tag handling is corrected backend-side.

The two read-only tag tools are unaffected and stay exposed.

---

## Section 1.5: Document Status

| Field | Value |
|-------|-------|
| Status | Phases A–C implemented (uncommitted); Phase D (PR) pending |
| Last Updated | 2026-07-28 |
| Prior artifacts | `context.md`, `summary.md` in this folder (from `preparing-ticket`) |
| Investigation | Complete — reused from `context.md`, not re-run |
| Approach decision | Confirmed with the reporter: comment out registrations **+** imports **+** the two wrapper test classes |
| Code written | None — this document plans only |

---

## Section 2: Solution Description

Comment out (do **not** delete) three blocks, so that re-enablement after the backend fix is
"uncomment three blocks and revert one skip":

1. The **six write tool registrations** in `playbook_server.py`.
2. The **six write-function imports** in the module-level import block of `playbook_server.py`.
3. The **two wrapper test classes** that resolve those tools out of the MCP tool registry.

Plus one behavioural change:

4. An **explicit skip** on the live tag-write E2E class, because it exercises the endpoints the
   backend is removing.

`playbook_functions.py` is **not touched at all**. Every `sb_*` tag function, every helper, and every
unit test that calls those functions directly stays in place and keeps passing. That is what makes
this cheap to reverse.

### Why comment out rather than flag-gate

There is no feature flag or conditional-registration mechanism anywhere in
`SafeBreachPlaybookServer._register_tools()` (`playbook_server.py:44`) — all tools are registered
unconditionally. Introducing a gating mechanism would be new machinery for a temporary withdrawal, so
commenting out is the available and proportionate lever.

---

## Section 3: Affected Components

### 3.1 `safebreach_mcp_playbook/playbook_server.py`

**Registrations to comment out** (each is a complete `@self.mcp.tool(...)` decorator plus its wrapper
function):

| # | Tool | Lines | Annotation today |
|---|------|-------|------------------|
| 1 | `add_playbook_attack_tag` | 350-364 | `readOnlyHint=False, destructiveHint=False` |
| 2 | `remove_playbook_attack_tag` | 366-380 | `readOnlyHint=False, destructiveHint=True` |
| 3 | `rename_playbook_attack_tag` | 382-400 | `readOnlyHint=False, destructiveHint=False` |
| 4 | `bulk_add_playbook_attack_tags` | 421-437 | `readOnlyHint=False, destructiveHint=False` |
| 5 | `bulk_remove_playbook_attack_tags` | 439-454 | `readOnlyHint=False, destructiveHint=True` |
| 6 | `bulk_rename_playbook_attack_tag` | 456-478 | `readOnlyHint=False, destructiveHint=False` |

Note the ordering: `get_playbook_attack_tags` (402-419) sits **between** the single-attack writes and
the bulk writes. It must be left registered — the two commented regions are therefore
**non-contiguous** (350-400 and 421-478), which is the easiest thing to get wrong here.

**Imports to comment out** — inside the `from .playbook_functions import (...)` block at lines 17-28:

```
    sb_get_playbook_attacks,              # keep
    sb_get_playbook_attack_details,       # keep
    sb_get_playbook_attacks_by_tags,      # keep
    sb_add_playbook_attack_tag,           # comment out
    sb_remove_playbook_attack_tag,        # comment out
    sb_rename_playbook_attack_tag,        # comment out
    sb_get_playbook_attack_tags,          # keep
    sb_bulk_add_playbook_attack_tags,     # comment out
    sb_bulk_remove_playbook_attack_tags,  # comment out
    sb_bulk_rename_playbook_attack_tag    # comment out
```

Mind the trailing comma on the last surviving entry — `sb_bulk_rename_playbook_attack_tag` currently
has none, so whichever name ends the list must not leave a dangling comma before `)`.

`ToolAnnotations` (line 15) stays imported — the surviving read tools still use it.

### 3.2 `safebreach_mcp_playbook/tests/test_tag_write_tools.py` (311 lines)

- Comment out `TestWriteToolWrappers` — class at line **269**, runs to **end of file (311)**. Include
  its banner comment block at lines 266-268.
- Comment out the now-unused import at line **22**
  (`from safebreach_mcp_playbook.playbook_server import SafeBreachPlaybookServer`) — it is referenced
  only at line 271, inside the class being commented out.
- **Leave untouched**: `TestAddPlaybookAttackTag` (67), `TestRemovePlaybookAttackTag` (149),
  `TestRenamePlaybookAttackTag` (206). These call the `sb_*` functions directly and must keep passing.

**Removes 6 test cases**: `test_registered_and_write_annotations` (parametrized ×3),
`test_add_wrapper_delegates_and_markdown`, `test_rename_wrapper_delegates`, `test_wrapper_error_path`.

### 3.3 `safebreach_mcp_playbook/tests/test_bulk_tag_tools.py` (223 lines)

- Comment out `TestBulkWrappers` — class at line **193**, runs to **end of file (223)**. Include its
  banner comment block at lines 190-192.
- Comment out the now-unused import at line **22** (same symbol, referenced only at line 195).
- **Leave untouched**: `TestBulkAdd` (64), `TestBulkRemove` (141), `TestBulkRename` (164).

**Removes 5 test cases**: `test_registered_write_annotations` (parametrized ×3),
`test_add_wrapper_delegates`, `test_wrapper_error_path`.

### 3.4 `safebreach_mcp_playbook/tests/test_e2e.py` (867 lines)

`TestPlaybookTagWriteE2E` (class at line **751**) holds **9** live tests. Only some of them touch the
endpoints the backend is removing, so the skip is applied **per-test, not to the class**:

| Group | Tests | Hits withdrawn endpoints? | Action |
|-------|-------|---------------------------|--------|
| Mutating | `test_add_read_remove_tag_roundtrip_e2e`, `test_rename_tag_roundtrip_e2e`, `test_bulk_add_remove_roundtrip_e2e`, `test_bulk_rename_roundtrip_e2e` | **Yes** — write real tags | **Skip these 4** |
| Read-only | `test_get_tags_on_attack_e2e` | No — reads the cached attacks listing | **Leave** — covers `get_playbook_attack_tags`, a tool this ticket keeps |
| Validation | `test_bulk_attack_id_cap_enforced_e2e` (847), `test_bulk_tag_value_cap_enforced_e2e` (853), `test_add_empty_tag_rejected_e2e` (859), `test_rename_noop_rejected_e2e` (864) | No — each asserts a `ValueError` raised *before any API call* | **Leave** — still covers the parked `sb_*` input validation, unchanged by this ticket |

A blanket class-level skip would wrongly disable the read-only test for a tool being kept, plus four
validation tests whose own banner (line 845) reads "no live writes; always run". Hence per-test.

**Why the existing decorator is not the lever**: the class already carries `@skip_e2e` (749) and
`@pytest.mark.e2e` (750), but `skip_e2e` is **inert by default** — `SKIP_E2E_TESTS` is read at line 39
as `os.environ.get('SKIP_E2E_TESTS', 'false')`, so the default is *run*, not skip. (Its reason string,
"set SKIP_E2E_TESTS=false to enable", reads backwards relative to that default, and differs from
`safebreach_mcp_data/tests/test_drift_tools.py:3300`, which defaults to `"true"`. Out of scope — just
don't be misled.)

Apply `@pytest.mark.skip(reason=...)` to each of the 4 mutating tests. Per house rules the reason
string must **not** contain a ticket ID — ticket context belongs in the commit/PR, not in code.

**Note on redundancy**: the 4 mutating tests all consume the `writable_move_ids` fixture, which GETs
the tags endpoint and `pytest.skip()`s when no move has a writable `/content/v3` store. If the backend
*removes* the endpoints (404), that fixture would skip these 4 on its own and no code change would be
needed. If the backend *keeps* them and only rejects writes, the fixture still yields IDs and the tests
would fail. The explicit skip is correct under **either** outcome, which is why it is applied rather
than relying on the fixture (see Open Question 1).

### 3.5 Explicitly NOT touched

| File / area | Reason |
|-------------|--------|
| `playbook_functions.py` | All `sb_*` tag functions + helpers `_build_move_tags_request` (345), `_parse_bulk_tag_values` (554), `_bulk_tags_request` (571) stay. Parked for re-enable. |
| Rate limiter | Per-tool-name entries (`playbook_functions.py:382/388`, `424/430`, `472/478`, `631/637`, `652/660`, `681/688`) become unreachable but are harmless. |
| `CLAUDE.md` | Line 224 lists only `get_playbook_attacks` / `get_playbook_attack_details` — it never documented the tag tools, so nothing to update. |
| `playbook_types.py` | Tag transformation helpers serve the surviving read path. |

---

## Section 4: Backend Dependency

All six write tools funnel into two config-service endpoints:

| Scope | URL | Built by |
|-------|-----|----------|
| Single attack | `{config}/api/content/v3/accounts/{account_id}/moves/{attack_id}/tags` | `_build_move_tags_request` (`playbook_functions.py:345-354`) |
| Bulk | `{config}/api/content/v3/accounts/{account_id}/moves/tags` | `_bulk_tags_request` (`playbook_functions.py:571-577`) |

The two **read** tag tools never touch either endpoint, which is why they stay exposed:

- `sb_get_playbook_attack_tags` (`:490`) resolves tags from the cached playbook-attacks listing via
  `_get_all_attacks_from_cache_or_api`, then `_extract_custom_tag_values`.
- `sb_get_playbook_attacks_by_tags` (`:292`) filters that same cached listing.

---

## Section 5: Out of Scope

- Fixing the cloned-move tag bug (backend work, tracked separately).
- Introducing a feature flag or RBAC-gated registration mechanism.
- Deleting any `sb_*` function, helper, or direct-call unit test.
- Repairing the 25 pre-existing `test_e2e.py` credential failures.
- Reconciling the inconsistent `SKIP_E2E_TESTS` defaults across the repo.
- Updating `CLAUDE.md` (never documented these tools).

---

## Section 6: Definition of Done

- [x] All six write tool registrations commented out in `playbook_server.py`, across both
      non-contiguous regions.
- [x] The six write-function imports commented out in the `playbook_server.py` import block, with no
      dangling comma — verified by `python -c "import safebreach_mcp_playbook.playbook_server"`.
- [x] Advertised playbook tool list is exactly four tools: `get_playbook_attacks`,
      `get_playbook_attack_details`, `get_playbook_attacks_by_tags`, `get_playbook_attack_tags`.
      Verified by enumerating the registry — 4 tools, exactly these.
- [x] `TestWriteToolWrappers` and `TestBulkWrappers` commented out, along with the now-unused
      `SafeBreachPlaybookServer` import in each test file.
- [x] The 4 **mutating** tests in `TestPlaybookTagWriteE2E` carry `@pytest.mark.skip`, reason contains
      no ticket ID. *(Revised from a class-level skip — see 3.4. A blanket skip would have disabled the
      read-only test for a kept tool plus 4 validation tests that never call the backend.)*
- [x] `playbook_functions.py` shows **zero** diff — verified with `git diff --quiet`.
- [x] `pytest safebreach_mcp_playbook/ --ignore=safebreach_mcp_playbook/tests/test_e2e.py` reports
      **246 passed, 0 failed**. *(Revised from 236: the 247 baseline − 11 removed wrapper cases = 236,
      plus the 10 new `TestExposedTagTools` cases = 246.)*
- [x] Read-path tag tests in `test_tag_tools.py` still pass, including `test_tool_registered` and
      `test_tool_registered_read_only`.
- [x] Full repo unit suite (`-m "not e2e"` across all modules) passes: **1439 passed, 0 failed**.
- [x] Work is on `feature/SAF-34168-withdraw-tag-write-tools`, based on `origin/main`.
- [ ] PR description records: which blocks were commented (not deleted), that imports were commented
      alongside, and that the 4 mutating E2E tests were skipped. *(Phase D — pending)*

---

## Section 7: Testing Strategy

### 7.1 Baseline (measured on `origin/main`, this branch's base)

| Invocation | Result |
|------------|--------|
| `pytest safebreach_mcp_playbook/ --ignore=safebreach_mcp_playbook/tests/test_e2e.py` | **247 passed, 0 failed** |
| `pytest safebreach_mcp_playbook/` (full, incl. E2E) | 251 passed, 25 failed, 4 errors, 1 skipped |
| The three tag test files alone | 95 passed |

Every failure and error in the full run lives in `test_e2e.py` and is caused by missing live-console
credentials (`ValueError: Failed to fetch playbook attacks: Environment variable 'demo-...'`). These
are pre-existing on `main` and **must not** be treated as regressions.

### 7.2 Expected after the change

| Invocation | Expected | Actual |
|------------|----------|--------|
| Unit-only (E2E ignored) | **246 passed, 0 failed** | ✅ 246 passed |
| Full repo unit suite, `-m "not e2e"` | no failures | ✅ 1439 passed |
| `test_tag_tools.py` (read paths) | unchanged, all pass | ✅ |
| `test_playbook_server.py` | **gains** `TestExposedTagTools` (10 cases) — see below | ✅ |

246 = 247 baseline − 11 removed wrapper cases + 10 new `TestExposedTagTools` cases.

`test_playbook_server.py` previously asserted only that the server and `.mcp` exist, with a comment
claiming tool registration "can't easily be tested" — which the wrapper tests disproved. The new
`TestExposedTagTools` class replaces that gap with the real invariant, and is what makes this change
durable rather than a one-off edit:

- `test_tag_write_tool_not_registered` (parametrized ×6) — none of the withdrawn write tools is advertised.
- `test_expected_tool_registered` (parametrized ×4) — all four surviving tools, including **both** tag
  read tools, are still advertised. This is the guard against the non-contiguous-region hazard (Risk 1).

Deliberately **not** a strict set-equality assertion: equality would break the moment an unrelated
playbook tool is added, while presence+absence covers both real risks (over-deletion and partial
withdrawal) without that brittleness.

### 7.3 Verification steps

1. **Tool-list assertion** (the criterion that actually matters). Instantiate the server and confirm
   the registry holds exactly the four surviving names:
   ```python
   sorted(SafeBreachPlaybookServer().mcp._tool_manager._tools.keys())
   ```
   Must contain none of the six withdrawn names. This is the same registry accessor the deleted
   wrapper tests used, so it is known to work.
2. **Unit suite**: `pytest safebreach_mcp_playbook/ --ignore=safebreach_mcp_playbook/tests/test_e2e.py`
   → 236 passed, 0 failed.
3. **Collection check**: `pytest safebreach_mcp_playbook/tests/test_e2e.py --collect-only -q` to
   confirm the tag-write class is skipped rather than erroring at import.
4. **Import sanity**: `python -c "import safebreach_mcp_playbook.playbook_server"` — catches a
   malformed import block (dangling comma / orphaned parenthesis), the most likely mechanical slip.

### 7.4 No CI safety net

`.github/workflows/` contains only `release.yml` and `security-scan.yml` (TruffleHog). There is no
lint or unit-test workflow, and no ruff/flake8/pylint config in `pyproject.toml`. The suite must be
run locally; unused imports would not be caught automatically, which is part of why the imports are
being commented rather than left behind.

---

## Section 8: Implementation Phases

### Phase Status Tracking

| Phase | Name | Status | Completed | Commit | Notes |
|-------|------|--------|-----------|--------|-------|
| A | Server registrations + imports | ✅ Complete | 2026-07-28 | uncommitted | Registry verified at exactly 4 tools; import smoke check passes |
| B | Unit tests (wrapper classes) | ✅ Complete | 2026-07-28 | uncommitted | Both wrapper classes + the unused import in each file commented |
| C | E2E skip | ✅ Complete | 2026-07-28 | uncommitted | Narrowed during implementation to the 4 **mutating** tests (see 3.4) |
| D | PR | ⏳ Pending | — | — | Requires explicit approval to commit/push |

Status icons: ✅ Complete · 🔄 In Progress · ⏳ Pending · ❌ Blocked

> **Atomicity constraint**: Phases A and B **must land in the same change**. Phase A alone removes the
> six registrations while `TestWriteToolWrappers` / `TestBulkWrappers` still resolve those tools from
> the registry, leaving 11 knowingly-failing tests. Do not commit A without B.

### Phase A — Server registrations + imports
1. Comment out the six `@self.mcp.tool` blocks: 350-364, 366-380, 382-400, then 421-437, 439-454,
   456-478. Leave `get_playbook_attack_tags` (402-419) registered between the two regions.
2. Comment out the six write-function names in the `playbook_server.py:17-28` import block; fix comma
   placement on the last surviving name.
3. Run `python -c "import safebreach_mcp_playbook.playbook_server"`.
4. Assert the registry holds exactly four tools (Section 7.3 step 1).

### Phase B — Unit tests
1. Comment out `TestWriteToolWrappers` (`test_tag_write_tools.py` 266-311) and the unused
   `SafeBreachPlaybookServer` import at line 22.
2. Comment out `TestBulkWrappers` (`test_bulk_tag_tools.py` 190-223) and the unused import at line 22.
3. Run `pytest safebreach_mcp_playbook/ --ignore=safebreach_mcp_playbook/tests/test_e2e.py` → expect
   **236 passed**.

### Phase C — E2E skip
1. Add an unconditional `@pytest.mark.skip(...)` to `TestPlaybookTagWriteE2E` (line 751), above or
   below the existing `@skip_e2e` / `@pytest.mark.e2e` decorators. Reason string must carry no ticket ID.
2. Run `pytest safebreach_mcp_playbook/tests/test_e2e.py --collect-only -q` and confirm the class is
   collected-and-skipped, not erroring.

### Phase D — PR
1. Commit the three commented blocks plus the E2E skip.
2. PR description: the backend cloned-move tag bug as the driver, the parked-not-deleted intent, the
   import decision, the E2E skip, and the 247 → 236 count change.

---

## Section 9: Risks and Assumptions

| # | Risk | Mitigation |
|---|------|-----------|
| 1 | **Non-contiguous regions.** `get_playbook_attack_tags` (402-419) sits between the single and bulk write blocks; a careless range comment-out kills a read tool that must survive. | Section 7.3 step 1 asserts the exact four-tool list. |
| 2 | **Malformed import block.** Commenting names inside a parenthesised import easily leaves a dangling comma or orphaned paren. | Explicit `import` smoke check (Phase A step 3). |
| 3 | **Partial withdrawal.** Missing one of the six — easiest with the three bulk variants — leaves a tool advertised that will fail against the changed backend, while looking done. | All six enumerated by name in the DoD and the tool-list assertion. |
| 4 | **Import/patch coupling.** Commenting registrations alone fails the wrapper tests with `KeyError`; also commenting imports fails them with `AttributeError`. Doing one without the other yields a confusing red suite. | Resolved by decision: all three blocks go together, in Phases A and B of the same change. |
| 5 | **Ordering vs the backend change.** If MCP lands *after* the backend, the tools stay advertised while the backend rejects calls — agents get opaque failures. The reverse (tools gone, backend still working) is harmless. | Open question 3; prefer shipping at or before the backend change. |
| 6 | **Comment-out is not enforcement.** The parked `sb_*` functions remain importable and callable in-process. | Acceptable: the real block is backend-side. The MCP change stops clients calling something that no longer works. |
| 7 | **Dormant-code decay.** ~100 commented lines plus two commented test classes will drift from live code. | Re-enable trigger is the backend cloned-move fix landing. |
| 8 | **Read-tool assumption.** "Keep the read tools" rests on them reading the attacks listing rather than the write endpoints (Section 4). If the cloned-move bug also corrupts tag values *as read*, scope needs revisiting. | Open question 2. |

### Assumptions
- The backend change removes only tag *mutation*; tag *reads* via the attacks listing stay correct.
- The six `sb_*` functions are expected back, so parking beats deleting.
- No consumer (skill, prompt, saved workflow) hard-depends on the six tool names. Not verified outside
  this repo.

---

## Section 10: Open Questions

1. Is the backend removing the two move-tags endpoints entirely (404), or keeping them and rejecting
   writes? Determines how the parked `sb_*` functions fail if ever called.
2. Do the read-only tag tools stay correct under the cloned-move bug? They surface tags from the
   attacks listing, not the write endpoints.
3. Should this ship before, with, or after the backend change?

---

## Section 11: Executive Summary

A backend bug in cloned-move tag handling is causing tag mutation to be removed backend-side. Six MCP
playbook tag write tools depend on the two endpoints being withdrawn, so they are commented out — not
deleted — along with their module-level imports and the two test classes that assert their
registration. One live E2E class gets an unconditional skip. `playbook_functions.py` is untouched, so
re-enabling after the backend fix means uncommenting three blocks and reverting one skip.

Scope: **1 source file, 3 test files, 0 changes to business logic.** Advertised playbook tools drop
from 10 to 4. Unit suite goes 247 → 236 passed.

---

## Section 12: Change Log

| Date | Change |
|------|--------|
| 2026-07-28 | PRD created. Investigation reused from `context.md` (no re-run). Approach confirmed with reporter: comment out registrations + imports + both wrapper test classes. Discovered during planning that `skip_e2e` is inert by default (`SKIP_E2E_TESTS` defaults to `'false'` at `test_e2e.py:39`), so an explicit skip is required. |
| 2026-07-28 | Phases A–C implemented via TDD. Two revisions found during implementation: **(1)** `TestPlaybookTagWriteE2E` holds **9** tests, not the 5 first recorded, and only **4** of them mutate tags — the skip was narrowed from the class to those 4, since a blanket skip would have disabled the read-only test for `get_playbook_attack_tags` (a tool this ticket keeps) plus 4 validation tests that raise before any API call. **(2)** Expected unit count revised 236 → 246 to account for the 10 new `TestExposedTagTools` cases added as the TDD red step. |
