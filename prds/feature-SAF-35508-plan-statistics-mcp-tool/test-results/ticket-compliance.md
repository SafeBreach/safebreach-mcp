# Ticket Compliance — SAF-35508

> PRD: ../prd.md | Run: 2026-09-03 | Iterations: 1/5 | HEAD: 1e93f1cf29bf8604c666bb3300c735abebd23843

Extraction mode: **Subtask with an explicit "Acceptance criteria" section** — the 12 numbered criteria are
TI-1…TI-12, in field order. Base ref `origin/main`, merge-base `1b6f63f`; diff scope 21 files,
12 354 insertions.

## Coverage

| TI | Item | Source | Mapped to | Status | Evidence / Justification |
|----|------|--------|-----------|--------|---------------------------|
| TI-1 | Ad-hoc plan body scored; `scenario_id` passed as `{id}`; step-less plan raises a typed error | AC-1 | Phases 2, 5, 7 | 🟡 accepted | Substance covered: T-6, T-8, T-26 green. Mechanism accepted — an OOB UUID has no field on the endpoint that accepts it (probed live), so it is resolved to steps; integer ids pass through. See `context.md` |
| TI-2 | Per-step `simulationCount`, `moves`, three simulator maps, `isLimitReached`, structured constraints; five query params pass through with documented defaults | AC-2 | Phase 2 | ✅ covered | T-6 (unreduced response), T-9 (all five params + overrides); `safebreach_mcp_core/plan_statistics.py` |
| TI-3 | Runnable by default; expected available; both labelled; docs state expected is not derivable | AC-3 | Phases 2, 5, 7 | ✅ covered | T-27 (one call or two, labelled), T-30 (inversion observed live on `zircon-piculet`: 1,971 vs 578,148) |
| TI-4 | Numbers match the console per view and per parameter set | AC-4 | Final (T-35) | 🟡 accepted | **Never verified.** T-35 is Manual and has never run; no console provisioned. Everything else establishes self-consistency, not correctness. See `context.md` |
| TI-5 | `isLimitReached` reported; `null` (not computed) kept distinct from `0`; short step list surfaced; no zero-impact reporting on that path | AC-5 | Phases 2, 4 | ✅ covered | T-10, T-15 (crash fixed at three sites), T-22 (reporting suppressed by construction) |
| TI-6 | No estimation path outside `plan/statistics`; `_get_scenario_statistics` and both callers migrated | AC-6 | Phase 3 | ✅ covered | T-16; verified at HEAD — one URL builder, `safebreach_mcp_core/plan_statistics.py:140`. The three new tools route through `sb_get_plan_statistics`, adding no second path |
| TI-7 | `CONSTRAINT_REASON_DESCRIPTIONS` deleted, no meaning vendored; **all 88 codes carry a `fix_lever`**; test fails if a code lacks one | AC-7 | Phase 1 | 🟡 accepted | Deletion covered: T-1, T-38, T-39; symbol absent from source. Lever map **deliberately not built** — SAF-35568 removed `fixLever` as redundant. Repo asserts its absence. See `context.md` |
| TI-8 | Conflicts normalized (catalog + references); `severity` computed from counts alone; every conflict surfaced; `description: null` marked, never omitted | AC-8 | Phase 4 | ✅ covered | T-23, T-36 (one code both blocking and reducing in one step), T-3 (unrecognised code surfaced). The AC's "null lever" clause falls with TI-7 |
| TI-9 | `moves[id] === 0` reported as inapplicable with its blocking conflicts; save not blocked; never reported on `null` | AC-9 | Phases 4, 8 | ✅ covered | T-20 (integer-zero predicate), T-22; rendered to the caller by `get_scenario_blocked_entities` |
| TI-10 | `simulators[id] === 0` reported the same way, from the **union** map | AC-10 | Phases 4, 8 | ✅ covered | T-21 (one-sided nodes not falsely reported) |
| TI-11 | Any changed decision triggers a fresh call; no MCP-side caching | AC-11 | Phase 2 | ✅ covered | T-12 (repeated identical calls each hit the API); no cache in `plan_statistics.py` |
| TI-12 | Registered as **`get_plan_statistics`**, `readOnlyHint=True`, in the CLAUDE.md catalog; gate table not extended | AC-12 | Phases 5, 8, 9 | 🟡 accepted | Read-only ✅ (T-24), catalogued ✅ (T-34), gate table unextended ✅ (verified: the CLAUDE.md diff contains no table rows). Registered as **three** tools per decision D4. See `context.md` |

## Accounting

- 12 items extracted; 12 appear above with exactly one Status. No item dropped.
- 8 ✅ covered · 4 🟡 accepted · 0 ❌ open.
- All four acceptances are recorded in `context.md` under `## Accepted Ticket-Compliance Gaps`, each naming
  the decision that superseded the criterion and where it is documented.

## The one that matters

Three of the four acceptances are bookkeeping: the ticket was written before SAF-35568 shipped, before the
endpoint was probed, and before decision D4. Those criteria describe a design that was deliberately replaced,
and the repo asserts the replacement.

**TI-4 is not bookkeeping.** It is the only criterion that would establish the numbers are *right* rather than
internally consistent, and it has never been exercised. 1 927 tests pass; none of them has seen a SafeBreach
console. Accepting it is a decision to ship verified-internally and unverified-against-the-product, and it
should be read that way.

## Verdict

RESULT: 4 gaps (4 accepted)
