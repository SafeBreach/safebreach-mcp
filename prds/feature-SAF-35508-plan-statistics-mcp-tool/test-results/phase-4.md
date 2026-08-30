# Test Results — Phase 4 (SAF-35508)
> Plan: ../test-plan.md | Run: 2026-08-27 | Mode: run

Phase 4 — Translation + zero-impact reporting layer.

## Preflight (Step 0)

| Check | Result |
|-------|--------|
| Dispatch mode | source-repo **uv-pytest** |
| `uv` toolchain | ✓ `uv 0.9.25`; `--python 3.12` pin mandatory |
| Environment reachability | ✓ genuinely n/a — the layer is a pure function over the Phase 2 fetch-core dict: no transport, no auth context, no console |
| `Environment needs` accuracy | ✓ **correct for the first time** — T-18…T-23 and T-36 all say `none`, which matches reality |
| Unwritten tests | ✗ stale `planned:` markers again |

## Accounting

| T-\<n\> | Level | Execution | Env | Runner | Outcome | Evidence / Reason |
|-------|-------|-----------|-----|--------|---------|-------------------|
| T-1, T-3, T-38, T-39 | unit | Automatic | none | uv-pytest | executed | cumulative re-run, green |
| T-6 … T-12 | integration | Automatic | none¹ | uv-pytest | executed | cumulative re-run, green |
| T-13 … T-17 | integration | Automatic | none¹ | uv-pytest | executed | cumulative re-run, green — the Phase 3 goldens still hold |
| T-18 | unit | Automatic | none | uv-pytest | executed | 4/4 PASSED — `TestSparseConstraintMapIsNotDense` |
| T-19 | unit | Automatic | none | uv-pytest | executed | 4/4 PASSED — `TestEveryReasonInAConstraintLeafSurfaces` |
| T-20 | unit | Automatic | none | uv-pytest | executed | 5/5 PASSED — `TestZeroImpactAttacksRequireIntegerZero` |
| T-21 | unit | Automatic | none | uv-pytest | executed | 5/5 PASSED — `TestZeroImpactSimulatorsComeFromTheUnionMap` |
| T-22 | unit | Automatic | none | uv-pytest | executed | 6/6 PASSED — `TestLimitReachedSuppressesZeroImpactReporting` |
| T-23 | unit | Automatic | none | uv-pytest | executed | 6/6 PASSED — `TestConflictsAreNormalizedAgainstTheCatalog` |
| T-36 | unit | Automatic | none | uv-pytest | executed | 6/6 PASSED — `TestSeverityIsComputedFromTheAttackCount` |

¹ the plan says `repo-harness`; every one mocks the transport. Recorded since Phase 2.

Ledgered = 23. Selected = 23. No test dropped.

## Cumulative readiness

- Selected (Passes after ≤ 4, Active): T-1, T-3, T-38, T-39, T-6…T-12, T-13…T-17, T-18…T-23, T-36
- Green: all 23 · BLOCKED: none · Unwritten-planned: none · Delegated: none
- Phase verdict: **PASS**

## Evidence

```
uv run --python 3.12 pytest safebreach_mcp_studio/tests/test_studio_functions.py -q \
  -k "Sparse or EveryReason or ZeroImpactAttacks or ZeroImpactSimulators or \
      LimitReachedSuppresses or NormalizedAgainstTheCatalog or SeverityIsComputed or \
      ConflictDetailModes or DisagreeingValues or CountsModeIsDerived"
→ 50 passed
```

Full repo suite: **1676 passed, 137 deselected, 0 failed**.

- **T-18**: executed — with three simulators in scope and one in the constraint map, only that one
  produces a conflict and only it is reported zero-impact. The other two keep their entries in the
  relayed count maps (they are genuinely in scope) but gain no conflict rows, and nothing anywhere
  describes them as unevaluated or unknown.
- **T-19**: executed — all three reasons in one leaf surface; the same simulator appearing on both sides
  merges to `side: ['attacker', 'target']` with `simulator_count: 1` rather than one side overwriting
  the other or the node being double-counted.
