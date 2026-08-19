# Test Plan — Disclose Propagate Attacks in Playbook Tools (SAF-34553)

> PRD: ./prd.md  |  Branch: bugfix/SAF-34553-disclose-propagate-attacks  |  Status: Draft  |  Updated: 2026-08-19 13:26

## Status & Review

| Field | Value |
|-------|-------|
| Status | Draft (In Sync with PRD v1) |
| Offering / surface | repo-harness (primary) + console (one thin real-API slice); content spans Validate and Propagate |

## Requirements Traceability

Sources: JIRA acceptance criteria ∪ PRD §7 Definition of Done (user-confirmed at the authoring gate).

| Req | Requirement (from SAF-34553 ∪ PRD §7) | Covered by | Status |
|-----|----------------------------------------|------------|--------|
| R1 | Default (no `test_type`) returns Validate only; total excludes every Propagate attack | T-11, T-12, T-19, T-24, T-33 | Covered |
| R2 | `test_type='propagate'` returns only Propagate, never mixed | T-8, T-26 | Covered |
| R3 | `test_type='all'` reports a split total and marks Propagate rows | T-9, T-20, T-21, T-32 | Covered |
| R4 | A default call that excluded attacks discloses the excluded count and how to include them | T-15, T-16, T-17, T-18, T-33, T-34 | Covered |
| R5 | Discriminator matches group id 44 / name `ALM` / value `1`; value `0` is Validate | T-1, T-2, T-3, T-4 | Covered |
| R6 | Scope applied before pagination — total reflects scope | T-12, T-24 | Covered |
| R7 | Applied scope appears in applied-filters output | T-14, T-27 | Covered |
| R8 | `get_playbook_attacks_by_tags` honors `test_type` with the same default | T-25, T-26, T-27 | Covered |
| R9 | `get_playbook_attack_details` marks a Propagate attack as not reachable from the Playbook | T-28, T-31 | Covered |
| R10 | Invalid `test_type` raises an error naming the valid values | T-13, T-34 | Covered |
| R11 | No regression of SAF-33946 (Propagate-disabled metadata behaviour) | — | **Out of scope — justified.** T-30 tombstoned: the guarded behaviour is absent from this repo (no SAF-33946 commit, no entitlement branch in the details path). Phase 7 adds a line and modifies no existing branch, so there is no code path here to regress. Entitlement lives upstream in content-manager. |
| R12 | Verified on a Propagate-capable console; staging cannot exercise this path | T-24, T-31, T-33 | Covered |
| R13 | Unpublished drafts are hidden by default, so a reported total equals what the Playbook UI displays | T-35, T-36, T-40, T-43, T-44, T-46 | Covered |
| R14 | Drafts remain reachable on request, and their exclusion is disclosed | T-37, T-38, T-39, T-41, T-42, T-47 | Covered |
| R15 | The render paths tolerate a null description (strict-review crashes in touched lines) | T-48, T-49, T-50, T-51 | Covered |

## Change Coverage

| File | Covered by | Justification (if no unit test) |
|------|------------|---------------------------------|
| `safebreach_mcp_playbook/playbook_types.py` | T-1..T-10, T-36 | — |
| `safebreach_mcp_playbook/playbook_functions.py` | T-11..T-19, T-25..T-28, T-35, T-37..T-43 | — |
| `safebreach_mcp_playbook/playbook_server.py` | T-20..T-23, T-29, T-34, T-47, T-48..T-51 | — |

## Risk Landscape

- **Known risk areas** (PRD §9 + reviewer input at gate):
  - Narrowing the default result set changes numbers existing tests/consumers assert.
  - Restructuring the details response could regress SAF-33946 (Propagate metadata leak when Propagate disabled).
  - The excluded-count ordering trap: counting after the scope filter always reports zero; counting before the other criteria filters reports attacks the tactic filter already removed.
  - Overwriting an existing `hint_to_agent` (the next-page hint) instead of composing with it.
  - `sb_get_playbook_attacks_by_tags` currently **assigns** `applied_filters = {'tags': tags}`, overwriting whatever the paginator set — adding `test_type` there is a known overwrite hazard.
  - The 30-minute in-process cache serving pre-change reduced payloads after a deploy.
- **Existing coverage (investigated)**: `filter_attacks_by_criteria` → `safebreach_mcp_playbook/tests/test_playbook_types.py` (`TestFilteringFunctions`, `TestMitreFiltering`, `TestPlatformFiltering`); `sb_get_playbook_attacks` → `tests/test_playbook_functions.py` (`TestGetPlaybookAttacks`, `TestMitreGetPlaybookAttacks`, `TestPlatformGetPlaybookAttacks`); `paginate_attacks`, `transform_*` → `tests/test_playbook_types.py`; real-API precedent → `tests/test_e2e.py` (`TestPlatformE2E`, 14 tests — a new filter axis given a full real-API class). This plan targets the gaps below.
- **What we protect**: existing name/description/id/date/MITRE/platform filtering behaviour; the next-page hint contract; the not-found error path of the details tool; SAF-33946's Propagate-disabled metadata handling.
- **Gaps this plan closes**:
  - The MCP server layer's Markdown formatting has **no tests at all** today (`tests/test_playbook_server.py` asserts only tool registration and config parsing). Header subtotals and row markers land on untested surface — T-20..T-23 are the first tests of their kind for that layer.
  - No fixture in the repo carries a tag group with id 44 / name `ALM`. One is introduced, captured verbatim from pentest01's real moves payload rather than hand-shaped.
  - `paginate_attacks` has no test covering a caller-supplied `hint_to_agent` — only the next-page one (T-17).
