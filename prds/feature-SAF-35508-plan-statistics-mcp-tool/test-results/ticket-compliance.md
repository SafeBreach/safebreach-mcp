# Ticket Compliance — SAF-35508

> PRD: ../prd.md | Run: 2026-09-03 (iteration 2 — after provisioning saf-35508) | Iterations: 2/5 | HEAD: (this commit)

Extraction mode: **Subtask with an explicit "Acceptance criteria" section** — the 12 numbered criteria are
TI-1…TI-12, in field order. Base ref `origin/main`, merge-base `1b6f63f`; diff scope 21 files,
12 354 insertions.

## Coverage

| TI | Item | Source | Mapped to | Status | Evidence / Justification |
|----|------|--------|-----------|--------|---------------------------|
| TI-1 | Ad-hoc plan body scored; `scenario_id` passed as `{id}`; step-less plan raises a typed error | AC-1 | Phases 2, 5, 7 | 🟡 accepted | Substance covered: T-6, T-8, T-26 green. Mechanism accepted — an OOB UUID has no field on the endpoint that accepts it (probed live), so it is resolved to steps; integer ids pass through. See `context.md` |
| TI-2 | Per-step `simulationCount`, `moves`, three simulator maps, `isLimitReached`, structured constraints; five query params pass through with documented defaults | AC-2 | Phase 2 | ✅ covered | T-6 (unreduced response), T-9 (all five params + overrides); `safebreach_mcp_core/plan_statistics.py` |
| TI-3 | Runnable by default; expected available; both labelled; docs state expected is not derivable | AC-3 | Phases 2, 5, 7 | ✅ covered | T-27 (one call or two, labelled), T-30 (inversion observed live on `zircon-piculet`: 1,971 vs 578,148) |
| TI-4 | Numbers match the console per view and per parameter set | AC-4 | Final (T-35) | ✅ **covered (numbers)** / 🟡 accepted (rendered view) | **Verified live on `saf-35508`.** Checkout param set (`includeDisabled=true`): console `[54, 1, 0, 0]` == counts tool `[54, 1, 0, 0]`. Run-gating (`false`): identical match. Mode labels correct, runnable ≤ expected. e2e suite 11 passed / 2 skipped. Remaining: the *rendered* Checkout figure — browser MCPs unavailable; T-35 not marked passed. `environment.md` |
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
- 9 ✅ covered (TI-4 substantively; its rendered-view half remains accepted) · 3 🟡 accepted · 0 ❌ open.
- The acceptances are recorded in `context.md` under `## Accepted Ticket-Compliance Gaps`, each naming the
  decision that superseded the criterion and where it is documented. TI-4's entry is superseded by the live
  verification above and by `environment.md`; only its rendered-view half still stands.

## The one that mattered — now largely closed

Three of the four acceptances are bookkeeping: the ticket was written before SAF-35568 shipped, before the
endpoint was probed, and before decision D4. Those criteria describe a design that was deliberately replaced,
and the repo asserts the replacement.

**TI-4 was not bookkeeping, and it has now been exercised.** A Validate console (`saf-35508`) was provisioned
for exactly this purpose. The counts tool reproduces the console's own numbers under the console's own
parameter sets, on a live 4-step scenario. What remains is only the *rendered* half — reading the figure out
of the Checkout view in a browser — which is blocked on tooling, not on the feature. That sliver stays
accepted; the substance is verified.

**Running against a real console immediately earned its keep.** Three defects surfaced that every mocked test
had passed straight through:
- T-48 read `os_type` / `isConnected` under the wrong names, so it would have skipped on **every** console
  forever while blaming the fleet — a test that can never fail is worse than no test.
- It then read the playbook response under the wrong key, and posted a filter missing its required `operator`.
- 🔴 And a genuine product finding: an attack the orchestrator never turns into a move comes back **`absent`**
  — "not present in this scenario" — for an attack the caller just named in that scenario's filter. Spec-correct
  (AC-9 governs `moves[id] === 0`, which never occurs there) and user-facing wrong. Recorded in
  `environment.md` §Known gaps as follow-up work.

## Verdict

RESULT: 3 gaps (3 accepted, TI-4 substantively verified — rendered-view half outstanding)
