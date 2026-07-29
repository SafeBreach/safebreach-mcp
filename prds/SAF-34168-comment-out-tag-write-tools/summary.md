# Ticket Summary: SAF-34168

## Overview
**Mode**: Improving existing
**Project**: SAF
**Repositories**: `safebreach-mcp`

---

## Current State
**Summary**: MCP: Comment out playbook attack tag write tools (add / remove / rename, incl. bulk)

**Issues Identified in the ticket as created**:
- It states *what* to comment out but not *why*. The driver, supplied by the reporter, is a
  **backend bug in how tags are treated for cloned moves**; the ability to change tags is being
  **removed on the backend for now**. The MCP write tools call those backend endpoints, so they are
  withdrawn in step with the backend change. This is not an MCP-side defect.
- It does not identify the 11 test cases that fail as a direct result, nor which tests are safe.

- It does not flag the import/patch coupling in `playbook_server.py:17-28`, which is the one detail
  most likely to cause a confusing red suite mid-implementation.
- It does not name the base branch, even though the obvious candidate (the local
  `feature/SAF-29870-...` branch) is the wrong one.

---

## Investigation Summary

### safebreach-mcp
- The playbook server registers **10 tools unconditionally** in
  `SafeBreachPlaybookServer._register_tools()` (`safebreach_mcp_playbook/playbook_server.py:44`).
  No `if` guard, env-var gate, or role check exists around any of them.
- The **six write tools** in scope: `add_playbook_attack_tag` (350-364),
  `remove_playbook_attack_tag` (366-380), `rename_playbook_attack_tag` (382-400),
  `bulk_add_playbook_attack_tags` (421-437), `bulk_remove_playbook_attack_tags` (439-454),
  `bulk_rename_playbook_attack_tag` (456-478).
- The **two read-only tag tools to keep**: `get_playbook_attacks_by_tags` (288-348) and
  `get_playbook_attack_tags` (402-419).
- **The backend endpoints being withdrawn.** All six write tools funnel into two config-service
  endpoints: single-attack writes to
  `{config}/api/content/v3/accounts/{account_id}/moves/{attack_id}/tags`
  (`_build_move_tags_request`, `playbook_functions.py:345-354`), and bulk writes to
  `{config}/api/content/v3/accounts/{account_id}/moves/tags`
  (`_bulk_tags_request`, `playbook_functions.py:571-577`). These are the calls that stop being
  supported.
- **The read tools are on a different path**, which is why they stay:
  `sb_get_playbook_attack_tags` (`:490`) resolves tags from the cached attacks listing via
  `_get_all_attacks_from_cache_or_api`, and `sb_get_playbook_attacks_by_tags` (`:292`) filters that
  same listing. Neither touches the two write endpoints.
- Implementations to preserve live in `playbook_functions.py`: `sb_add_playbook_attack_tag` (357),
  `sb_remove_playbook_attack_tag` (399), `sb_rename_playbook_attack_tag` (441),
  `sb_bulk_add_playbook_attack_tags` (620), `sb_bulk_remove_playbook_attack_tags` (641),
  `sb_bulk_rename_playbook_attack_tag` (664), plus helpers `_build_move_tags_request` (345),
  `_parse_bulk_tag_values` (554), `_bulk_tags_request` (571).
- **Import coupling**: `playbook_server.py:17-28` imports all six write functions at module level.
  The wrapper tests `patch` those module attributes, so commenting the imports breaks them with
  `AttributeError`, while commenting only the registrations breaks them with `KeyError`.
- **11 test cases fail** once registration is removed: `TestWriteToolWrappers` in
  `tests/test_tag_write_tools.py:269` (6 cases) and `TestBulkWrappers` in
  `tests/test_bulk_tag_tools.py:193` (5 cases). All other tag tests call `sb_*` directly and are
  unaffected; `test_playbook_server.py` asserts nothing about individual tool names.