- **A second cause was missed by the original ticket.** Excluding Propagate alone took the reporter's query from 181 to 136 while the Playbook UI showed 121. The residual 15 were unpublished BREACH_STUDIO drafts — the same defect class (undisclosed scope), different cause. The plan's reconciliation test is now T-46, and the ticket's premise ("Helm's number should agree with the UI") was only satisfied after Phase 8.
- **The `move` table is not the population the API serves.** The KB API returns 10,056 moves against 9,605 rows in `move`; the difference is custom/Studio content. Any DB-based cross-check in this plan is against a subset — the ALM count (111) matched exactly only because custom moves are not ALM-tagged.
- **Anti-test — staging-management produces a FALSE PASS**: staging-management has 9,497 moves and **zero** ALM tags. Every scope assertion trivially passes there while proving nothing. Any real-API test must assert a non-zero ALM count as a precondition, or skip loudly. Recorded here because it is the single most likely way a future executor reports a green run that means nothing.
- **Intentionally out of scope**:
  - **The Helm-facing UI/LLM route** (automation repo `tests/automation_team/pen_test/ui/ai/helm/`, driven by `Jenkinsfile.HelmTests.groovy` with its `swap_images` artifact injection). Scoped out at the gate to avoid the two-repo build chain (repin `requirements.txt` → build `mcp-proxy` → `dpull` → verify `pip freeze`). **Consequence, stated plainly**: nothing in this plan proves Helm's *phrasing* to the customer actually improved — only that the data and the disclosure hint reaching Helm are correct. T-33 partially mitigates by judging an agent's comprehension of the tool output directly.
  - **A Manual regression test is deliberately absent.** Every regression assertion on this surface is deterministic (scope counts, filter behaviour, rendered markers) and is therefore carried by Automatic tests, which the ownership model prefers over Manual. The only genuinely judgment-based surface — how Helm phrases the answer — is the out-of-scope route above. Regression is instead protected by T-24/T-31 (real-API, Automatic) plus the whole unit suite.
  - **Seeding or tagging ALM moves through a product API.** No such mechanism exists: every fixture path found in the automation repo creates *custom moves/scenarios*, not tag-group-tagged OOB playbook moves. Confirmed at the gate: ALM content is a property of the console's content package, so real-API tests assert against what the KB returns and skip when the console reports zero ALM moves.

## Coverage Summary (generated)

| Execution | unit | integration | system | e2e | Total |
|-----------|------|-------------|--------|-----|-------|
| Automatic | 42   | 0           | 0      | 7   | 49    |
| Manual    | 0    | 0           | 0      | 1   | 1     |

## Environment Requirements (aggregated)

- Environment classes: `none` (unit — the overwhelming majority); `console environment` (Validate console **entitled to Propagate content**) for T-24, T-31, T-32, T-33.

Capability checklist — answered from the plan's real-env (e2e) tests only:

- [x] **Simulators required?** — **No.** Every real-env test reads the move *catalog*; no simulator executes anything.
- [x] **Running simulations / attacks required?** — **No.** The ALM tag exists on catalog content independently of any run; pentest01's existing 111 ALM moves are sufficient.
- [x] **Mockulators sufficient?** — **N/A.** No simulators of any kind are needed, real or mock.
- [x] **Console-specific configuration required?** — **Yes.** A content package containing Propagate/ALM-tagged moves (tag group 44 / `ALM` / `1`) — the single hard gate. Plus valid e2e auth per `E2E_TESTING.md` (`E2E_CONSOLE`, `E2E_CONSOLE_URL`, `E2E_CONSOLE_ACCOUNT`, `<console>_apitoken`).
- [x] **Lateral-movement topology required?** — **No.** No DC, patient-zero or victim host. The feature never reads or produces Propagate *findings*, only ALM-tagged catalog rows. A `create-propagate-environment` build was explicitly rejected: it provisions topology and does not guarantee ALM content in the catalog.
- Required additions (beyond class defaults): a console with a **non-zero ALM move count** — verify before designing anything else. pentest01 (`i-0b889ae01e44bf882`) qualifies; staging-management is disqualified.
- Artifacts under test: none. Real-env tests run the repo's own code against a live console API; no `mcp-proxy` rebuild is required for the chosen route.

## Regression

- **CI that must pass**: the repo's `.pre-commit-config.yaml` hooks plus the local playbook suite (`uv run pytest safebreach_mcp_playbook/tests/ -m "not e2e"`). **Known gap, confirmed at the gate**: `safebreach-mcp` has no CI job that runs its unit suites — `.github/workflows/` contains only `release.yml` and `security-scan.yml`. "The relevant CI is green" is therefore currently unenforceable for this repo and deserves its own ticket. The automation-repo Helm suite (`Jenkins-jobs/pen-testing/helm/Jenkinsfile.HelmTests.groovy`) is **not** in scope for this change.
- **Regression tests in this plan**: T-19 (repro-regression keyed to the reported defect), T-22 (existing single-total header preserved), T-17 (existing next-page hint preserved), T-24 (real-API coherence). No Manual regression test — justified in the Risk Landscape.

## Tests

**Unit** — all Automatic; environment: none

