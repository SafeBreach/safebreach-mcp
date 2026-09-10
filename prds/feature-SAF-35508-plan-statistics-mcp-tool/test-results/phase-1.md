# Test Results — Phase 1 (SAF-35508)
> Plan: ../test-plan.md | Run: 2026-08-27T14:59:04Z | Mode: run

Phase 1 — Relay the orchestrator's constraint catalog (delete the vendored translation table).

## Preflight (Step 0)

| Check | Result |
|-------|--------|
| Dispatch mode | source-repo **uv-pytest** (standalone-Python repo: `pyproject.toml` + `uv.lock`, no `package.json`) |
| `uv` toolchain | ✓ present — `uv 0.9.25` |
| Interpreter pin | ✓ `--python 3.12` mandatory; bare `pytest` resolves 3.14, for which `pydantic-core` has no wheel |
| Bootstrap | ✓ `uv sync` satisfied from `uv.lock` |
| Environment reachability | n/a — every selected test declares `Environment needs: none` (no console, no AWS/SSM, no VPN) |
| Sub-runners | n/a — no e2e / system / Helm / Manual test in this phase's set |
| Data preconditions | n/a — no test reads backend data |
| Unwritten tests | ✗ **stale marker** — all four are `Automation lives in: planned:`, but were authored and committed this session (`8a444f8`). See Smell observations. |

## Accounting

| T-\<n\> | Level | Execution | Env | Runner (intended) | Outcome | Evidence / Reason |
|-------|-------|-----------|-----|-------------------|---------|-------------------|
| T-1 | unit | Automatic | none | source-repo uv-pytest | executed | 4/4 PASSED — `TestNoVendoredConstraintVocabulary` (see Evidence) |
| T-3 | unit | Automatic | none | source-repo uv-pytest | executed | 5/5 PASSED — `TestUnrecognisedConstraintCode` |
| T-38 | unit | Automatic | none | source-repo uv-pytest | executed | 6/6 PASSED — `TestConstraintDescriptionsRelayedVerbatim` |
| T-39 | unit | Automatic | none | source-repo uv-pytest | executed | 6/6 PASSED — `TestAbsentConstraintCatalog` |

Ledgered = 4. Selected = 4. No test dropped.

## Cumulative readiness

- Selected (Passes after ≤ 1, Active): T-1, T-3, T-38, T-39
- Green: T-1, T-3, T-38, T-39 · BLOCKED: none · Unwritten-planned: none · Delegated: none
- Phase verdict: **PASS**

## Evidence

Command (evidence for all four):

```
uv run --python 3.12 pytest safebreach_mcp_studio/tests/test_studio_functions.py -v -m "not e2e" \
  -k "TestNoVendoredConstraintVocabulary or TestUnrecognisedConstraintCode or \
      TestConstraintDescriptionsRelayedVerbatim or TestAbsentConstraintCatalog or TestRenderConstraintReason"
→ 25 passed, 455 deselected in 0.12s
```

- **T-1**: executed — `test_constraint_reason_descriptions_symbol_is_gone`,
  `test_no_constraint_fix_levers_symbol`, `test_no_module_constant_maps_reason_codes_to_prose`,
  `test_no_module_constant_maps_reason_codes_to_a_lever` — all PASSED. Repo-wide grep confirms zero
  references to `CONSTRAINT_REASON_DESCRIPTIONS`; the only surviving `fixable` token is the lever-detection
  guard inside T-1's own assertion.
- **T-3**: executed — `test_code_absent_from_catalog_resolves_to_null_description`,
  `test_code_present_with_empty_entry_resolves_to_null_description`,
  `test_resolver_never_returns_the_code_as_the_description`,
  `test_unrecognised_code_is_still_surfaced_as_a_conflict`,
  `test_aggregated_summary_surfaces_unrecognised_code_with_null_description` — all PASSED. Both miss forms
  (code absent from the catalog; present with an empty `{}` entry) resolve to `description: None`, and the
  conflict is still surfaced in both the per-attack and aggregated views.