- **T-20**: executed — of `{'281': 40, '226': 0, '9012': None}` only `226` is zero-impact. The null is
  absent from every zero-impact list, and a boolean `False` count is not treated as zero either.
- **T-21**: executed — only the union-map zero is reported. A simulator absent from a role map is not
  reported on that basis, and a null union count is not reported at all.
- **T-22**: executed — the fixture deliberately carries non-empty `simulatorConstraints`, so suppression
  is proved rather than trivially satisfied: no zero-impact lists, no conflicts, an empty catalog, and a
  hint stating that null means not-computed rather than zero.
- **T-23**: executed — the catalog holds one entry per distinct code present, excludes a code the
  response describes but MCP never emits, gives an unrecognised code `{'description': None}`, and no
  conflict entry carries a `description` at all. Three attacks share one code; the catalog holds it once.
- **T-36**: executed — `incompatible_os` resolves `blocking` for the zero-count attack and `reducing`
  for both positive-count attacks **within one step**, and the verdict is unchanged when the catalog is
  absent or when it describes the code as something harmless.

## Hand-off (delegated / BLOCKED)

None.

## To author (unwritten-planned)

None.

## Manual substitutions (not the planned test)

None.

## Smell observations

1. **Four approved deviations from §4's response example** (owner-approved before implementation).
   §4's example is authoritative for structure, not for these values:
   - **`severity: "none"` is not emitted.** §4's third conflict shows `none` for an attack whose count is
     240, which §3 Component D, §7, §8 Phase 4 and §9 R8 all say must be `reducing`. It is residue from
     the `informational` code classification that §2's alternatives table rejects as *"premise was
     wrong"* — the same premise that tombstoned T-37. **§4's example needs correcting.**
   - `zero_impact_simulators` blockers carry `attack_count`, not a constant `simulator_count: 1`.
   - `simulator_name` is omitted when unresolvable — no source for it exists in this repo.
   - `is_limit_reached` is always emitted, so its absence is never ambiguous.
2. **`summary` and `per_attack` differ only by name resolution.** §8 says `summary` "groups by code with
   counts", but T-23's `Expected` requires every conflict to carry `attack_id`, and T-36 requires two
   severities for one shared code — severity is per-attack by construction. A code-only grouping would
   fail both reviewed tests, so the grouping unit is `(attack_id, code)` in all three modes. §8's "the
   default must stay cheap" goal is therefore only partly met: the default is already per-attack-code.
   **Either §8 is reworded or a genuine code-level summary needs its own `T-<n>`.**
3. **No `T-<n>` covers `conflict_detail` at all** — not the three modes, not the capped `simulator_ids`
   sample that is the anti-explosion guarantee, not the `ValueError` guard. 14 branch tests were written
   without a plan item, after a review found every non-default branch untested.
4. **T-39's deferred clauses are still not closed.** phase-1.md owed Phase 4 the assertion that
   conflicts keep `severity`, `attack_id`, `side` and `simulator_count` **on a catalog-absent response**.
   T-36's last two cases assert severity survives an absent catalog, but nothing asserts the full
   four-key shape there. Owed to `authoring-test-plan`, not to another phase.
5. **`predicted_simulations: 0` on a truncated response is still live** and is now *pinned green* by
   T-15's two caller cases from Phase 3. Fixing it needs a plan item, a `T-<n>`, and an amendment to
   those two cases — deliberately not absorbed here.
6. **The layer has no production caller until Phase 5.** It does, however, close Phase 1's dead-code
   smell: `_build_plan_statistics_report` is `_build_constraint_catalog`'s first non-test consumer.
7. **Nothing exercises the fetch-core → shaping seam.** Phase 4's tests build the fetch-core dict by
   hand. If a field name drifted between the two layers, only Phase 5's tool tests would catch it.

## Verdict

- **PASS** — every cumulative test for Phase 4 green with the pytest output its `Evidence required`
  demands. No BLOCKED, no unwritten-planned, no manual substitution.