| Test | Description | Aspect | Passes after | Repo |
|------|-------------|--------|--------------|------|
| T-1 | Group 44 named ALM with value 1 is Propagate | — | Phase 1 | safebreach_mcp_playbook |
| T-2 | Group 44 named ALM with value 0 is NOT Propagate | — | Phase 1 | safebreach_mcp_playbook |
| T-3 | Malformed or absent tag data is not Propagate | — | Phase 1 | safebreach_mcp_playbook |
| T-4 | Both id and name must match; neither alone qualifies | — | Phase 1 | safebreach_mcp_playbook |
| T-5 | `is_propagate` is always present on a reduced attack | API-contract | Phase 2 | safebreach_mcp_playbook |
| T-6 | `is_propagate` carries the discriminator's verdict | API-contract | Phase 2 | safebreach_mcp_playbook |
| T-7 | Validate scope excludes Propagate attacks | — | Phase 3 | safebreach_mcp_playbook |
| T-8 | Propagate scope keeps only Propagate attacks | — | Phase 3 | safebreach_mcp_playbook |
| T-9 | All scope filters nothing out | — | Phase 3 | safebreach_mcp_playbook |
| T-10 | Scope comparison is case-insensitive | — | Phase 3 | safebreach_mcp_playbook |
| T-11 | Omitting `test_type` defaults to Validate scope | — | Phase 4 | safebreach_mcp_playbook |
| T-12 | Reported total reflects scope, not the unfiltered catalog | regression | Phase 4 | safebreach_mcp_playbook |
| T-13 | Invalid `test_type` raises naming the valid values | — | Phase 4 | safebreach_mcp_playbook |
| T-14 | Applied scope is echoed in applied filters | API-contract | Phase 4 | safebreach_mcp_playbook |
| T-15 | Default-scoped call discloses the excluded Propagate count | — | Phase 4 | safebreach_mcp_playbook |
| T-16 | No exclusion hint when nothing was excluded | — | Phase 4 | safebreach_mcp_playbook |
| T-17 | The existing next-page hint is preserved, not overwritten | regression | Phase 4 | safebreach_mcp_playbook |
| T-18 | Excluded count is computed after the other criteria filters | — | Phase 4 | safebreach_mcp_playbook |
| T-19 | The reported defect: tactic filter + default scope excludes Propagate | regression | Phase 4 | safebreach_mcp_playbook |
| T-20 | All scope renders a split per-catalog header | — | Phase 5 | safebreach_mcp_playbook |
| T-21 | Propagate rows are marked not reachable from the Playbook | — | Phase 5 | safebreach_mcp_playbook |
| T-22 | Non-all scope keeps the existing single-total header | regression | Phase 5 | safebreach_mcp_playbook |
| T-23 | Missing per-catalog counts fall back to the single total | — | Phase 5 | safebreach_mcp_playbook |
| T-25 | Tag search defaults to Validate scope | — | Phase 6 | safebreach_mcp_playbook |
| T-26 | Tag search honours Propagate scope without mixing | — | Phase 6 | safebreach_mcp_playbook |
| T-27 | Tag search echoes scope without losing the tags filter | regression | Phase 6 | safebreach_mcp_playbook |
| T-28 | Details marks a Propagate attack as unreachable | — | Phase 7 | safebreach_mcp_playbook |
| T-29 | Details output is unchanged for a Validate attack | regression | Phase 7 | safebreach_mcp_playbook |
| T-34 | Valid-value enum and user-facing copy are exact | API-contract | Final | safebreach_mcp_playbook |
| T-35 | Unpublished drafts are excluded by default | — | Phase 8 | safebreach_mcp_playbook |
| T-36 | A move with no status field is not a draft | — | Phase 8 | safebreach_mcp_playbook |
| T-37 | `include_drafts=True` brings drafts back | — | Phase 8 | safebreach_mcp_playbook |
| T-38 | Draft exclusion is disclosed with its count | — | Phase 8 | safebreach_mcp_playbook |
| T-39 | No draft hint when nothing was hidden | — | Phase 8 | safebreach_mcp_playbook |
| T-40 | Per-catalog counts describe visible, non-draft attacks | — | Phase 8 | safebreach_mcp_playbook |
| T-41 | The draft and catalog gates are independent | — | Phase 8 | safebreach_mcp_playbook |
| T-42 | Applied filters record the draft gate | API-contract | Phase 8 | safebreach_mcp_playbook |
| T-43 | Tag search excludes drafts by default | regression | Phase 8 | safebreach_mcp_playbook |
| T-48 | Listing render survives a null description | regression | Phase 8 | safebreach_mcp_playbook |
| T-49 | Listing render truncates a long description | regression | Phase 8 | safebreach_mcp_playbook |
| T-50 | Listing render keeps a short description verbatim | regression | Phase 8 | safebreach_mcp_playbook |
| T-51 | Details render survives a null description | regression | Phase 8 | safebreach_mcp_playbook |

**E2E**

| Test | Description | Exec | Aspect | Passes after | Repo | Environment |
|------|-------------|------|--------|--------------|------|-------------|
| T-24 | Real console: default scope excludes ALM moves and scopes are coherent | Automatic | regression | Phase 5 | safebreach_mcp_playbook | console environment |
| T-31 | Real console: details on a real ALM attack states it is unreachable | Automatic | — | Phase 7 | safebreach_mcp_playbook | console environment |
| T-32 | Real console: rendered subtotals agree with the function-layer counts | Automatic | API-contract | Final | safebreach_mcp_playbook | console environment |
| T-33 | An agent reading the tool output does not present Propagate as Playbook content | Manual | progression | Final | — | console environment |
| T-44 | Real console: drafts hidden by default and the hidden count disclosed | Automatic | regression | Phase 8 | safebreach_mcp_playbook | console environment |
| T-45 | Real console: the draft and catalog gates stay independent | Automatic | — | Phase 8 | safebreach_mcp_playbook | console environment |
| T-46 | Real console: the reporter's query equals the Playbook UI count | Automatic | regression | Phase 8 | safebreach_mcp_playbook | console environment |
| T-47 | Real console: draft rows are marked when included | Automatic | — | Phase 8 | safebreach_mcp_playbook | console environment |

### T-1 — Group 44 named ALM with value 1 is Propagate

- Description: Proves the discriminator recognises the one tag shape that actually marks a Propagate attack.
- Status: Active
- Passes after: Phase 1
- Level: unit
- Execution: Automatic
- Risk: A wrong predicate silently mis-scopes the entire catalog in both directions.
- Risk source: PRD §9
- Verify: Call the discriminator with a tag list containing a group whose id is 44, name is `ALM`, and whose values include an entry with value `1`.
- Expected: Returns true.
- Evidence required: CI run — local `uv run pytest safebreach_mcp_playbook/tests/ -m "not e2e"` output, until repo CI exists.
- Automation lives in: `planned: safebreach_mcp_playbook/tests/test_playbook_types.py` (new `TestPropagateDiscriminator` class, mirroring `TestPlatformFiltering`)
- Environment needs: none

### T-2 — Group 44 named ALM with value 0 is NOT Propagate

- Description: Proves the predicate reads the tag's value rather than merely its presence — the specific defect declined from ui-react's `isAlmMove`.
- Status: Active
- Passes after: Phase 1
- Level: unit
- Execution: Automatic
- Risk: Presence-only matching would classify an explicitly non-ALM attack as Propagate and hide it from the default result set — a silent data loss with no error.
- Risk source: reviewer input
- Verify: Call the discriminator with group id 44, name `ALM`, values containing only an entry with value `0`.
- Expected: Returns false.
- Evidence required: CI run — local pytest output.
- Automation lives in: `planned: safebreach_mcp_playbook/tests/test_playbook_types.py`
- Environment needs: none

### T-3 — Malformed or absent tag data is not Propagate

- Description: Proves the predicate degrades to "Validate" rather than raising, matching the defensive style of the sibling tag extractors.
- Status: Active
- Passes after: Phase 1
- Level: unit
- Execution: Automatic
- Risk: An exception here would break every listing call, since the predicate runs per attack on every request.
- Risk source: PRD §8 Phase 1
- Verify: Call the discriminator with each of: `None`; a non-list value; a list containing non-dict members; a matching group whose values key is missing; a matching group whose values is not a list; an empty list.
- Expected: Returns false for every input; raises nothing.
- Evidence required: CI run — local pytest output.
- Automation lives in: `planned: safebreach_mcp_playbook/tests/test_playbook_types.py`
- Environment needs: none

