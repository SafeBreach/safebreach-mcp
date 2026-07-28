# Ticket Context: SAF-34168

## Status
Phase 6: PRD Created — see `prd.md` in this folder

## Decisions Taken During Planning
- **Approach (confirmed with reporter)**: comment out the six tool registrations **and** the six
  write-function imports at `playbook_server.py:17-28` **and** the two wrapper test classes
  (`TestWriteToolWrappers`, `TestBulkWrappers`). Nothing deleted; re-enable = uncomment three blocks.
- **`TestPlaybookTagWriteE2E` needs an *unconditional* skip.** Discovered during planning that its
  existing `@skip_e2e` decorator is inert by default: `SKIP_E2E_TESTS` is read as
  `os.environ.get('SKIP_E2E_TESTS', 'false')` at `test_e2e.py:39`, so the default is *run*, not skip.
  (The decorator's reason string reads backwards relative to that default, and differs from
  `safebreach_mcp_data/tests/test_drift_tools.py:3300`, which defaults to `"true"`.)
- **Verified expected end state**: the two wrapper classes collect exactly 6 and 5 cases; deselecting
  both from the unit run yields **236 passed, 0 failed** (from the 247 baseline).

## Mode
Improving (ticket created 2026-07-28, then prepared)

## Original Ticket
- **Summary**: MCP: Comment out playbook attack tag write tools (add / remove / rename, incl. bulk)
- **Type**: Task
- **Status**: To Do
- **Parent Epic**: SAF-29873 — MCP and BG Actions and Guardrails
- **Sprint**: Saf sprint 94 (active)
- **Team / Offering**: Core / All
- **Assignee**: Dan Almog
- **Description (as created)**: Comment out the six tag write tool registrations in
  `safebreach_mcp_playbook/playbook_server.py`; keep the two read-only tag tools; do not delete the
  underlying `sb_*` implementations so the tools can be re-enabled later.

## Task Scope
Withdraw the playbook attack **tag write** surface from the SafeBreach MCP playbook server so that
only read-only tag tools remain exposed to clients, without deleting the implementation work
delivered under SAF-29870.

## Repositories Under Investigation
- `/Users/dan/dev/repos/safebreach-mcp` (single repo; owns all affected code)

---

## Investigation Findings

### Repository: safebreach-mcp

#### 1. Tool inventory — playbook server registers 10 tools, all unconditionally

All tools are registered inside `SafeBreachPlaybookServer._register_tools()`
(`safebreach_mcp_playbook/playbook_server.py:44`), called from `__init__`
(`playbook_server.py:35-42`). There is **no conditional registration** — no `if` guard, no
environment-variable gate, no role check around any tool.

Registered tool names in `origin/main`:

| Tool | Kind | server.py lines |
|------|------|-----------------|
| `get_playbook_attacks` | read | 47-167 |
| `get_playbook_attack_details` | read | 169-286 |
| `get_playbook_attacks_by_tags` | read (tag) | 288-348 |
| `add_playbook_attack_tag` | **write** | 350-364 |
| `remove_playbook_attack_tag` | **write** | 366-380 |
| `rename_playbook_attack_tag` | **write** | 382-400 |
| `get_playbook_attack_tags` | read (tag) | 402-419 |
| `bulk_add_playbook_attack_tags` | **write** | 421-437 |
| `bulk_remove_playbook_attack_tags` | **write** | 439-454 |
| `bulk_rename_playbook_attack_tag` | **write** | 456-478 |

The six **write** tools are exactly the ones in scope. The two read-only tag tools
(`get_playbook_attacks_by_tags`, `get_playbook_attack_tags`) stay.

#### 2. The backend endpoints the write tools depend on

All six write tools funnel into two config-service endpoints:

| Scope | URL | Built by |
|-------|-----|----------|
| Single attack | `{config}/api/content/v3/accounts/{account_id}/moves/{attack_id}/tags` | `_build_move_tags_request` (`playbook_functions.py:345-354`) |
| Bulk | `{config}/api/content/v3/accounts/{account_id}/moves/tags` | `_bulk_tags_request` (`playbook_functions.py:571-577`) |