- **T-38**: executed — `test_awkward_descriptions_relayed_byte_for_byte`,
  `test_contradicting_description_is_not_corrected_toward_the_code_name`,
  `test_catalog_keys_are_the_api_code_strings_unchanged`,
  `test_empty_string_description_is_relayed_not_nulled`,
  `test_summarize_constraints_relays_description_verbatim`,
  `test_catalog_is_read_from_the_response_root_not_from_a_step` — all PASSED. Leading/trailing whitespace,
  internal double space, inconsistent terminal punctuation, non-ASCII (`Sécurité … é`) and a description that
  contradicts its own code name all survive byte-for-byte. The root-vs-step case plants a decoy
  `constraintCatalog` inside `steps[0]` and asserts the root value wins.
- **T-39**: executed — `test_absent_catalog_does_not_raise_and_nulls_every_description`,
  `test_empty_catalog_does_not_raise_and_nulls_every_description`,
  `test_every_referenced_code_key_is_present_not_omitted`,
  `test_conflicts_are_still_surfaced_when_no_catalog_supplied`, `test_hint_names_the_missing_catalog`,
  `test_get_scenario_statistics_survives_a_response_with_no_catalog` — all PASSED. Neither an absent nor an
  empty catalog raises; every referenced code key is present with `description: None`; conflicts keep their
  `code` and `detail`; the catalog-absent hint is emitted.
  **Post-run amendment:** `test_hint_names_the_missing_catalog` and the hint it covered were removed after
  this run, on the PRD owner's ruling that every console serves SAF-35568's catalog. T-39's other five cases
  are unaffected and still green; the suite total is 1437 (not 1438) as of that removal.

Regression context — full repo suite, same run: **1438 passed, 137 deselected, 0 failed**
(`safebreach_mcp_config` + `_data` + `_utilities` + `_playbook` + `_studio`, `-m "not e2e"`).
Pre-change baseline on this branch was 1434 passed / 0 failed.

## Hand-off (delegated / BLOCKED)

None.

## To author (unwritten-planned)

None. All four selected tests are authored (committed in `8a444f8`), despite the plan still marking them
`planned:` — see Smell observations.

## Manual substitutions (not the planned test)

None.

## Smell observations

1. **`test-plan.md`'s `Automation lives in:` is stale for T-1/T-3/T-38/T-39** — still prefixed `planned:`
   though the file now exists and the tests run. Left as-is here because this runner does not edit the plan;
   drop the `planned:` prefix via `authoring-test-plan` so a future phase run doesn't mis-classify them as
   `unwritten-planned`.
2. **T-39's `Expected` straddles two phases.** It asserts each conflict carries `severity`, `side` and
   `simulator_count`, and that `hint_to_agent` names the missing catalog — but PRD §8 builds `severity`,
   `side` and `simulator_count` in **Phase 4**, and `hint_to_agent` in Phase 4/5. Phase 1 emits
   `{move_id, reasons: [{code, description, detail}]}`. The provable half was implemented and is green
   (no raise, key present, `description: None`, conflicts surfaced); the conflict-shape clauses must be
   re-asserted at Phase 4, or T-39's `Passes after` moved to Phase 4. **The hint clause is now
   unsatisfiable by design** — the PRD owner ruled that every console serves SAF-35568's catalog, so the
   catalog-absent hint was removed after this run; T-39 needs rescoping to its remaining assertions.
3. **No `T-<n>` covers the preview renderer.** `_render_constraint_reason` (`studio_server.py`) was added
   under an approved Phase-1 scope extension because `description` became nullable and the renderer indexed
   it directly, printing the literal string `None`. Four tests were written for it
   (`TestRenderConstraintReason`) and are green, but they answer to no plan item — a plan gap to back-fill.
   Its absence of coverage is what let a real defect (empty-string vs never-supplied conflation) through the
   first review pass.
4. **`_build_constraint_catalog` has no production caller.** It is a named Phase 1 deliverable that PRD §8
   Phase 4 consumes ("built by Phase 1's builder"), so this is by design — but a builder whose only consumer
   is its own tests is exactly the kind of thing that quietly never gets wired. Flagged for Phase 4 sign-off.
5. **A user-visible affordance was removed by design.** Dropping `fixable` also removed the
   "⚠ N attacks require configuration not addressable via `step_overrides`" footer from `run_scenario`
   previews. PRD-sanctioned (§9 R7, "MCP asserts no remedy at all"), but `run_scenario`'s tool description
   still frames its three-turn workflow around `step_overrides` as the remedy.

## Verdict

- **PASS** — every cumulative test for Phase 1 green, each with the pytest run output its `Evidence required`
  field demands. No BLOCKED, no unwritten-planned, no manual substitution.