### T-4 — Both id and name must match; neither alone qualifies

- Description: Proves the predicate requires the id and the name together, so an unrelated group that reuses either one cannot masquerade as ALM.
- Status: Active
- Passes after: Phase 1
- Level: unit
- Execution: Automatic
- Risk: Matching on id alone couples correctness to a content id that could be reassigned; matching on name alone would catch a differently-scoped group with the same label.
- Risk source: reviewer input
- Verify: Call the discriminator with (a) id 44 and a non-ALM name, and (b) an ALM name with a different id — both carrying value `1`.
- Expected: Returns false in both cases.
- Evidence required: CI run — local pytest output.
- Automation lives in: `planned: safebreach_mcp_playbook/tests/test_playbook_types.py`
- Environment needs: none

### T-5 — `is_propagate` is always present on a reduced attack

- Description: Proves the field is unconditional, so neither the filter nor the renderer has to defend against its absence.
- Status: Active
- Passes after: Phase 2
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: A conditionally-emitted field would make scope filtering silently treat unmarked attacks as Validate.
- Risk source: PRD §9
- Verify: Reduce an attack whose tags contain no ALM group, and one with no tags key at all.
- Expected: The Propagate boolean key is present on both results, false in both.
- Evidence required: CI run — local pytest output.
- Automation lives in: `planned: safebreach_mcp_playbook/tests/test_playbook_types.py` (mirrors `TestPlatformGetPlaybookAttacks::test_platform_fields_always_present`)
- Environment needs: none

### T-6 — `is_propagate` carries the discriminator's verdict

- Description: Proves the reduced payload's flag actually reflects the underlying tag data rather than a constant.
- Status: Active
- Passes after: Phase 2
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: A hard-coded or inverted flag would pass T-5 while breaking every scope assertion downstream.
- Risk source: PRD §9
- Verify: Reduce two attacks from the ALM-bearing fixture — one tagged ALM value 1, one untagged.
- Expected: True for the ALM-tagged attack, false for the other.
- Evidence required: CI run — local pytest output.
- Automation lives in: `planned: safebreach_mcp_playbook/tests/test_playbook_types.py`
- Environment needs: none

### T-7 — Validate scope excludes Propagate attacks

- Description: Proves the scope filter removes Propagate attacks when Validate is requested.
- Status: Active
- Passes after: Phase 3
- Level: unit
- Execution: Automatic
- Risk: The core of R1; a broken filter reproduces the original defect.
- Risk source: PRD §9
- Verify: Filter a mixed list (engineered asymmetric: 3 Validate, 2 Propagate, so a collapsed count cannot coincidentally match) with Validate scope.
- Expected: Exactly the 3 Validate attacks, by id; neither Propagate id appears.
- Evidence required: CI run — local pytest output.
- Automation lives in: `planned: safebreach_mcp_playbook/tests/test_playbook_types.py`
- Environment needs: none

### T-8 — Propagate scope keeps only Propagate attacks

- Description: Proves R2 at the filter level — a Propagate request is never contaminated with Validate content.
- Status: Active
- Passes after: Phase 3
- Level: unit
- Execution: Automatic
- Risk: Mixing in the other direction is as misleading as the reported defect.
- Risk source: PRD §9
- Verify: Filter the same asymmetric mixed list with Propagate scope.
- Expected: Exactly the 2 Propagate attacks, by id; no Validate id appears.
- Evidence required: CI run — local pytest output.
- Automation lives in: `planned: safebreach_mcp_playbook/tests/test_playbook_types.py`
- Environment needs: none

### T-9 — All scope filters nothing out

- Description: Proves the escape hatch genuinely returns both catalogs.
- Status: Active
- Passes after: Phase 3
- Level: unit
- Execution: Automatic
- Risk: If All silently filtered, the split header would report a total the rows contradict.
- Risk source: PRD §9
- Verify: Filter the asymmetric mixed list with All scope.
- Expected: All 5 attacks returned.
- Evidence required: CI run — local pytest output.
- Automation lives in: `planned: safebreach_mcp_playbook/tests/test_playbook_types.py`
- Environment needs: none

### T-10 — Scope comparison is case-insensitive

- Description: Proves scope handling matches the sibling module's case-insensitive contract, so an agent passing a capitalised value is not silently mis-scoped.
- Status: Active
- Passes after: Phase 3
- Level: unit
- Execution: Automatic
- Risk: An LLM-supplied value with different casing falling through to "no filter" would reproduce the defect while appearing to honour the request.
- Risk source: reviewer input
- Verify: Filter with mixed-case spellings of each scope value.
- Expected: Identical results to the lowercase spellings.
- Evidence required: CI run — local pytest output.
- Automation lives in: `planned: safebreach_mcp_playbook/tests/test_playbook_types.py`
- Environment needs: none

### T-11 — Omitting `test_type` defaults to Validate scope

- Description: Proves expected result 1 at the function boundary — the default is safe without the caller doing anything.
- Status: Active
- Passes after: Phase 4
- Level: unit
- Execution: Automatic
- Risk: The entire fix depends on the default; a permissive default leaves the bug in place for every existing caller.
- Risk source: PRD §9
- Verify: Call the listing function with no scope argument, over a mocked fetch returning the asymmetric mixed dataset.
- Expected: No Propagate attack appears in the page, and the reported total equals the Validate count.
- Evidence required: CI run — local pytest output.
- Automation lives in: `planned: safebreach_mcp_playbook/tests/test_playbook_functions.py` (new `TestTestTypeGetPlaybookAttacks` class, mirroring `TestPlatformGetPlaybookAttacks`)
- Environment needs: none

### T-12 — Reported total reflects scope, not the unfiltered catalog