These are the calls that stop being supported when the backend removes tag mutation, and they are
the reason the MCP tools have to be withdrawn in step.

The two **read** tag tools are on a different path, which is why they can stay exposed:
- `sb_get_playbook_attack_tags` (`playbook_functions.py:490`) resolves tags from the cached
  playbook-attacks listing via `_get_all_attacks_from_cache_or_api`, then
  `_extract_custom_tag_values` — no call to either write endpoint.
- `sb_get_playbook_attacks_by_tags` (`:292`) filters that same cached listing.

There is no feature flag or conditional-registration mechanism in the playbook server (see finding 1),
so commenting out the registrations is the available lever rather than a config toggle.

#### 3. Underlying implementations (to be preserved)

`safebreach_mcp_playbook/playbook_functions.py`:

| Function | Line | Note |
|----------|------|------|
| `sb_add_playbook_attack_tag` | 357 | write |
| `sb_remove_playbook_attack_tag` | 399 | write |
| `sb_rename_playbook_attack_tag` | 441 | write |
| `sb_get_playbook_attack_tags` | 490 | read — keep exposed |
| `sb_bulk_add_playbook_attack_tags` | 620 | write |
| `sb_bulk_remove_playbook_attack_tags` | 641 | write |
| `sb_bulk_rename_playbook_attack_tag` | 664 | write |
| `sb_get_playbook_attacks_by_tags` | 292 | read — keep exposed |
| `_build_move_tags_request` (helper) | 345 | shared by single-attack writes |
| `_parse_bulk_tag_values` (helper) | 554 | bulk only |
| `_bulk_tags_request` (helper) | 571 | bulk only |

Each write function calls `rate_limiter.check_limit(...)` / `record_action(...)` keyed on its own
tool name (`playbook_functions.py:382/388`, `424/430`, `472/478`, `631/637`, `652/660`, `681/688`).

#### 4. The import block is a hidden coupling

`playbook_server.py:17-28` imports all ten `sb_*` functions at module level, including the six
write functions. Two consequences:

- If the tool registrations are commented out but the imports are kept, the imports become unused.
  This is cosmetically dead but **harmless for CI** (see finding 6).
- If the imports are *also* commented out, the wrapper-delegation tests break in a second,
  different way: they patch the module attribute
  `safebreach_mcp_playbook.playbook_server.sb_add_playbook_attack_tag`
  (`test_tag_write_tools.py:284`, `:296`, `:305`; `test_bulk_tag_tools.py:208`, `:217`), which
  raises `AttributeError` if the name no longer exists on the module.

So the import decision and the test decision are coupled and must be made together.

#### 5. Tests affected

**Will fail** — these resolve the tool out of the registry via
`server.mcp._tool_manager._tools[name]`, which raises `KeyError` once registration is removed:

| File | Class | Tests |
|------|-------|-------|
| `tests/test_tag_write_tools.py` | `TestWriteToolWrappers` (line 269) | `test_registered_and_write_annotations` (parametrized ×3), `test_add_wrapper_delegates_and_markdown`, `test_rename_wrapper_delegates`, `test_wrapper_error_path` → **6 test cases** |
| `tests/test_bulk_tag_tools.py` | `TestBulkWrappers` (line 193) | `test_registered_write_annotations` (parametrized ×3), `test_add_wrapper_delegates`, `test_wrapper_error_path` → **5 test cases** |

**Unaffected** — these call the `sb_*` functions directly and keep passing as long as the functions
survive:
- `test_tag_write_tools.py`: `TestAddPlaybookAttackTag` (67), `TestRemovePlaybookAttackTag` (149),
  `TestRenamePlaybookAttackTag` (206)
- `test_bulk_tag_tools.py`: `TestBulkAdd` (64), `TestBulkRemove` (141), `TestBulkRename` (164)
- `test_tag_tools.py`: read-path tests, plus `test_tool_registered` (220) and
  `test_tool_registered_read_only` (295) — these cover the two **read** tag tools, which stay