- **No CI gate**: `.github/workflows/` has only `release.yml` and `security-scan.yml` (TruffleHog).
  No ruff/flake8/pylint config anywhere, so unused imports fail nothing and the suite must be run
  locally.
- **Measured baseline on `origin/main`** (this branch's base): unit tests
  (`pytest safebreach_mcp_playbook/ --ignore=.../test_e2e.py`) = **247 passed, 0 failed**. The full
  suite including E2E = 251 passed / 25 failed / 4 errors / 1 skipped, where **every** failure and
  error is in `test_e2e.py` and caused by missing live-console credentials. E2E must therefore be
  excluded from this ticket's gate.
- **Base branch**: SAF-29870 is already squash-merged to `main` as `ad38a43` (PR #76). `origin/main`
  registers all ten tools. The local `feature/SAF-29870-...` branch is 12 ahead / 3 behind and
  differs from `main` in the playbook module only in `tests/test_e2e.py`, where `main` has 201 lines
  the branch lacks (`TestPlaybookTagWriteE2E`, line 751). **Branch from `origin/main`.**
- **Docs**: `CLAUDE.md:224` never listed the tag tools — already stale, no change needed here.

**Relevant files**:
- `safebreach_mcp_playbook/playbook_server.py` (registrations + imports) — the only file that must change
- `safebreach_mcp_playbook/tests/test_tag_write_tools.py` (`TestWriteToolWrappers`)
- `safebreach_mcp_playbook/tests/test_bulk_tag_tools.py` (`TestBulkWrappers`)
- `safebreach_mcp_playbook/tests/test_e2e.py` (`TestPlaybookTagWriteE2E`, on `main`)
- `safebreach_mcp_playbook/playbook_functions.py` (unchanged — preserved)

---

## Problem Analysis

### Problem Description
There is a backend bug in how tags are treated for **cloned moves**. Because of it, the ability to
change tags is being **removed on the backend for now**.

The MCP playbook server's six tag write tools call the backend move-tags endpoints:

* single-attack writes → `{config}/api/content/v3/accounts/{account_id}/moves/{attack_id}/tags`
  (`_build_move_tags_request`, `playbook_functions.py:345-354`)
* bulk writes → `{config}/api/content/v3/accounts/{account_id}/moves/tags`
  (`_bulk_tags_request`, `playbook_functions.py:571-577`)

Since the capability those tools depend on is going away, the tools must be withdrawn in step with
the backend change — otherwise the MCP server keeps advertising six tools that will fail, or that
keep exercising the broken cloned-move tag path.

The two read-only tag tools do **not** touch either endpoint: `sb_get_playbook_attack_tags` (`:490`)
resolves tags from the cached attacks listing via `_get_all_attacks_from_cache_or_api`, and
`sb_get_playbook_attacks_by_tags` (`:292`) filters that same listing. They stay exposed.

The implementation is parked rather than deleted so it can be restored once the cloned-move tag
handling is fixed backend-side.

### Impact Assessment
- **MCP clients**: playbook server tool count drops 10 → 4. Calls to any of the six names fail as
  unknown tools.
- **`playbook_server.py`**: ~100 lines of registration commented out; import block at 17-28 decided
  jointly with the tests.
- **`playbook_functions.py`**: unchanged, keeping the revert cheap.
- **Tests**: 11 cases must be commented out / skipped in the same change.
- **Rate limiter / docs**: no changes required.

### Risks & Edge Cases
- **Import/patch coupling**: commenting registrations *and* imports fails the delegation tests
  differently (`AttributeError`) than commenting registrations alone (`KeyError`). Handle both together.
- **Wrong base branch**: branching off the local `feature/SAF-29870-...` branch loses `main`'s
  `TestPlaybookTagWriteE2E` coverage.
- **Comment-out only removes the tools from MCP discovery** — the parked `sb_*` functions stay
  importable and callable in-process. That is acceptable here because the actual block is
  backend-side: the endpoints themselves stop supporting tag mutation. The MCP change keeps clients
  from calling something that no longer works; it is not itself the enforcement point.
- **Dead-code decay**: ~100 dormant lines plus dormant tests will drift from the live code. The
  re-enable trigger is the backend cloned-move fix landing.
- **Live E2E writes**: `TestPlaybookTagWriteE2E` mutates tags on a real console through the preserved
  functions. Once the backend removes tag mutation it will fail regardless of this change, so it
  should be skip-marked here.
- **Partial withdrawal**: missing any one of the six (easy with the bulk variants) leaves a tool
  advertised that will fail against the changed backend, while looking complete — hence all six are
  enumerated in the criteria.
- **Timing/ordering with the backend**: if the MCP change ships well before or after the backend
  change, there is a window where either the tools are gone while the backend still works, or the
  tools remain while the backend rejects them. The latter is the harmful direction.

---

## Proposed Ticket Content

### Summary (Title)
MCP: Comment out playbook attack tag write tools (add/remove/rename + bulk) following backend removal
of tag mutation

### Description

**Background**

There is a **backend bug in how tags are treated for cloned moves**. As a result, the ability to
change tags is being **removed on the backend for now**.

The MCP playbook server exposes six tag *write* tools that call the backend move-tags endpoints.
Since the backend capability they depend on is going away, those tools must be withdrawn in step
with the backend change. This is not an MCP-side defect — the implementation is parked, not fixed,
and is preserved so it can be restored once the cloned-move tag handling is corrected backend-side.

The two read-only tag tools are unaffected and stay exposed.

**Technical Context**

* All tools are registered unconditionally in `SafeBreachPlaybookServer._register_tools()`
  (`safebreach_mcp_playbook/playbook_server.py:44`) — no flag or role check exists to toggle.
* Write tools to withdraw: `add_playbook_attack_tag` (350-364), `remove_playbook_attack_tag`
  (366-380), `rename_playbook_attack_tag` (382-400), `bulk_add_playbook_attack_tags` (421-437),
  `bulk_remove_playbook_attack_tags` (439-454), `bulk_rename_playbook_attack_tag` (456-478).
* Read-only tag tools that must keep working: `get_playbook_attacks_by_tags` (288-348),
  `get_playbook_attack_tags` (402-419).
* `playbook_functions.py` is unchanged: `sb_add_playbook_attack_tag` (357),
  `sb_remove_playbook_attack_tag` (399), `sb_rename_playbook_attack_tag` (441),
  `sb_bulk_*` (620 / 641 / 664) and helpers (345 / 554 / 571) all stay.
* `playbook_server.py:17-28` imports the six write functions at module level, and the wrapper tests
  `patch` those module attributes — so the import decision and the test decision must be made together.
* Rate limiting is per-tool-name (`playbook_functions.py:382/388`, `424/430`, `472/478`, `631/637`,
  `652/660`, `681/688`); those entries become unreachable but need no change.
* Base branch is `origin/main` — SAF-29870 is already squash-merged there (`ad38a43`, PR #76). The
  local `feature/SAF-29870-...` branch is stale and lacks `main`'s `TestPlaybookTagWriteE2E`.
* Repo has no lint or unit-test CI gate (`.github/workflows/` = `release.yml` +
  `security-scan.yml`), so the suite must be run locally.

**Problem Description**

* A backend bug in how tags are treated for **cloned moves** is being addressed by removing the
  ability to change tags on the backend for now.
* The MCP playbook server advertises six tag write tools that call the two backend move-tags
  endpoints, so they depend on a capability that is going away.
* Left in place, those tools either fail against the changed backend or keep exercising the broken
  cloned-move tag path.
* There is no feature flag or conditional-registration mechanism in the playbook server to switch
  them off, so commenting out the registrations is the available lever.
* The implementation must be parked rather than deleted, since it is expected back once the
  cloned-move tag handling is fixed backend-side.

**Affected Areas**

* `safebreach-mcp` — `safebreach_mcp_playbook/playbook_server.py` (registrations at 350-400 and
  421-478; imports at 17-28)
* `safebreach-mcp` — `safebreach_mcp_playbook/tests/test_tag_write_tools.py`
  (`TestWriteToolWrappers`, 6 cases)
* `safebreach-mcp` — `safebreach_mcp_playbook/tests/test_bulk_tag_tools.py` (`TestBulkWrappers`,
  5 cases)
* `safebreach-mcp` — `safebreach_mcp_playbook/tests/test_e2e.py` (`TestPlaybookTagWriteE2E`)
* `safebreach-mcp` — `safebreach_mcp_playbook/playbook_functions.py` (**unchanged**, preserved)

### Acceptance Criteria

- [ ] All six write tool registrations are commented out in `playbook_server.py`:
      `add_playbook_attack_tag`, `remove_playbook_attack_tag`, `rename_playbook_attack_tag`,
      `bulk_add_playbook_attack_tags`, `bulk_remove_playbook_attack_tags`,
      `bulk_rename_playbook_attack_tag`.
- [ ] The playbook server's advertised tool list contains exactly four tools:
      `get_playbook_attacks`, `get_playbook_attack_details`, `get_playbook_attacks_by_tags`,
      `get_playbook_attack_tags`.
- [ ] `get_playbook_attacks_by_tags` and `get_playbook_attack_tags` still work, verified by the
      existing read-path tests in `tests/test_tag_tools.py`.
- [ ] All `sb_*` tag functions and helpers in `playbook_functions.py` are left in place and untouched,
      so the change is a pure re-enable.
- [ ] The 11 registration-dependent test cases (`TestWriteToolWrappers`,
      `TestBulkWrappers`) are commented out or skip-marked in the same change, with the reason and
      this ticket referenced in the commit/PR — not in a code comment.
- [ ] The module-level imports of the six write functions are handled consistently with the test
      decision, and the resulting state is explicitly recorded in the PR description.
- [ ] `pytest safebreach_mcp_playbook/ --ignore=safebreach_mcp_playbook/tests/test_e2e.py` passes
      locally with no failures and no errors. Baseline on `origin/main` is **247 passed**; the
      expected end state is 247 minus however many of the 11 registration-dependent cases are
      removed outright (skip-marking keeps the count and reports them as skipped).
- [ ] `test_e2e.py` is **excluded** from the pass/fail gate: on `origin/main` it already reports
      25 failed / 4 errors / 1 skipped purely from missing live-console credentials. Do not treat
      those as regressions, and do not attempt to "fix" them under this ticket.
- [ ] Work is based on `origin/main`, not on `feature/SAF-29870-mcp-actions-ai-agent-tags`.
- [ ] `TestPlaybookTagWriteE2E` is skip-marked — it writes tags through the endpoints the backend is
      removing, so it will fail against a live console once the backend change lands regardless of
      the MCP change.

### Suggested Labels/Components
- Component: (none set on this project's tasks)
- Labels: `CTEM-dev` (matches SAF-29870, the story this withdraws from)

---

## Open Questions for the Reviewer

1. **Is the backend removing the two move-tags endpoints entirely (404), or keeping them and
   rejecting writes?** Determines how the parked `sb_*` functions fail if ever called, and how
   `TestPlaybookTagWriteE2E` should be marked.
2. **Do the read-only tag tools stay correct under the cloned-move bug?** They surface tags from the
   attacks listing rather than the write endpoints. Confirm the cloned-move handling does not also
   make *read* values wrong or misleading — if it does, the read tools need a caveat too, and this
   ticket's "keep the read tools" scope would need revisiting.
3. **Imports at `playbook_server.py:17-28`** — comment out alongside the registrations, or keep so
   the dormant tests can be re-enabled unchanged?
4. **Ordering relative to the backend change** — should this ship before, with, or after it? The
   harmful direction is the tools remaining live while the backend already rejects the calls.