- Description: Proves the ordering requirement R6 — scope is applied before pagination, which is what makes the headline number in the bug report correct.
- Status: Active
- Passes after: Phase 4
- Level: unit
- Execution: Automatic
- Aspect: regression
- Risk: Filtering after pagination would return correct rows with a wrong total — exactly the symptom the customer reported, in a subtler form that row-level assertions would miss.
- Risk source: PRD §9
- Verify: Call the listing function with Validate scope over a mocked dataset of more than one page (engineered so Validate and total differ and neither equals a page size), and inspect the reported total and page count.
- Expected: The total equals the Validate-only count and the page count is derived from it, not from the unfiltered catalog size.
- Evidence required: CI run — local pytest output.
- Automation lives in: `planned: safebreach_mcp_playbook/tests/test_playbook_functions.py`
- Environment needs: none

### T-13 — Invalid `test_type` raises naming the valid values

- Description: Proves an unusable value fails loudly with a message an agent can recover from, matching the sibling module's error contract.
- Status: Active
- Passes after: Phase 4
- Level: unit
- Execution: Automatic
- Risk: Silently ignoring an unrecognised scope would return the merged catalog — the original defect, triggered by a typo.
- Risk source: PRD §9
- Verify: Call the listing function with an unrecognised scope string.
- Expected: Raises, and the message names all three valid values.
- Evidence required: CI run — local pytest output.
- Automation lives in: `planned: safebreach_mcp_playbook/tests/test_playbook_functions.py`
- Environment needs: none

### T-14 — Applied scope is echoed in applied filters

- Description: Proves R7 — the scope in force is visible in the response, so the answer's scope is self-describing rather than implicit.
- Status: Active
- Passes after: Phase 4
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: An undisclosed active filter is the root class of this whole bug.
- Risk source: PRD §9
- Verify: Call the listing function with each scope value and read the applied-filters map.
- Expected: The map contains the scope actually applied, including on a defaulted call.
- Evidence required: CI run — local pytest output.
- Automation lives in: `planned: safebreach_mcp_playbook/tests/test_playbook_functions.py`
- Environment needs: none

### T-15 — Default-scoped call discloses the excluded Propagate count

- Description: Proves R4 — the default is safe *and* honest, which is the inversion of the reported complaint.
- Status: Active
- Passes after: Phase 4
- Level: unit
- Execution: Automatic
- Risk: A silent default filter trades one undisclosed scope for another.
- Risk source: PRD §9
- Verify: Call the listing function with no scope over the asymmetric mixed dataset and read the agent hint.
- Expected: The hint states the number of Propagate attacks excluded (2 for the engineered fixture) and names the value that includes them.
- Evidence required: CI run — local pytest output.
- Automation lives in: `planned: safebreach_mcp_playbook/tests/test_playbook_functions.py`
- Environment needs: none

### T-16 — No exclusion hint when nothing was excluded

- Description: Proves the disclosure is conditional, so a Validate-only console does not emit a confusing "0 excluded" line.
- Status: Active
- Passes after: Phase 4
- Level: unit
- Execution: Automatic
- Risk: An unconditional hint would add noise to every response on the majority of consoles, which have no Propagate content at all.
- Risk source: reviewer input
- Verify: Call the listing function with no scope over a dataset containing zero Propagate attacks.
- Expected: No exclusion hint is present.
- Evidence required: CI run — local pytest output.
- Automation lives in: `planned: safebreach_mcp_playbook/tests/test_playbook_functions.py`
- Environment needs: none

### T-17 — The existing next-page hint is preserved, not overwritten

- Description: Proves the new disclosure composes with the paginator's existing hint rather than replacing it — a named risk, and a contract the paginator has no test for today.
- Status: Active
- Passes after: Phase 4
- Level: unit
- Execution: Automatic
- Aspect: regression
- Risk: Overwriting the next-page hint would silently strip the agent's only signal that more pages exist, breaking pagination behaviour that works today.
- Risk source: PRD §9
- Verify: Call the listing function with no scope over a multi-page dataset that also contains Propagate attacks, on a page that is not the last.
- Expected: The hint conveys both the next-page instruction and the excluded count.
- Evidence required: CI run — local pytest output.
- Automation lives in: `planned: safebreach_mcp_playbook/tests/test_playbook_functions.py`
- Environment needs: none

### T-18 — Excluded count is computed after the other criteria filters

- Description: Proves the ordering trap named in PRD §8 Phase 4 — the excluded count must describe what this query dropped, not what the whole catalog holds.
- Status: Active
- Passes after: Phase 4
- Level: unit
- Execution: Automatic
- Risk: Counting before the other criteria filters would tell the customer "45 Propagate attacks excluded" when their tactic filter already removed 40 of them — a new misleading number introduced by the fix for a misleading number.
- Risk source: PRD §9
- Verify: Call the listing function with no scope plus a criteria filter (e.g. a MITRE tactic) engineered so that only a subset of the Propagate attacks match that criterion.
- Expected: The excluded count equals the number of Propagate attacks that matched the other criteria, not the dataset's total Propagate count.
- Evidence required: CI run — local pytest output.
- Automation lives in: `planned: safebreach_mcp_playbook/tests/test_playbook_functions.py`
- Environment needs: none

### T-19 — The reported defect: tactic filter + default scope excludes Propagate

- Description: The repro-regression test keyed to the RCA — red before the fix, green after. Reconstructs the reporter's exact query shape.
- Status: Active
- Passes after: Phase 4
- Level: unit
- Execution: Automatic
- Aspect: regression
- Risk: Without a test pinned to the original reproduction, a future refactor can reintroduce the merged total without failing anything.
- Risk source: PRD §9
- Verify: Reproduce the reported query — a credential-access MITRE tactic filter with no scope argument — over a fixture holding both Validate and Propagate attacks that carry that tactic.
- Expected: The reported total counts only the Validate attacks carrying the tactic, and no Propagate attack appears in the returned rows.
- Evidence required: CI run — local pytest output, plus a recorded red run against the pre-fix code.
- Automation lives in: `planned: safebreach_mcp_playbook/tests/test_playbook_functions.py`
- Environment needs: none

### T-20 — All scope renders a split per-catalog header

- Description: Proves expected result 3's presentation half — the customer sees which catalogs the total spans.
- Status: Active
- Passes after: Phase 5
- Level: unit
- Execution: Automatic
- Risk: This is the first test of the server layer's formatting; that layer has no coverage at all today.
- Risk source: reviewer input
- Verify: Invoke the listing tool with All scope over a mocked function-layer result carrying per-catalog counts, and read the rendered header text.
- Expected: The header states the overall total and both per-catalog figures, and the three are arithmetically consistent.
- Evidence required: CI run — local pytest output.
- Automation lives in: `planned: safebreach_mcp_playbook/tests/test_playbook_server.py` (new formatting test class — none exists)
- Environment needs: none