- `test_playbook_server.py`: asserts only that the server object and `.mcp` exist; it explicitly
  does not assert on individual tool names (lines 12-33) → unaffected

**Live E2E** — `origin/main`'s `tests/test_e2e.py` contains `TestPlaybookTagWriteE2E` (line 751)
with `test_get_tags_on_attack_e2e`, `test_add_read_remove_tag_roundtrip_e2e`,
`test_rename_tag_roundtrip_e2e`, `test_bulk_tag_value_cap_enforced_e2e`,
`test_add_empty_tag_rejected_e2e`. These drive the `sb_*` functions against a live console rather
than the MCP tool registry, so they will keep passing — but they would be exercising a surface no
longer offered to clients. Needs an explicit decision (skip/mark vs. leave).

#### 6. Repo has no lint or unit-test CI gate

`.github/workflows/` contains only `release.yml` and `security-scan.yml` (TruffleHog secret scan).
There is no ruff/flake8/pylint configuration in `pyproject.toml` (sections present: `project`,
`optional-dependencies`, `scripts`, `tool.setuptools`, `tool.uv`, `tool.pytest.ini_options`) and no
`.flake8` / `ruff.toml`. Therefore unused imports will not fail anything automatically, and the
test suite must be run locally to catch the 11 failing cases.