### T-21 — Propagate rows are marked not reachable from the Playbook

- Description: Proves the row-level half of expected result 3 — the customer can tell which listed attacks they cannot open.
- Status: Active
- Passes after: Phase 5
- Level: unit
- Execution: Automatic
- Risk: An unmarked Propagate row in an All-scoped answer is the original complaint verbatim.
- Risk source: PRD §9
- Verify: Invoke the listing tool with All scope over a mocked result mixing Propagate and Validate attacks, and inspect the rendered block for each.
- Expected: Every Propagate attack's block carries the unreachable-from-Playbook marker; no Validate attack's block does.
- Evidence required: CI run — local pytest output.
- Automation lives in: `planned: safebreach_mcp_playbook/tests/test_playbook_server.py`
- Environment needs: none

### T-22 — Non-all scope keeps the existing single-total header

- Description: Proves the header change is confined to All scope, so the format existing consumers and tests read is untouched elsewhere.
- Status: Active
- Passes after: Phase 5
- Level: unit
- Execution: Automatic
- Aspect: regression
- Risk: Rewriting the header unconditionally is an unnecessary contract change on the majority path.
- Risk source: PRD §9
- Verify: Invoke the listing tool with Validate and with Propagate scope.
- Expected: The header retains its current single-total form in both cases.
- Evidence required: CI run — local pytest output.
- Automation lives in: `planned: safebreach_mcp_playbook/tests/test_playbook_server.py`
- Environment needs: none

### T-23 — Missing per-catalog counts fall back to the single total

- Description: Proves the renderer degrades rather than raising if the counts are absent or malformed.
- Status: Active
- Passes after: Phase 5
- Level: unit
- Execution: Automatic
- Risk: A formatting exception would turn a cosmetic gap into a total tool failure for the customer.
- Risk source: reviewer input
- Verify: Invoke the listing tool with All scope over mocked results whose per-catalog counts are absent, then non-numeric.
- Expected: The single-total header is rendered; no exception propagates.
- Evidence required: CI run — local pytest output.
- Automation lives in: `planned: safebreach_mcp_playbook/tests/test_playbook_server.py`
- Environment needs: none

### T-24 — Real console: default scope excludes ALM moves and scopes are coherent

- Description: Proves the fix against the real catalog rather than a frozen fixture, catching any drift in the tag-44 shape that a fixture cannot.
- Status: Active
- Passes after: Phase 5
- Level: e2e
- Execution: Automatic
- Aspect: regression
- Risk: The fixture is frozen truth; if content-manager ever changes the tag group shape, every unit test stays green while the feature silently stops filtering.
- Risk source: PRD §9
- Verify: Against a live console, first assert the precondition that the Propagate-scoped call returns a non-zero count — if it is zero, fail with an explicit "console has no Propagate content, this test proves nothing" message rather than passing. Then call the tool with each of the three scopes and compare the reported totals.
- Expected: Propagate count is non-zero; Validate total plus Propagate total equals the All total; no attack reported under Validate scope is also reported under Propagate scope.
- Evidence required: CI run — `source .vscode/set_env.sh && uv run pytest -m "e2e" safebreach_mcp_playbook/tests/` output, with the console name and observed counts recorded.
- Automation lives in: `planned: safebreach_mcp_playbook/tests/test_e2e.py` (new `TestPropagateScopeE2E` class, mirroring `TestPlatformE2E`)
- Environment needs: console environment
  - Non-default addition: the console must be entitled to Propagate content (non-zero ALM move count). pentest01 qualifies; staging-management is disqualified — see the anti-test note in the Risk Landscape.

### T-25 — Tag search defaults to Validate scope

- Description: Proves R8's default — the same defect is not reachable through the tag-search door.
- Status: Active
- Passes after: Phase 6
- Level: unit
- Execution: Automatic
- Risk: Leaving tag search unscoped means the customer asks a slightly different question and gets the old merged answer.
- Risk source: PRD §9
- Verify: Call the tag-search function with a tag that both Validate and Propagate attacks carry, and no scope argument.
- Expected: Only Validate attacks are returned and the total reflects that.
- Evidence required: CI run — local pytest output.
- Automation lives in: `planned: safebreach_mcp_playbook/tests/test_tag_tools.py`
- Environment needs: none

### T-26 — Tag search honours Propagate scope without mixing

- Description: Proves R2 holds on the tag-search path as well as the main listing path.
- Status: Active
- Passes after: Phase 6
- Level: unit
- Execution: Automatic
- Risk: Divergent scope behaviour between two tools answering the same question is its own inconsistency bug.
- Risk source: PRD §9
- Verify: Call the tag-search function with the shared tag and Propagate scope.
- Expected: Only Propagate attacks are returned.
- Evidence required: CI run — local pytest output.
- Automation lives in: `planned: safebreach_mcp_playbook/tests/test_tag_tools.py`
- Environment needs: none

### T-27 — Tag search echoes scope without losing the tags filter

- Description: Guards a specific known hazard — the tag-search path currently assigns its applied-filters map wholesale, so adding scope there can silently drop the tags entry.
- Status: Active
- Passes after: Phase 6
- Level: unit
- Execution: Automatic
- Aspect: regression
- Risk: The existing code replaces rather than merges the applied-filters map; a careless addition loses either the tags or the scope from the disclosed filters, reintroducing an undisclosed filter.
- Risk source: PRD §9
- Verify: Call the tag-search function with tags and an explicit scope, then read the applied-filters map.
- Expected: Both the tags entry and the scope entry are present.
- Evidence required: CI run — local pytest output.
- Automation lives in: `planned: safebreach_mcp_playbook/tests/test_tag_tools.py`
- Environment needs: none

### T-28 — Details marks a Propagate attack as unreachable

- Description: Proves R9 — a customer handed a Propagate attack id is told why they cannot find it in the Playbook.
- Status: Active
- Passes after: Phase 7
- Level: unit
- Execution: Automatic
- Risk: Half the reported pain is being given an id and name that cannot be opened; without this the fix addresses only the counting half.
- Risk source: PRD §9
- Verify: Invoke the details tool for an ALM-tagged attack id over a mocked fetch.
- Expected: The rendered output states the attack is a Propagate attack and is not reachable from the Playbook.
- Evidence required: CI run — local pytest output.
- Automation lives in: `planned: safebreach_mcp_playbook/tests/test_playbook_functions.py`
- Environment needs: none

### T-29 — Details output is unchanged for a Validate attack

- Description: Proves the marker is additive and does not alter the output customers already see for ordinary attacks.
- Status: Active
- Passes after: Phase 7
- Level: unit
- Execution: Automatic
- Aspect: regression
- Risk: Restructuring the details rendering is the named path to a SAF-33946 regression.
- Risk source: PRD §9
- Verify: Invoke the details tool for a non-ALM attack and compare the rendered output against the pre-change expectation.
- Expected: No Propagate marker appears and the remaining output is unchanged.
- Evidence required: CI run — local pytest output.
- Automation lives in: `planned: safebreach_mcp_playbook/tests/test_playbook_functions.py`
- Environment needs: none

### T-30 — SAF-33946 Propagate-disabled metadata behaviour is unchanged

- Description: Explicit no-regression guard for the previously-fixed metadata leak, since this change touches the same tool.
- Status: Removed — **the behaviour this test guards does not exist in this repo.** Verified during Phase 7: no commit in `safebreach-mcp` references SAF-33946, there is no PRD folder for it, and `sb_get_playbook_attack_details` contains no entitlement or Propagate-disabled branch at all — it locates the attack and transforms it. Package entitlement is enforced upstream in content-manager (`getLicensedContentPackageIds`, `PROPAGATE_PACKAGE_IDS`), so a Propagate-disabled console would not receive ALM moves from the KB moves API in the first place; that upstream location is **inference, not verified**. Writing a test here would have asserted invented behaviour. R11 is consequently not covered by this plan — see the traceability note.
- Passes after: Phase 7
- Level: unit
- Execution: Automatic
- Aspect: regression
- Risk: Re-leaking full metadata for Propagate ids when Propagate is disabled would reopen a closed bug on the same code path.
- Risk source: PRD §9
- Verify: Reproduce SAF-33946's condition — request details for a Propagate attack id under the Propagate-disabled state its fix guards — and assert the behaviour that fix established still holds with the marker added.
- Expected: The SAF-33946 behaviour is unchanged; the marker does not bypass or alter it.
- Evidence required: CI run — local pytest output, with the SAF-33946 assertion identified.
- Automation lives in: `planned: safebreach_mcp_playbook/tests/test_playbook_functions.py`
- Environment needs: none

### T-31 — Real console: details on a real ALM attack states it is unreachable

- Description: Proves the reachability marker fires for a genuine ALM attack from the live catalog, not just a hand-built fixture.
- Status: Active
- Passes after: Phase 7
- Level: e2e
- Execution: Automatic
- Risk: The marker depends on the same tag shape as the filter; a real-catalog check is the only thing that catches upstream drift.
- Risk source: PRD §9
- Verify: Against a live console, list with Propagate scope, take the first returned attack id, then request its details.
- Expected: The details output carries the unreachable-from-Playbook marker. If Propagate scope returns nothing, fail with the no-Propagate-content message rather than passing.
- Evidence required: CI run — e2e pytest output with the console name and the attack id used.
- Automation lives in: `planned: safebreach_mcp_playbook/tests/test_e2e.py`
- Environment needs: console environment
  - Non-default addition: console entitled to Propagate content (non-zero ALM move count).

### T-32 — Real console: rendered subtotals agree with the function-layer counts

- Description: The cross-layer consistency check — the same fact asserted through two layers must agree, so a correct count cannot be rendered wrongly.
- Status: Active
- Passes after: Final
- Level: e2e
- Execution: Automatic
- Aspect: API-contract
- Risk: The function layer and the renderer compute and display the split independently; a formatting bug could show figures that contradict the data the agent received.
- Risk source: reviewer input
- Verify: Against a live console, call the tool with All scope and parse the rendered header's per-catalog figures; separately obtain the counts from the function layer for the same console and scope.
- Expected: The rendered figures equal the function-layer counts, and the two per-catalog figures sum to the rendered overall total.
- Evidence required: CI run — e2e pytest output showing both sets of figures.
- Automation lives in: `planned: safebreach_mcp_playbook/tests/test_e2e.py`
- Environment needs: console environment
  - Non-default addition: console entitled to Propagate content (non-zero ALM move count).

### T-33 — An agent reading the tool output does not present Propagate as Playbook content

- Description: Sign-off evidence that the disclosure actually works on its intended consumer — an LLM — which is the one thing no deterministic assertion can establish.
- Status: Active
- Passes after: Final
- Level: e2e
- Execution: Manual
- Aspect: progression
- Risk: The hint and marker could be technically present but too subtle for a model to act on, leaving the customer-visible defect intact despite every automated test passing.
- Risk source: reviewer input
- Verify: An AI executor, with the playbook MCP tools connected to a Propagate-capable console, issues the reporter's prompt ("Show me all attacks related to credential access"), then a follow-up asking for Propagate attacks as well. It records the full transcript and judges: did the first answer avoid naming any Propagate attack? Did it surface that Propagate attacks exist and were excluded? Did the second answer distinguish the two catalogs and state that Propagate attacks are not reachable from the Playbook?
- Expected: All three judgements hold. Any failure is reported as a failure with the transcript, never smoothed over. If the tools cannot be connected, the test reports BLOCKED rather than an improvised pass.
- Evidence required: full prompt-and-response transcript, the console name, the observed attack counts, and an explicit observed-vs-expected verdict per judgement.
- Manual because: the assertion is whether an LLM comprehends and acts on the disclosure — non-deterministic judgment about generated natural language, which cannot be reduced to a deterministic check. The mechanical facts underneath it are covered automatically by T-24 and T-32.
- Environment needs: console environment
  - Non-default addition: console entitled to Propagate content (non-zero ALM move count).

### T-34 — Valid-value enum and user-facing copy are exact

- Description: Pins the declarative surface — the accepted scope vocabulary and the exact wording the customer and the agent read.
- Status: Active
- Passes after: Final
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: The scope values are a contract with the agent and, once the Playbook UI ships its test-type filter, with the UI too; drifting copy weakens the disclosure the whole fix exists to provide.
- Risk source: reviewer input
- Verify: Assert the exact set of accepted scope values; assert the validation message names all of them; assert the Propagate row marker text and the exclusion hint text against their expected wording; assert the tool description states the default scope and how to request Propagate or both.
- Expected: All values and strings match exactly; the accepted set has no fourth member.
- Evidence required: CI run — local pytest output.
- Automation lives in: `planned: safebreach_mcp_playbook/tests/test_playbook_server.py`
- Environment needs: none