**Measured baseline on `origin/main`** (the base of this ticket's branch):

| Invocation | Result |
|------------|--------|
| `pytest safebreach_mcp_playbook/ --ignore=safebreach_mcp_playbook/tests/test_e2e.py` | **247 passed, 0 failed** |
| `pytest safebreach_mcp_playbook/` (full, incl. E2E) | 251 passed, 25 failed, 4 errors, 1 skipped |

Every one of the 25 failures and 4 errors is in `test_e2e.py` and is caused by missing live-console
credentials (`ValueError: Failed to fetch playbook attacks: Environment variable 'demo-...'`), not by
anything related to this ticket. **E2E must be excluded from this ticket's pass/fail gate**, and
those pre-existing failures must not be mistaken for regressions or "fixed" here.

#### 7. Branch / base state — SAF-29870 is already merged to `main`

- `origin/main` HEAD: `17c0b52`; `ad38a43` is **"SAF-29870: MCP AI-Agent tag actions (CRUD +
  retrieval + bulk) (#76)"** — squash-merged.
- `origin/main` already registers all ten tools including the six writes, and already contains
  `tests/test_tag_write_tools.py` and `tests/test_bulk_tag_tools.py`.
- The local branch `feature/SAF-29870-mcp-actions-ai-agent-tags` is **12 ahead / 3 behind**
  `origin/main`, but a direct tree diff shows the playbook module differs from `main` in
  `tests/test_e2e.py` only (`main` has 201 lines the branch lacks — the `TestPlaybookTagWriteE2E`
  class). The branch is effectively superseded by the squash merge.
- **Implication**: SAF-34168 must branch from `origin/main`, not from the SAF-29870 branch.
  Branching off the stale feature branch would silently drop `main`'s E2E tag-write tests.

#### 8. Documentation

`CLAUDE.md:224` documents the playbook server's tools as only `get_playbook_attacks` and
`get_playbook_attack_details`. It never listed the tag tools, so it is already stale and requires
no change for this ticket — though it is a pre-existing gap worth noting.

#### Working-tree note
The checkout currently has uncommitted `uv.lock` modifications and an untracked `.idea/` directory.
Unrelated to this ticket; must not be swept into its commits.

---

## Problem Analysis

### Problem Description
**Driver (from the reporter, not derivable from this repo):** there is a backend bug in how tags are
treated for **cloned moves**. To contain it, the ability to change tags is being **removed on the
backend for now**.

SAF-29870 delivered a tag-mutation surface on the MCP playbook server: six write tools (add / remove /
rename a custom tag on a playbook attack, plus three bulk variants). Those tools call the two
config-service move-tags endpoints documented in finding 2. Since the backend capability they depend
on is going away, the tools have to be withdrawn in step with the backend change — left in place they
either fail against the changed backend, or keep exercising the broken cloned-move tag path.

This is **not** an MCP-side defect. Nothing in the MCP implementation is being fixed; the surface is
being parked. That is why the ticket asks for comment-out rather than deletion: the six `sb_*`
functions, their helpers, and their direct unit tests stay in place so the tools can be restored once
the cloned-move tag handling is corrected backend-side.

The two read-only tag tools resolve tags from the cached attacks listing rather than the write
endpoints (finding 2), so they are unaffected and stay exposed.

### Impact Assessment
- **MCP clients**: the playbook server's advertised tool list drops from 10 to 4 tools. Any client,
  prompt, or skill that calls one of the six names starts failing with an unknown-tool error rather
  than a graceful message.
- **`playbook_server.py`**: six `@self.mcp.tool` blocks (~100 lines across lines 350-400 and
  421-478) commented out; the module-level import block at lines 17-28 must be decided on jointly
  with the tests.
- **`playbook_functions.py`**: unchanged. All seven `sb_*` tag functions and the three helpers
  remain, keeping the change cheap to revert.
- **Test suite**: 11 test cases across two files fail as written and need to be commented out,
  skipped, or deleted in step with the registrations.
- **Rate limiter**: the per-tool-name limits for the six tools become unreachable but harmless; no
  change required.
- **Docs**: no change required (`CLAUDE.md` never listed these tools).

### Risks & Edge Cases
- **Import/patch coupling** (highest-value detail): commenting out the registrations *and* the
  imports breaks the delegation tests differently (`AttributeError` on `patch`) than commenting out
  registrations alone (`KeyError` on the registry lookup). Deciding one without the other produces
  a confusing red suite.
- **Wrong base branch**: branching from the local `feature/SAF-29870-...` branch instead of
  `origin/main` would lose `main`'s `TestPlaybookTagWriteE2E` coverage and reintroduce a stale
  `test_e2e.py`.
- **Comment-out only removes the tools from MCP discovery**: the parked `sb_*` code paths remain
  importable and callable in-process. That is acceptable here because the real block is backend-side —
  the endpoints themselves stop supporting tag mutation. The MCP change stops clients calling
  something that no longer works; it is not itself the enforcement point.
- **Ordering relative to the backend change**: if MCP and backend land far apart there is a window
  where either the tools are gone while the backend still accepts writes (harmless), or the tools are
  still advertised while the backend rejects them (harmful — agents get opaque failures). The second
  direction is the one to avoid.
- **Commented-out code decays**: ~100 lines of dormant registration plus dormant tests will drift
  from the live code. The re-enable trigger is the backend cloned-move fix landing.
- **Live E2E writes**: `TestPlaybookTagWriteE2E` mutates tags on a real console through the preserved
  `sb_*` functions. Once the backend removes tag mutation it will fail regardless of the MCP change,
  so it should be skip-marked here.
- **Partial withdrawal is a trap**: leaving any one of the six registered (e.g. forgetting a bulk
  variant) leaves a tool advertised that will fail against the changed backend, while appearing done.
  The acceptance criteria must enumerate all six by name.
- **Read-tool assumption**: "keep the read tools" rests on them reading the attacks listing rather
  than the write endpoints (finding 2). If the cloned-move bug also corrupts the tag values *as read*,
  that assumption needs revisiting — see open question 2.

### Open Questions
1. Is the backend removing the two move-tags endpoints entirely (404), or keeping them and rejecting
   writes? Determines how the parked `sb_*` functions fail if ever called, and how
   `TestPlaybookTagWriteE2E` should be marked.
2. Do the read-only tag tools stay correct under the cloned-move bug? They surface tags from the
   attacks listing, not the write endpoints — confirm the cloned-move handling does not also make
   *read* values wrong or misleading.
3. Should the module-level imports of the six write functions be commented out too, or kept so the
   dormant tests can be re-enabled unchanged?
4. Should this ship before, with, or after the backend change?