### T-35 to T-43 — draft exclusion (unit)

- Description: prove unpublished drafts are hidden by default, reachable on request, disclosed when hidden, and that the draft gate is independent of the catalog scope.
- Status: Active
- Passes after: Phase 8
- Level: unit
- Execution: Automatic
- Aspect: regression (T-43)
- Risk: Hiding drafts silently would repeat the very defect this ticket fixes; treating a statusless move as a draft would hide almost the entire catalog (most OOB moves carry no status at all).
- Risk source: reviewer input — discovered by cross-checking the fix against a live console
- Verify: over a fixture of published, statusless, and draft moves (one draft also Propagate-tagged): default excludes drafts (T-35); the statusless move stays visible (T-36); `include_drafts=True` restores them (T-37); the hint names the hidden count and how to include them (T-38); no hint when nothing was hidden (T-39); per-catalog counts describe the non-draft population (T-40); opening one gate does not open the other (T-41); the gate appears in applied filters (T-42); tag search behaves identically (T-43).
- Expected: as stated per test; ids asserted explicitly, never just counts.
- Evidence required: CI run — local `uv run pytest safebreach_mcp_playbook/tests/ -m "not e2e"` output.
- Automation lives in: `safebreach_mcp_playbook/tests/test_playbook_functions.py` (`TestDraftExclusion`) and `tests/test_tag_tools.py` (`TestDraftExclusionByTags`)
- Environment needs: none

### T-44 to T-47 — draft exclusion (real console)

- Description: prove against live content that the draft gate behaves as designed and that the reported total reconciles with the Playbook UI — the ticket's actual acceptance test.
- Status: Active
- Passes after: Phase 8
- Level: e2e
- Execution: Automatic
- Aspect: regression (T-44, T-46)
- Risk: The whole ticket exists because Helm's number contradicted the UI. Only a live comparison can prove they now agree; fixtures cannot.
- Risk source: reviewer input
- Verify: default vs `include_drafts=True` totals differ and the delta is disclosed, failing loudly if the console has no drafts (T-44); the draft and catalog gates compose without leaking into each other (T-45); the Credential Access default total equals `PLAYBOOK_UI_CREDENTIAL_ACCESS_COUNT`, skipping when unset rather than asserting an unverified number (T-46); a rendered draft row carries its marker (T-47).
- Expected: T-46 is the reconciliation assertion — observed 121 == 121 on pentest01.
- Evidence required: e2e pytest output with the observed totals; for T-46, the human-observed UI count recorded alongside.
- Automation lives in: `safebreach_mcp_playbook/tests/test_e2e.py` (`TestDraftExclusionE2E`)
- Environment needs: console environment
  - Non-default addition: the console must carry unpublished Breach Studio drafts, and for T-46 the operator must supply the UI's observed count via `PLAYBOOK_UI_CREDENTIAL_ACCESS_COUNT`.

### T-48 to T-51 — null-description render guards (unit)

- Description: regression guards for two `TypeError` crashes the strict review confirmed in the render blocks this ticket edits.
- Status: Active
- Passes after: Phase 8
- Level: unit
- Execution: Automatic
- Aspect: regression
- Risk: `transform_reduced_playbook_attack` always SETS the description key, so a missing API description arrives as `None` and `dict.get`'s default never fires — slicing it raises, and the outer handler swallows the crash into a generic error message. Pre-existing on main, but in lines this ticket touches, and the render layer had zero tests before this ticket.
- Risk source: PRD §9 + strict review
- Verify: render a listing with a null description (T-48), an over-long one (T-49), a short one (T-50), and render attack details with a null description (T-51).
- Expected: the placeholder appears, truncation is applied only past the limit, and no generic error surfaces.
- Evidence required: CI run — local pytest output.
- Automation lives in: `safebreach_mcp_playbook/tests/test_playbook_server.py` (`TestNullDescriptionRendering`)
- Environment needs: none

## Tests by Phase (readiness view — generated)

| After phase | Newly green | Cumulative green |
|-------------|-------------|------------------|
| Phase 1 | T-1, T-2, T-3, T-4 | T-1..T-4 |
| Phase 2 | T-5, T-6 | T-1..T-6 |
| Phase 3 | T-7, T-8, T-9, T-10 | T-1..T-10 |
| Phase 4 | T-11, T-12, T-13, T-14, T-15, T-16, T-17, T-18, T-19 | T-1..T-19 |
| Phase 5 | T-20, T-21, T-22, T-23, T-24 | T-1..T-24 |
| Phase 6 | T-25, T-26, T-27 | T-1..T-27 |
| Phase 7 | T-28, T-29, T-31 | T-1..T-31 (T-30 removed) |
| Phase 8 | T-35..T-51 | T-1..T-51 (T-30 removed) |
| Final | T-32, T-33, T-34 | all |

## Sign-off

- [ ] Requirements traceability complete — every R# covered or explicitly out-of-scope
- [ ] Change Coverage complete — every changed file tested or justified
- [ ] Regression complete — Manual regression justified in Risk Landscape + post-ship CI named (with the known repo-CI gap recorded)
- [ ] Progression evidence — T-33 executed with transcript
- [ ] validating-test-plan: RESULT: clean
- [ ] All tests green (cumulative through Final) — evidence: test-results/<phase-or-date>.md
- [ ] Accepted gaps listed and approved: Helm UI/LLM route out of scope; Manual regression absent by justification; repo has no unit-test CI; R11/T-30 out of scope (guarded behaviour absent from repo)

## Change Log

| Date | Change |
|------|--------|
| 2026-08-19 13:26 | Test plan created from PRD v1 |
| 2026-08-19 14:55 | T-30 tombstoned — SAF-33946's guarded behaviour is absent from this repo; R11 moved to justified out-of-scope. Status stays Draft (material change). |
| 2026-08-19 16:10 | Added T-35..T-51 for Phase 8 (draft exclusion) and the strict-review null-description guards. R13-R15 added. Status stays Draft (material change). |
