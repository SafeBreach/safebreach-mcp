# PRD — MCP support for Core plan statistics API (`get_plan_statistics`) — SAF-35508

## 1. Overview

- **Title**: MCP support for Core plan statistics API: ad-hoc plan impact, per-attack/simulator counts, and constraints — SAF-35508
- **Task Type**: feature + refactor (+ bug fix — three live defects in the existing private helper)
- **Purpose**: Helm must repeatedly answer, mid-conversation, *"given the configuration as it stands right
  now, what will actually run, what will not, and why?"* Core already answers this via
  `POST /orch/v1/accounts/{accountId}/plan/statistics`. MCP reaches that endpoint today only through a
  **private, hardcoded, lossy and partly incorrect** pre-flight helper buried inside two run-oriented tools.
  This subtask promotes that integration into a first-class read-only tool and fixes its defects.
- **Target Consumer**: Internal — the Helm conversational agent is the primary caller. Secondarily any MCP
  client (Claude Desktop) doing pre-flight impact analysis.
- **Target Roles (RBAC)**: Inherits the caller's console API token. The endpoint is read-only; existing
  `check_rbac_response` handling applies. No new role surface.
- **Key Benefits**:
  1. A **read-only** impact primitive. Today the only route to impact data is `run_scenario` / `quick_run` —
     tools declared as *running a test*, which queue a real one at `evaluate=False`.
  2. **Correct** numbers. Runnable counts become reachable for the first time, along with the
     `simulator_is_offline` reason that explains the gap between expected and runnable.
  3. **Actionable** conflicts. Every one of the 88 reason codes gets a `fix_lever` naming the control surface
     that resolves it — the fact a calling model cannot infer. Meanings are **not** MCP's to own: the
     translation table is deleted outright and descriptions become SAF-35568's deliverable (§9, §10).
- **Business Alignment**: Implements functional requirements **6** and **7** of parent story SAF-34615
  ("MCP support for Validate scenario creation and update, Stage 1"), and covers parent Definition-of-Done
  items **2** and **5**. See §9 for the DoD-6 caveat introduced by the scope decision.
- **Originating Request**: [SAF-35508](https://safebreach.atlassian.net/browse/SAF-35508), subtask of
  [SAF-34615](https://safebreach.atlassian.net/browse/SAF-34615).

---

## 1.5 Document Status

| Field | Value |
|-------|-------|
| **PRD Status** | In Review |
| **Last Updated** | 2026-08-26 |
| **Owner** | Boris Berezovsky (AI-assisted planning) |
| **Current Phase** | N/A — not started |

---

## 2. Solution Description

### Chosen solution — a new raw fetch core, with the existing helper refactored on top of it

Four pieces, in dependency order:

1. **Delete the translation table; keep a fix-lever map.** `CONSTRAINT_REASON_DESCRIPTIONS` is removed
   outright rather than extended — MCP stops owning constraint *meanings* altogether. What remains is a
   `CONSTRAINT_FIX_LEVERS` map: for each of the 88 emitted codes, the control surface that resolves it. Helm
   renders the sentence from the code plus the lever (parent req 13); authoritative meanings arrive from
   [SAF-35568](https://safebreach.atlassian.net/browse/SAF-35568), which this therefore **depends on** rather
   than merely anticipating. See §9 for what that trade costs.
2. **A new low-level fetch function** that performs the HTTP call, exposes **every** query parameter, and
   returns the **raw, null-safe** per-step response — including the `simulators` union map and
   `isLimitReached`, both of which the current helper never even extracts.
3. **`_get_scenario_statistics` refactored into a thin summariser** over that fetch function, preserving its
   current return contract **byte-for-byte**.
4. **A new public function + registered tool** `get_plan_statistics` (`readOnlyHint=True`) that returns raw
   counts plus translated constraints and a zero-impact report.

The decisive constraint on this shape is **F16**: `_get_scenario_statistics` is referenced **58 times** in
`safebreach_mcp_studio/tests/test_studio_functions.py` (a 10 228-line file), the majority as
`@patch(..., return_value=[...])` decorators carrying hardcoded dicts in its present summary shape. Changing
that shape would force ~20+ mechanical decorator edits whose diff noise could easily mask a real regression.
Layering instead of rewriting satisfies AC-6 (exactly one path to `plan/statistics`) at near-zero regression
cost, and it cleanly isolates the `includeDisabled` correction: the new tool defaults to `false` (runnable),
while the summariser keeps passing `true` **explicitly**, so `quick_run` / `run_scenario` previews are
unchanged by default and correcting them becomes a separate, deliberate decision rather than a side effect.

### Alternatives considered

| Alternative | Pros | Cons | Verdict |
|---|---|---|---|
| **Rewrite `_get_scenario_statistics` to return the rich shape and adapt its callers** | One function, no layering; the two callers immediately gain correct runnable counts. | Forces ~20+ hardcoded `@patch` return-value edits across 58 references; silently changes numbers two shipped tools already report (R2); the diff hides regressions. | **Rejected** — cost and risk both land on existing shipped behaviour for no benefit to this subtask's ACs. |
| **New tool as a wholly separate code path, leaving the helper untouched** | Zero regression risk; smallest diff. | Directly violates **AC-6** — two independent paths to the same endpoint, which is exactly what parent req 6 forbids. Translation-table drift would then differ per path. | **Rejected** — violates an acceptance criterion. |
| **Always issue both calls (expected + runnable)** | Fully satisfies parent req 13's "both figures" with no caller decision. | Two round trips on **every** call against an endpoint given a 120 s timeout, with `getAllConstraints=true` already disabling the validator short-circuit (R5). Helm re-checks after *every* changed decision (AC-11). | **Rejected** by user decision D2 — runnable default, second call only on explicit request. |
| **Derive expected counts client-side from a runnable response** | One call, both numbers. | **Impossible.** `includeDisabled=false` filters disabled simulators out of the counts entirely (F2, `plan_statistics.js:65-66`); the information is not in the response. | **Rejected** — not implementable. |
| **Generate the translation table at runtime from `constraints.js`** | Never drifts from upstream. | `orchestrator` is not a dependency of `safebreach-mcp`, and the file is JavaScript. Would add a cross-repo build-time coupling to a differently-cadenced release. | **Rejected** — vendor statically, guard with a coverage test (D4). |
| **Describe only the ~20 codes whose plain reading misleads, and let a model infer the rest** | Smallest artifact; less to rot on an upstream rewording. | Rests on the other ~68 being self-describing, which is **false**. The `*_is_ignored` family reads as a benign note and in fact eliminates the node (`aws_validation.js:96-101`). Deciding per-code which names can be trusted is an unbounded judgement, and the failure mode is a *confidently wrong* explanation. | **Rejected** — but so was describing all 88; see the next two rows. |
| **Vendor a description for all 88, authored from their emit sites** | SAF-35508 ships self-sufficient; fixes the live raw-code leak immediately; no dependency on another team. | It is the largest authoring effort in the plan and **entirely throwaway** once SAF-35568 serves descriptions. Worse, it is a pressure-release valve: `ui-react` has carried an "interim" copy of this vocabulary for years — 57 real entries, 3 dead, 31 missing — precisely because vendoring removed the incentive to fix the API. A third copy would do the same. | **Rejected** — deleting is the only option that keeps the forcing function on SAF-35568. |
| **Delete the table; keep only the fix-lever map** | MCP stops owning meanings it is not the source of. No throwaway authoring, no third copy, no risk of asserting a wrong meaning. Preserves the pressure for SAF-35568 to land. | SAF-35508 can no longer satisfy AC-7/AC-8's description half alone, so **SAF-35568 becomes a dependency** with its localization question on Stage 1's path; and the 14 codes that carry correct descriptions today lose them, which is a visible regression for `quick_run` / `run_scenario`. | **Chosen.** The costs are real and are recorded in §9 (R7, R9) rather than papered over. |
| **Classify each code as `elimination` vs `informational`** (a `kind` field) | Would let a consumer drop benign notes rather than report them as problems. | **No such class exists.** Every one of the 88 sets `valid = false` and the node is never pushed to `filteredNodes` — verified in `aws_validation.js:96-101` and `gcp_validation.js:77-81`. The apparent "informational" family is variant-level de-duplication, and the effect it was meant to capture is already covered by severity derived from the counts: a variant elimination on an attack that still runs is `reducing`. | **Rejected — premise was wrong.** No vocabulary metadata is needed for severity. |
| **Keep `fix_lever` MCP-side permanently** | Core has no `step_overrides` parameter. | `step_overrides` is only MCP's wrapper over `attackerFilter` / `targetFilter`, which are **Core's own `ValidatePlan` fields**, and `os`/`role`/`simulators`/`connection` are fields in Core's `simulatorsFilter` schema. The lever is expressible in Core's vocabulary, and the console needs the identical knowledge. | **Rejected** — SAF-35568 asks the API for it too; only the snake_case rename onto MCP's JSON shape stays here. |
| **Have the orchestrator API serve the catalog** | Single source of truth; a new code is described in the same commit that adds it; retires ui-react's duplicate table too. | Cross-team, multi-repo change on another release cadence — it would block a Stage 1 subtask scoped as "promote an existing helper", and the description half carries an unresolved localization question. | **Right long-term direction, filed as SAF-35568.** Adopting the normalized catalog shape now makes that migration a drop-in with **no response-contract change**. |

### Decision rationale

The chosen shape is the only one that satisfies AC-6 without paying R2's regression cost, and it makes each
correctness fix independently reviewable. Naming (`get_plan_statistics`), the runnable default, and the
read-only/deferral posture are user decisions **D1–D3**, recorded in `context.md`.

---

## 3. Core Feature Components

### Component A — Delete the translation table; add a fix-lever map (`CONSTRAINT_FIX_LEVERS`)

**Purpose**: Remove `CONSTRAINT_REASON_DESCRIPTIONS` (`studio_functions.py:2225`) outright and replace it with
a map of the one fact MCP is genuinely the right owner of. Satisfies AC-7; AC-8's description half moves to
SAF-35568.

**Why delete rather than extend.** MCP is not the source of truth for what a constraint code means —
`orchestrator` is. Vendoring a meaning here creates a third copy of one vocabulary, and the evidence that this
does not stay "interim" is direct: `ui-react` has carried its copy for years and it has drifted both ways (57
real entries, 3 dead, 31 missing, 4 commented out). A vendored table is a pressure-release valve — it removes
the incentive to fix the API. Deleting keeps that incentive, and it means MCP can never assert a meaning that
is wrong.

**What remains: `CONSTRAINT_FIX_LEVERS`**
- One entry per distinct emitted reason code, giving the control surface that resolves it, from a closed enum:
  `target_filter.os`, `attacker_filter.role`, `*_filter.simulators`, `*_filter.connection`,
  `console.simulator_approval`, `console.license`, `console.advanced_actions`, `step.parameters`, or `null`
  for intrinsic incompatibility.
- This is the fact a calling model **cannot** infer, and the reason it cannot is that the remedy diverges
  sharply between similar-looking codes: `incompatible_os` is a step filter, `simulator_is_offline` is a
  console action, `move_does_not_meets_license_requirements` is a licence. A closed enum is also testable in a
  way free-text prose is not, and it is cheap — largely patternable by validator family.
- **Naming**: snake_case, to match `step_overrides`. SAF-35568 will serve the same levers in Core's camelCase
  schema vocabulary (`attackerFilter.role`, `console.simulatorApproval`), so that migration includes a
  mechanical rename — see §10.
- **No `description` field, for any code.** Not for the 74 currently untranslated, and not for the 14 that
  have one today — those are deleted too, so the output is uniform rather than 14 special cases. Helm renders
  from the code plus the lever until SAF-35568 supplies authoritative meanings.
- **No `kind` field.** All 88 codes eliminate the node: every one sets `valid = false`, after which the node is
  never pushed to `filteredNodes` (`aws_validation.js:96-101`, `gcp_validation.js:77-81`). The `*_is_ignored`
  and `ignoring_*_variant` families are variant-level de-duplication, not benign notes. An earlier draft
  asserted a 72/16 `elimination`/`informational` split; it was inferred from code names and is **wrong**.
- **Keyed on emitted values, not source keys.** The source file has **87 distinct keys but 88 distinct
  values**, and two entries emit a value differing from their key —
  `some_cloned_advanced_actions_are_disabled` → **`some_duplicate_advanced_actions_are_disabled`**, and
  `move_does_not_require_location_simulator_location_is_ignored` (web-application group) →
  **`move_does_not_require_url_simulator_url_is_ignored`**. A key-derived map would ship two levers for codes
  that can never occur while missing the two that do — and a naive coverage test would still report 88/88.
  Two codes are also **shared across groups** (`incompatible_framework_version`), so an entry must not assume
  a single owning validator group.
- **Fail-safe default**: an unrecognised code — one added upstream after this ticket — resolves to
  `fix_lever: null` and is still surfaced as a conflict. Never dropped, never given an invented meaning.

**Blocker-ness is contextual and needs no vocabulary metadata.** A reason lives at `[simulatorId][moveId]` and
eliminates one node variant for one attack. An attack usually has several candidates, and `moves[id]` is
pre-seeded to 0 then incremented per survivor (F5), so nine of ten eliminated still yields a running attack.
Severity therefore falls straight out of the counts — see Component D — which is what makes a variant
de-duplication read as low-priority (`reducing`) without anyone classifying it.

**`unable_to_validate` is not a concern.** `validation_type.js` carries a third outcome, but it is returned
only from a catch block on the *generation* path (`sbGenerator/validators/index.js:60`), while
`simulatorConstraints` is populated exclusively by `StatisticsAggregator.addConstraintBySimulator` with reasons
from `constraints.js`. It is a separate return channel and cannot appear as a reason code.

### Component B — Raw fetch core (`_fetch_plan_statistics`)

**Purpose**: New private function; the single point at which `plan/statistics` is called. Satisfies AC-1,
AC-2, AC-5 and AC-6.

**Key features**
- Accepts a **plan body** (ad-hoc, no saved scenario needed) or a `scenario_id`. Per F1 the endpoint natively
  resolves a saved plan when the body carries `id` or `testId` (`plan_statistics.js:51-53`), so `scenario_id`
  is a **passthrough** as `{id: ...}` — no client-side resolution. `planId` is present in the `ValidatePlan`
  schema but is **not** honoured by the controller and must not be used.
- `ValidatePlan` requires only `name`; an ad-hoc body uses `""` as the existing helper does.
- Exposes all five query parameters — `limit`, `includeDisabled`, `getConstraints`, `getAllConstraints`,
  `useCache` — with documented defaults (§4).
- Returns the response **unreduced**: `simulationCount`, `moves`, `simulators`, `attackerSimulators`,
  `targetSimulators`, `simulatorConstraints`, `isLimitReached`.
- **Null-safe throughout.** Never compares a count with `>` or negates it for sorting without first
  establishing it is an integer. This is the live `TypeError` fix (F17): the current helper's
  `sum(1 for v in ... if v > 0)` and `sorted(moves.items(), key=lambda x: -x[1])` both crash on the `None`
  values a limit-reached response returns.
- **Preserves `null` vs `0`.** `null` means *not computed*; `0` means *in scope, runs nowhere*. It does not
  default a missing `simulationCount` to `0` — the present helper's `s.get('simulationCount', 0)` collapses
  exactly this distinction.
- **Reports truncation.** On a limit-reached response the controller pushes a sentinel step and returns
  early, so the returned step list is **shorter than the plan's** (F6). The function reports the plan's step
  count, the returned count, and an explicit truncation flag.
- **No MCP-side caching** — see §6.

### Component C — Contract-preserving summariser (`_get_scenario_statistics`)

**Purpose**: Modification. Becomes a thin adapter over Component B while keeping its observable contract
identical, so `sb_quick_run` (`:2737`), `sb_run_scenario` (`:2958`) and all 58 test references keep working.

**Key features**
- Same signature, same return shape, same key names (`matchedTargetSimulators`, `matchedAttacks`, …).
- Passes `includeDisabled=true` and `limit=500000` **explicitly**, so today's numbers are reproduced exactly
  rather than inherited from a default that has since changed.
- Gains null-safety and limit-reached survival for free from Component B — a latent crash fix for the two
  shipped tools.
- Its constraint summarisers (`_summarize_constraints` :2299, `_summarize_constraints_aggregated` :2350)
  switch to `CONSTRAINT_REASONS`, so both existing tools inherit 88/88 coverage and the safe fallback.

### Component D — Public tool (`get_plan_statistics`)

**Purpose**: New public function plus tool registration in `studio_server.py`. Satisfies AC-3, AC-12, and the
reporting half of the zero-impact rules.

**Key features**
- Registered `readOnlyHint=True, destructiveHint=False`. Per **F13** this follows an established in-server
  pattern — `studio_server.py` already registers four read-only tools (`validate_studio_code`,
  `get_all_studio_attacks`, `get_studio_attack_source`, `get_studio_attack_latest_result`) — correcting an
  earlier note that claimed this would be the server's first.
- Being read-only, it takes **no rate-limiting gates**; the `check_limit` / `record_action` contract in
  CLAUDE.md applies only to `readOnlyHint=False` tools.
- **Counts mode** (D2): returns **runnable** counts by default (`include_disabled=False`). Setting
  `include_disabled=True` returns expected counts. A `both` mode issues both calls and labels each result,
  and the response documents that expected cannot be derived from a runnable response.
- **Zero-impact reporting** — the read-only half of the hard-failure rules. Per-step lists of attacks whose
  count is genuinely `0` and simulators whose count is genuinely `0`, each carrying its **`blockers`** — by
  construction the `severity: blocking` subset. A `reducing` conflict therefore **cannot** be offered as the
  reason something runs nowhere; the guarantee is derived from the counts rather than statically asserted.
  Two further correctness rules:
  - Simulators are read from the **union `simulators` map**, never a single role map — a node present on only
    one side is `undefined` in the other, never `0` (F5). The current helper never extracts this map at all.
  - An entry is reported **only** when its value is an integer `0`. `None` never qualifies.
  - When the response is limit-reached, zero-impact reporting is **suppressed entirely** and the truncation is
    surfaced instead.
- **Normalized conflicts — a catalog plus references.** The response carries a top-level
  `constraint_catalog` holding one entry per code **actually present in this response** (each entry carrying
  its `fix_lever`; no `description`, per Component A) (so it stays small,
  typically a handful rather than 88), and each per-conflict entry references it by `code`, carrying only what
  varies: the computed `severity`, `attack_id`, `side`, `simulator_count`, and the API's own `values` detail
  (which genuinely differs per simulator — `required: WINDOWS, actual: LINUX` versus `actual: MAC`).
  This matters for two reasons beyond payload size. It makes a single code's **contextual** severity legible
  without contradiction — the same `incompatible_os` can be `blocking` for one attack and `reducing` for
  another, because the static and contextual halves now live in different places. And it makes the eventual
  migration to an API-served catalog (§10) a **drop-in with no response-contract change** — only where MCP
  fills the catalog from.
- **Computed `severity` per conflict**, derived from the counts alone: `blocking` when the attack's count is
  an integer `0`, `reducing` when the attack still runs (on fewer simulators than offered). No vocabulary
  metadata is consulted. This ticket **acts on** `blocking` only —
  partial-impact and fail-rate conflicts are explicitly SAF-35484's scope — but it **reports** `reducing`,
  which is the honest answer to "why is this number lower than I expected?". Keeping them in separate buckets
  is what stops Story 2 from having to re-plumb the response.
- **Conflicts are grouped by `(attack_id, code)`, never exploded per simulator.** With
  `getAllConstraints=true` the raw structure is `[simulatorId][moveId] → [reasons]`; a step with 50 simulators
  × 100 attacks × 3 reasons is 15 000 leaves. Grouping collapses that to roughly attacks × distinct codes,
  carrying `simulator_count` plus a capped `simulator_ids` sample. Without this the tool is unusable on a real
  console at exactly the moment it matters most.
- A **`conflict_detail`** parameter controls verbosity — `summary` (default; grouped by code with counts),
  `per_attack`, or `full` (adds simulator id lists). This mirrors the existing helper's
  `constraint_summary` / `constraint_summary_aggregated` split rather than inventing a new axis.
- The constraint map is **sparse** — `removeEmptySimulatorConstraints()` prunes empty leaves and then any
  simulator with no constraints, so an absent simulator means "no constraints", not "not evaluated" (F3). It
  must never be iterated as if dense. The leaf is an **array**: one (simulator, attack) pair can carry several
  reasons, and with `getAllConstraints=true` it usually will.
- **`hint_to_agent`** on the ambiguous cases: limit-reached truncation, an empty-steps rejection, and the
  expected-vs-runnable distinction when only one figure was requested.

---

## 4. API Endpoints and Integration

### Existing API consumed

- **API Name**: Get plan statistics (Core impact & validation engine)
- **URL**: `POST {orchestrator}/api/orch/v1/accounts/{account_id}/plan/statistics`
- **Headers**: `Content-Type: application/json`, plus console auth headers from
  `get_auth_headers_for_console(console)`
- **Source repository**: `orchestrator` — controller `src/server/controllers/plan_statistics.js`,
  `operationId: getPlanStatistics`. **Read-only reference; no orchestrator change is required or intended.**
- **Console wrapper for parity**: `getPlanStatistics(plan, limit, includeDisabled, getConstraints, abortable)`
  — `ui-react/src/actions/execution.tsx:615`
- **Timeout**: 120 s (matches the existing helper)

**Query parameters** — swagger default, tool default, and what each actually controls:

| Param | Swagger default | Tool default | What it controls |
|---|---|---|---|
| `includeDisabled` | `false` | **`false`** (runnable) | Selects *which question is asked*, not a tuning knob. `true` counts disabled simulators **and** empties `offlineNodes`, so `simulator_is_offline` is **never emitted** — the *expected* number. `false` excludes them from counts but still reports each one with that reason — the *runnable* number plus the explanation. Also governs **unapproved** simulators, since `node.isEnabled` is `isConnected && approved`. |
| `getConstraints` | `false` | **`true`** | Populates `simulatorConstraints`; without it the key is **absent entirely**. Required for AC-7/AC-8 to mean anything. |
| `getAllConstraints` | `false` | **`true`** | A **completeness** flag, not a grouping key (its swagger description is stale). `false` chains validators so a simulator records only the *first* reason that eliminated it; `true` runs every validator against the full node set so it records *all* of them, and enables two extra emitters. Console parity. |
| `limit` | `0` | **`500000`** | Console parity (`PLAN_SIMULATIONS_STATISTICS_LIMIT`). Compared against the **rendered-move** count, not the simulation count. `0` disables the circuit breaker entirely — and with it the limit-reached path. |
| `useCache` | `true` | **`true`** | Server-side cache. Never sent by the current helper. |

**Request body**: a `ValidatePlan`. Only `name` is required. Per-step scoping via `attacksFilter`,
`attackerFilter` / `targetFilter` (`simulatorsFilter`), `systemFilter`, `successCriteria`, and `draft: true`
for Studio draft custom attacks.

**Response**: `{ data: { steps: StepStatistics[] } }`. `StepStatistics` requires `simulationCount`, `moves`,
`simulators`, `targetSimulators`, `attackerSimulators`; `isLimitReached` and `simulatorConstraints` are
optional. The four maps are declared bare `"type": "object"` with no `properties` — untyped at the source.

```
simulatorConstraints = {
  attackerConstraints: { [simulatorNodeId]: { [moveId]: [ {reason, values?}, ... ] } },
  targetConstraints:   { [simulatorNodeId]: { [moveId]: [ {reason, values?}, ... ] } },
}
```

**Error responses**

| Status | Meaning | Tool behaviour |
|---|---|---|
| `400 NOT_ALLOWED` | "Can not get statistics for plans with no steps" — a **normal** state while Helm is still building a plan. | Typed, explanatory error naming the missing `steps`, not an unhandled 400 (AC-1). |
| `401` / `403` | Auth / RBAC | Existing `check_rbac_response` handling. |
| `500` | Also raised as `SafeBreachOperationNotSupported` when a step carries `systemFilter.simulations.values` and the simulators filter operator is not `is` (F7 — the per-constraint merge path for single-simulation re-runs). | Full response body propagated in the error message. |

**New APIs to create**: none.

### Tool response shape (normalized catalog + references)

Static facts live once in `constraint_catalog`; per-conflict entries carry only what varies. Illustrative,
`counts_mode: runnable`, `conflict_detail: summary`:

```json
{
  "counts_mode": "runnable",
  "plan_step_count": 2,
  "returned_step_count": 2,
  "truncated": false,
  "params_used": { "includeDisabled": false, "getConstraints": true,
                   "getAllConstraints": true, "limit": 500000, "useCache": true },
  "constraint_catalog": {
    "incompatible_os":      { "fix_lever": "target_filter.os",      "description": null },
    "incompatible_package": { "fix_lever": "attacker_filter.role",  "description": null },
    "simulator_is_offline": { "fix_lever": "console.simulator_approval", "description": null },
    "move_does_not_require_credentials_simulator_credentials_is_ignored":
                            { "fix_lever": null,                    "description": null }
  },
  "steps": [
    { "step_index": 0,
      "simulation_count": 420,
      "counts_computed": true,
      "attacks":             { "1234": 240, "5678": 180, "9012": 0 },
      "simulators":          { "a1b2": 2, "c3d4": 2, "e5f6": 0 },
      "attacker_simulators": { "a1b2": 2 },
      "target_simulators":   { "c3d4": 2, "e5f6": 0 },
      "zero_impact_attacks": [
        { "attack_id": "9012", "attack_name": "Write EICAR to disk",
          "blockers": [ { "code": "incompatible_os", "side": ["target"], "simulator_count": 3,
                          "values": { "required": "WINDOWS", "actual": "LINUX" } } ] }
      ],
      "zero_impact_simulators": [
        { "simulator_id": "e5f6", "simulator_name": "lab-linux-02",
          "blockers": [ { "code": "simulator_is_offline", "side": ["target"], "simulator_count": 1 } ] }
      ],
      "conflicts": [
        { "code": "incompatible_os", "severity": "blocking", "attack_id": "9012",
          "side": ["target"], "simulator_count": 3,
          "values": { "required": "WINDOWS", "actual": "LINUX" } },
        { "code": "incompatible_os", "severity": "reducing", "attack_id": "1234",
          "side": ["target"], "simulator_count": 1,
          "values": { "required": "WINDOWS", "actual": "MAC" } },
        { "code": "move_does_not_require_credentials_simulator_credentials_is_ignored",
          "severity": "none", "attack_id": "1234", "side": ["attacker"], "simulator_count": 1 }
      ] }
  ],
  "hint_to_agent": "..."
}
```

Note `incompatible_os` appearing as both `blocking` (attack 9012, count 0) and `reducing` (attack 1234,
count 240) with no contradiction — the static half is in the catalog, the contextual half on the conflict.

`description` is present but **always `null`** until SAF-35568 lands. The key is emitted deliberately rather
than omitted: it tells a caller that a meaning slot exists and is unfilled, so "not supplied" is
distinguishable from "described as empty", and the field becomes populated by the migration without a shape
change.

**Limit-reached variant** — must never be mistaken for "nothing runs":

```json
{
  "plan_step_count": 3, "returned_step_count": 1, "truncated": true,
  "constraint_catalog": {},
  "steps": [
    { "step_index": 0, "simulation_count": null, "counts_computed": false, "is_limit_reached": true,
      "attacks": { "1234": null, "5678": null },
      "simulators": {}, "attacker_simulators": {}, "target_simulators": {},
      "zero_impact_attacks": [], "zero_impact_simulators": [], "conflicts": [] }
  ],
  "hint_to_agent": "Core hit its evaluation limit and stopped early: 1 of 3 steps returned, no counts computed. null means not-computed, NOT zero — nothing here indicates any attack or simulator is inapplicable."
}
```

Both zero-impact lists are empty **by construction** when `counts_computed` is false. Compare with step 0
above: an identical-looking "nothing will run", opposite meaning. Conflating the two is risk R1.

---

## 6. Non-Functional Requirements

**Code reuse**
- Reuses `get_api_base_url(console, 'orchestrator')`, `get_api_account_id(console)`,
  `get_auth_headers_for_console(console)`, `check_rbac_response(response)`.
- Attack-name resolution reuses `_build_attack_name_map(console)` (:2286), which reads the playbook cache via
  `_get_all_attacks_from_cache_or_api`. Names are cosmetic — that helper already degrades to `{}` on failure.
- The vendored table lives in `safebreach_mcp_studio` alongside its only consumers rather than in
  `safebreach_mcp_core`; nothing outside the studio server reads constraint reasons.

**Performance**
- `getAllConstraints=true` disables the validator short-circuit, so full explanation coverage is measurably
  more expensive than a plain count (R5). It is the console's own setting and remains overridable.
- The runnable default costs **one** HTTP call. The expected figure costs a second, issued only on request.

**Caching — deliberately none, MCP-side**
CLAUDE.md's per-server caching pattern is **not** applied to this tool. AC-11 requires that any change to an
earlier decision trigger a fresh call, and Helm's whole usage pattern is re-scoring a configuration that just
changed. An MCP-side TTL cache would serve stale impact numbers for a configuration the user has already
edited — the precise failure this tool exists to prevent. Freshness control stays with the server-side
`useCache` parameter, which the caller can now actually set.

**Backward compatibility**
- `_get_scenario_statistics` keeps its exact contract; `sb_quick_run` and `sb_run_scenario` are behaviourally
  unchanged by default (§2, R2).
- `CONSTRAINT_REASON_DESCRIPTIONS` is superseded by `CONSTRAINT_CATALOG`. The 14 existing description strings
  are preserved wherever they survive into the ~20 corrective descriptions, so both existing tools' output
  gains a verified `description` and a `fix_lever` without losing wording they already display. Only `_summarize_constraints` reads the
  table directly (`:2333`, `:2334`); `_summarize_constraints_aggregated` inherits via `:2357`.

**Observability**
Follows the module's existing `logger` usage: one info line per call with step count, console, and the
parameter set actually used, and an error line carrying the full response body on failure.

---

## 7. Definition of Done

**Core functionality**
- [ ] `get_plan_statistics` evaluates an **ad-hoc plan body** with no saved scenario. *(AC-1)*
- [ ] It also accepts a `scenario_id`, passed to Core as `{id}` rather than resolved client-side. *(AC-1)*
- [ ] A plan with no steps surfaces a typed, explanatory error rather than an unhandled 400. *(AC-1)*
- [ ] The response surfaces per-step `simulationCount`, per-attack `moves`, and per-simulator `simulators`,
      `attackerSimulators` and `targetSimulators` counts, plus `isLimitReached` and structured constraints. *(AC-2)*
- [ ] `limit`, `includeDisabled`, `getConstraints`, `getAllConstraints` and `useCache` are all pass-through
      with the documented defaults in §4. *(AC-2)*
- [ ] Runnable counts are returned by default (`includeDisabled=false`); expected counts are available; a
      both-counts mode issues both calls and labels each result; the response states that expected cannot be
      derived from a runnable response. *(AC-3)*
- [ ] Numbers match the console per view and per parameter set — Add Simulators Checkout tab with
      `includeDisabled=true, getConstraints=true`, and run gating with `includeDisabled=false`. *(AC-4)*
- [ ] When `isLimitReached` is true the tool reports it explicitly, preserves `null` (not computed) versus `0`
      (runs nowhere), surfaces that the returned step list is shorter than the plan's, and performs no
      zero-impact reporting. *(AC-5)*
- [ ] `plan/statistics` is called from exactly one place in the repo; `_get_scenario_statistics` and its two
      callers route through it rather than forming a parallel implementation. *(AC-6)*
- [ ] `CONSTRAINT_REASON_DESCRIPTIONS` is **deleted**, including its 14 existing entries. No constraint
      meaning is vendored in this repo. *(AC-7)*
- [ ] All **88** emitted reason codes carry a `fix_lever` from the closed enum, keyed on the codes the API
      emits — including the two whose emitted value differs from their source key. A test fails if any
      emitted code lacks a lever. *(AC-7)*
- [ ] No `description` is fabricated for any code. Authoritative meanings are SAF-35568's deliverable; until
      it lands, the response carries the code and its lever and the caller renders. *(AC-7, §9 R9)*
- [ ] Conflicts are returned **normalized** — a `constraint_catalog` of the codes present in the response, plus
      per-conflict references carrying only `severity`, `attack_id`, `side`, `simulator_count` and `values`. *(AC-8)*
- [ ] `severity` is **computed** from the counts alone — `blocking` when the attack's count is an integer `0`,
      `reducing` when it still runs — consulting no vocabulary metadata. *(AC-8)*
- [ ] Every conflict is surfaced — an unrecognised code resolves to a null lever and is still reported, never
      dropped and never given an invented meaning. *(AC-8)*
- [ ] The response marks meanings as **not supplied**, so a caller can tell "no description available" from
      "described as empty" and does not present the bare code as an explanation to a user. *(AC-8, §9 R9)*
- [ ] An attack with `moves[id] === 0` is **reported** as inapplicable with a plain-language explanation of why
      it runs nowhere; reporting does not block save, and a `null` value is never reported as zero-impact. *(AC-9)*
- [ ] A simulator with `simulators[id] === 0` is **reported** the same way, read from the **union** `simulators`
      map rather than a single role map. *(AC-10)*
- [ ] The tool performs no caching of its own, so any change to an earlier decision produces a fresh call. *(AC-11)*
- [ ] Registered as `get_plan_statistics` with `readOnlyHint=True`, and documented in the CLAUDE.md tool
      catalog. The rate-limiting gate table is **not** extended — read-only tools are outside that contract. *(AC-12)*

**Quality gates**
- [ ] Every test in `test-plan.md` for this feature is green, with evidence in `test-results/`.
- [ ] `sb_quick_run` and `sb_run_scenario` are verified behaviourally unchanged.
- [ ] Coverage guard fails when a reason code lacks an entry. *(AC-7)*
- [ ] CLAUDE.md tool catalog updated.

**Deployment readiness**
- [ ] No feature flag, migration, or infrastructure change — additive read-only tool.
- [ ] No orchestrator change.

---

## 8. Implementation Phases

| Phase | Status | Completed | Commit SHA | Notes |
|-------|--------|-----------|------------|-------|
| Phase 1: Vendored constraint vocabulary + safe fallback | ⏳ Pending | - | - | |
| Phase 2: Raw fetch core | ⏳ Pending | - | - | |
| Phase 3: Refactor summariser onto the core | ⏳ Pending | - | - | |
| Phase 4: Translation + zero-impact reporting layer | ⏳ Pending | - | - | |
| Phase 5: Public function + tool registration | ⏳ Pending | - | - | |
| Phase 6: Documentation | ⏳ Pending | - | - | |

### Phase 1 — Delete the translation table; add the fix-lever map

**Semantic change**: Remove the vendored constraint meanings entirely and replace them with a lever map.

**Deliverables**: `CONSTRAINT_REASON_DESCRIPTIONS` deleted; `CONSTRAINT_FIX_LEVERS` added; a resolver that
returns a lever (or `null`) for any code and never a meaning.

**Implementation details**
- **Delete `CONSTRAINT_REASON_DESCRIPTIONS` (`:2225`) outright**, all 14 entries. Do not carry any of them
  forward. The output becomes uniform across all 88 codes rather than 14 special cases, and MCP stops
  asserting meanings it is not the source of.
- Build `CONSTRAINT_FIX_LEVERS` from the **emitted values** of the 21 exported groups in orchestrator's
  `constraints.js`. Enumerate by value, not by key: 87 keys, 88 values, two entries emitting a different
  string than their key (§3 Component A names both). Deduplicate — `incompatible_framework_version` is emitted
  by two groups.
- Assign each code a lever from the closed enum. Largely patternable by validator family, which is what keeps
  88 rows cheap: the `move_requires_X_but_the_simulator_is_missing_X` family is `console.*`; the
  OS/role/connection families map to their corresponding `*_filter.*` lever; the variant de-duplication family
  (`*_is_ignored`, `ignoring_*_variant`) is `null`, since nothing the caller can change affects it. Verify each
  row against its emit site rather than trusting the pattern blindly — the lever is a claim about remedy, and a
  wrong remedy sends someone down a dead end.
- Introduce a resolver used by every consumer. It returns the lever and an explicit `description: null`; on an
  unknown code it returns `fix_lever: null` and still reports the conflict. It **never** returns the code as an
  explanation and never fabricates a meaning. Replaces `...get(code, {}).get('description', code)` at `:2333`.
- **Repoint one function, not two.** `_summarize_constraints` (:2299) is the *only* direct reader — the table is
  referenced at exactly `:2333` and `:2334`, both inside it. `_summarize_constraints_aggregated` (:2350)
  consumes it transitively at `:2357` and inherits the change automatically.
- **This changes shipped output** for the 14 codes that currently carry a description: `quick_run` and
  `run_scenario` previews will report those conflicts without prose. That is a deliberate, accepted regression
  (§9 R9) — not a contract break, since the key set is unchanged and `description` simply becomes `null`.

**What can go wrong**: enumerating by key silently assigns levers to two impossible codes and misses two real
ones, and a key-based coverage test still reports 88/88 — the guard must compare against emitted values.
Assigning a lever from the code's name rather than its emit site produces a confidently wrong remedy; the
`*_is_ignored` family is the trap, since its name suggests a setting the user could change when in fact nothing
can. A resolver that falls through to the code violates AC-8.

**Changes**

| File | Description |
|---|---|
| `safebreach_mcp_studio/studio_functions.py` | Delete `CONSTRAINT_REASON_DESCRIPTIONS` (:2225); add `CONSTRAINT_FIX_LEVERS` + resolver; repoint `_summarize_constraints` (:2333-:2334) |

**Git commit**: `feat(studio): delete vendored constraint descriptions, add fix-lever map`

### Phase 2 — Raw fetch core

**Semantic change**: Introduce the single, fully-parameterised, null-safe call site for `plan/statistics`.

**Deliverables**: `_fetch_plan_statistics`.

**Implementation details**
- **Inputs**: `console`; either a plan body or a `scenario_id`; the five query parameters; nothing else.
- **Body construction**: a caller-supplied body is used as-is, defaulting `name` to `""` when absent. A
  `scenario_id` becomes `{"name": "", "id": <scenario_id>}` — a passthrough, because the controller resolves
  `id` or `testId` itself. Never populate `planId`; the controller ignores it.
- **Steps**: reject a body with no steps **before** the HTTP call, with a typed error explaining that Core
  returns `400 NOT_ALLOWED` for step-less plans and that this is expected mid-construction.
- **Request**: build the URL from all five parameters explicitly — no hardcoded fragments. POST with the
  standard headers and a 120 s timeout, then `check_rbac_response`. On HTTP error, raise carrying the **full
  response body**, not just the status.
- **Outputs**: for each returned step, the six response fields unmodified, plus a per-step flag for whether
  its counts are computed. `simulationCount` is **not** defaulted — absent stays absent, distinct from `0`.
  Top level: the plan's step count, the returned step count, an explicit truncation flag (returned < plan
  count, or any step reports `isLimitReached`), and the parameter set actually used.
- **Null-safety rule**: no comparison or arithmetic on a count without first establishing it is an integer.
  This is the whole `TypeError` class the current helper exhibits.

**What can go wrong**: treating falsy as zero re-introduces the `null`/`0` conflation; assuming the returned
step list aligns positionally with the plan's steps mis-attributes every step's numbers on a truncated
response.

**Changes**

| File | Description |
|---|---|
| `safebreach_mcp_studio/studio_functions.py` | Add `_fetch_plan_statistics` |

**Git commit**: `feat(studio): add null-safe plan statistics fetch core with full parameter passthrough`

### Phase 3 — Refactor the summariser onto the core

**Semantic change**: `_get_scenario_statistics` stops calling HTTP and becomes a summariser over Phase 2.

**Deliverables**: refactored `_get_scenario_statistics` with an unchanged contract.

**Implementation details**
- Keep the signature and every returned key exactly as they are.
- Delegate the call, passing `includeDisabled=true`, `limit=500000`, `useCache` at the server default, and
  `getConstraints`/`getAllConstraints` from `include_constraints` — i.e. today's URL, now stated explicitly
  instead of hardcoded.
- Compute the `matched*` / `total*` aggregates from the raw maps using integer-guarded counting, so a
  limit-reached response yields a defined result instead of raising.
- Sort `resolved_attacks` with a comparator that tolerates non-integer counts.
- This is the only phase that touches shipped behaviour; the intended visible delta is **none**.

**What can go wrong**: any renamed or dropped key breaks ~20 hardcoded `@patch` return values and both
callers. Changing the default `includeDisabled` here — rather than passing `true` explicitly — silently
alters the numbers two shipped tools report.

**Changes**

| File | Description |
|---|---|
| `safebreach_mcp_studio/studio_functions.py` | Rewrite `_get_scenario_statistics` (:2400) body onto `_fetch_plan_statistics` |

**Git commit**: `refactor(studio): route _get_scenario_statistics through the fetch core`

### Phase 4 — Translation + zero-impact reporting layer

**Semantic change**: Turn a raw statistics response into the caller-facing report.

**Deliverables**: a per-step shaping function producing translated constraints and zero-impact lists.

**Implementation details**
- **Normalize conflicts**: walk `attackerConstraints` and `targetConstraints` treating the map as **sparse**
  and each leaf as an **array**. Group by `(attack_id, code)`, merging the two sides and recording which
  side(s) and how many simulators produced each — never one row per simulator. Emit a `constraint_catalog`
  containing one entry per code **present in this response**, resolved through Phase 1's resolver; each
  conflict references the catalog by `code` and carries only `severity`, `attack_id`, `side`,
  `simulator_count` and the API's `values`. Attach attack names where resolvable, degrading silently.
- **Compute `severity`** per conflict from the attack's own count alone: `blocking` when
  `attacks[attack_id]` is an integer `0`, `reducing` when it is a positive integer. No catalog lookup is
  involved — the same code is legitimately `blocking` for one attack and `reducing` for another in the same
  step, which is also why a variant de-duplication reads as low-priority without being classified.
- **`conflict_detail`**: `summary` (default) groups by code with counts; `per_attack` keys by
  `(attack, code)`; `full` adds a capped `simulator_ids` sample. The default must stay cheap.
- **Zero-impact attacks**: entries of `attacks` whose value is an integer `0`, each carrying its `blockers` —
  the `severity: blocking` subset only. A `reducing` conflict can never appear here.
- **Zero-impact simulators**: entries of the **union `simulators`** map whose value is an integer `0`. Do not
  read the role maps for this — a node on one side only is `undefined` in the other, never `0`.
- **Suppression**: when the step's counts are not computed (limit-reached), emit **no** zero-impact lists, no
  conflicts and an empty catalog, and set the truncation explanation instead. This is the R1 guard.
- **Hints**: emit `hint_to_agent` for truncation, and — when only one counts mode was requested — for the
  expected-versus-runnable distinction.

**What can go wrong**: a dense iteration over the sparse constraint map fabricates absent simulators; reading
only the first element of a constraint array drops most reasons under `getAllConstraints=true`; a falsy test
instead of an integer-`0` test reports the whole selection as zero-impact on a truncated response; asserting
severity statically per code mislabels every `reducing` conflict as a blocker, which would drag SAF-35484's
partial-impact scope into this ticket by accident; and exploding conflicts per simulator makes the response
unusable on a real console.

**Changes**

| File | Description |
|---|---|
| `safebreach_mcp_studio/studio_functions.py` | Add the shaping/reporting helpers |
| `safebreach_mcp_studio/studio_types.py` | Response typing for the new shape |

**Git commit**: `feat(studio): add translated constraint and zero-impact reporting layer`

### Phase 5 — Public function + tool registration

**Semantic change**: Expose the capability as a registered read-only MCP tool.

**Deliverables**: `sb_get_plan_statistics` and the `get_plan_statistics` registration.

**Implementation details**
- **Parameters**: `console`; `plan` (JSON string, ad-hoc body) and `scenario_id` as mutually exclusive
  alternatives, with a clear error when both or neither is given; `include_disabled`; a both-counts flag;
  `get_constraints`; `get_all_constraints`; `limit`; `use_cache`.
- **Counts mode**: default runnable. Expected when `include_disabled` is set. When both are requested, issue
  two calls and return both, each labelled, plus the note that expected is not derivable from runnable.
- **Registration** in `studio_server.py` following the existing 12-tool pattern —
  `@self.mcp.tool(name="get_plan_statistics", annotations=ToolAnnotations(readOnlyHint=True,
  destructiveHint=False), description=...)`, wire name without the `sb_` prefix. **No** rate-limiting gates.
- The description must tell a calling model the three things that are counter-intuitive: `includeDisabled`
  selects expected-versus-runnable rather than merely widening a set; the tool reports zero-impact entities
  but removes nothing; and a limit-reached response means counts were not computed, not that nothing runs.

**What can go wrong**: adding rate-limiting gates to a read-only tool contradicts the CLAUDE.md contract;
a description that omits the `includeDisabled` inversion invites the caller to reproduce the very defect
being fixed.

**Changes**

| File | Description |
|---|---|
| `safebreach_mcp_studio/studio_functions.py` | Add `sb_get_plan_statistics` |
| `safebreach_mcp_studio/studio_server.py` | Register `get_plan_statistics` |

**Git commit**: `feat(studio): add get_plan_statistics read-only MCP tool`

### Phase 6 — Documentation

**Semantic change**: Record the new tool in the project's tool catalog.

**Implementation details**: add `get_plan_statistics` to the Studio Server section of the CLAUDE.md tool
catalog, documenting the runnable default, the `includeDisabled` inversion, the no-MCP-cache decision, and the
report-not-remove posture. State explicitly that the rate-limiting table is unchanged because the tool is
read-only.

**Changes**

| File | Description |
|---|---|
| `CLAUDE.md` | Tool catalog entry |

**Git commit**: `docs: document get_plan_statistics tool`

---

## 9. Risks and Assumptions

### Technical risks

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| **R1** | **Misreading a limit-reached response.** The controller returns a sentinel step with `simulationCount: null` and **every** `moves[id] = null`, and returns early so the step list is shorter than the plan's. Treating falsy as zero, or assuming positional alignment, would report the user's entire selection as zero-impact. | **High** | Integer-`0` predicate everywhere; zero-impact reporting suppressed entirely when counts are not computed; truncation reported explicitly (AC-5). Severity is reduced from the original ticket by D3 — the tool now only *reports*, so the worst case is a wrong report rather than a destroyed configuration. |
| **R2** | **Regressing the two existing callers.** 58 test references, ~20 with hardcoded `@patch` return values, plus `sb_quick_run` and `sb_run_scenario`. | **High** | Contract-preserving layering (§2); `includeDisabled=true` and `limit=500000` passed explicitly in Phase 3; Phase 3's intended visible delta is zero. |
| **R3** | **Vendored-catalog drift — measured, not hypothetical.** The vocabulary lives in `orchestrator`, on a different release cadence. The console has been vendoring the same vocabulary for years in `ui-react/src/containers/Studio/utils/constants.ts:166` and has demonstrably drifted **in both directions**: **3 dead entries** for codes orchestrator no longer emits (`incompatible_simulator_version`, `assume_role_incompatible_simulator_version`, `move_does_not_support_simulation_user_and_simulator_does_not_allows_default_system_user`), and **31 of 88 codes** it cannot translate at all, plus 4 explicitly commented out. This PRD deliberately does **not** add a third copy. | **Low** (was Medium-High) | Largely eliminated by deleting the table: MCP vendors no meanings, so there is no meaning to drift. What remains vendored is the lever map, which is smaller, and the drift test (T-5) plus the coverage guard (AC-7) cover it. The residual risk moves to R9 — meanings are now *absent* until SAF-35568 rather than *stale*. |
| **R4** | **"Matches the console" is not one number.** Checkout uses `includeDisabled=true`, run gating `false`. | **Medium** | AC-4 is per-view and per-parameter-set; §4 tabulates which parameters correspond to which view. |
| **R5** | **Cost of correctness.** `getAllConstraints=true` disables the validator short-circuit; both figures need two round trips, against a 120 s timeout. | **Medium** | Runnable default is one call; the second is opt-in (D2); every parameter is overridable for a cheap count-only call. |
| **R6** | **Vendoring by key rather than by value** ships two impossible codes, misses two real ones, and passes a naive coverage test. | **Medium** | Called out explicitly in §3 Component A and Phase 1; the guard compares against emitted values (T-2). |
| **R7** | **Levers assigned from code names rather than emit sites.** No descriptions are authored any more, but the same trap applies to the lever: `*_is_ignored` reads like a setting the user could change, when in fact it is variant de-duplication and nothing the caller controls affects it. A wrong lever sends someone down a dead end. | **Medium** | Phase 1 requires each lever traced to the branch that emits the code, and the variant-de-duplication family is `null` by rule. The console shows the same trap in production — it renders that one family three inconsistent ways ("… are not supported" / "… are ignored" / "Select a non-service account"), so this is an observed failure mode. Severity is lower than the description version: a null-or-wrong lever costs a wasted attempt, not a false belief about what happened. |
| **R8** | **Asserting severity per code** instead of computing it from the attack's count would label every `reducing` conflict a blocker — pulling SAF-35484's partial-impact scope into this ticket by accident and over-reporting zero-impact attacks. | **Medium** | Severity is derived in Phase 4 from `attacks[attack_id]` alone; the catalog holds no severity-like field to be tempted by. Covered by a test asserting the same code resolves `blocking` and `reducing` within one step. |

| **R9** | **Meanings are absent until SAF-35568 lands.** Deleting the table removes the 14 descriptions two shipped tools display today, and leaves all 88 codes without a vendored meaning. A caller renders from the code — and the code names mislead (`incompatible_package` is a *role* mismatch; `*_is_ignored` is variant de-duplication). So for the codes that matter most, the rendered explanation may be wrong until the API supplies one. | **Medium-High** | Accepted deliberately (§2 alternatives): vendoring is a pressure-release valve and `ui-react` proves an "interim" copy becomes permanent. Mitigations are honest rather than complete — the response emits `description: null` explicitly so a caller can tell "not supplied" from "empty" and choose to say *"a compatibility conflict was reported"* rather than guess; the lever still gives an actionable remedy; and SAF-35568 is tracked as a **dependency**, not a nice-to-have. Residual: this is a knowing regression on 14 codes' output. |
| **R10** | **SAF-35568 is now on Stage 1's critical path**, and its description half carries an unresolved localization question (`ui-react`'s strings are user-facing prose the console may localize). If that stalls, MCP has no meanings indefinitely. | **Medium** | SAF-35568 is explicitly scoped so the **lever half can ship alone** if localization stalls, and §10 requires MCP's resolver to tolerate a partial catalog — levers without descriptions — rather than treating it as an error. If the description half stalls past Stage 1, the fallback is to reopen the vendoring decision with that evidence in hand, not to discover the gap late. |

### Assumptions under question

- **The 88 codes are complete and current.** Measured on 2026-08-26 against the orchestrator working copy
  (21 groups, 89 entries, 87 keys, 88 values). Point-in-time by nature — R3 owns the consequence.
- **The endpoint's by-id resolution is sufficient for AC-1.** Read from `plan_statistics.js:51-53`; not yet
  exercised against a live console from MCP.
- **`getAllConstraints=true` is affordable as a default.** It is the console's own setting, but the console
  is not issuing it on every conversational turn as Helm will.

### Scope clarification — ACs 9/10 reworded from "remove" to "report" (decision D3)

Decision D3 was that a statistics call **reports** what will and will not run, and mutates nothing. Reviewing
the ticket against that, the original ACs 9/10 wording ("is auto-removed") described an **action on the plan
body**, not an output of a statistics call — the wording was the error, not the design.

The ticket was therefore **reworded on 2026-08-26** rather than the gap being accepted:

- ACs **9** and **10** now require the zero-impact attack / simulator to be **reported** as inapplicable with a
  plain-language explanation, never acting on `null`. Both are delivered by this PRD (§7).
- Description scope item **4** is now "Hard-failure **reporting**", and states explicitly that *acting* on the
  report — dropping those entities from the plan body being assembled — belongs to the caller that holds the
  configuration (Helm, or a future scenario-editing tool).
- The out-of-scope line now names plan-body mutation explicitly.
- AC-5 was aligned in the same edit ("performs no zero-impact reporting" rather than "no auto-removal"), and
  AC-12 now states that the rate-limiting gate table is not extended for a read-only tool.

**Consequence for the parent story.** SAF-34615 **req 7** keeps both halves in view: translation and
hard-failure surfacing are delivered here; the *act* of removing an entity from a configuration is not owned by
any Stage 1 subtask. Parent **DoD items 2 and 5** are covered; **DoD item 6** is covered only to the extent
that surfacing — not removing — satisfies it. Per the user's decision this is **recorded here and deferred**,
not tracked as a follow-up ticket yet; whether it becomes a new SAF-34615 subtask or folds into **SAF-35484**
(Story 2, which already owns the swap-or-proceed conflict family) is an open call. It changes no code planned
above.

---

## 10. Future Enhancements

- **[SAF-35568](https://safebreach.atlassian.net/browse/SAF-35568) — serve the constraint catalog from the
  plan/statistics response.** Not merely a follow-up: since this PRD deletes the vendored table, SAF-35568 is
  the **only** source of constraint meanings and is therefore a **dependency** of the parent story (R9, R10).
  Filed 2026-08-26 and linked to this sub-task. Today three repos vendor one vocabulary at three coverage levels: orchestrator 88 (source),
  ui-react 57 real + 3 dead + 31 untranslated, safebreach-mcp 14 → 88 under this PRD. That ticket adds a
  `constraintCatalog` to the statistics response mapping each code **referenced in that response** to
  `{ description, fixLever }`, gated on `getConstraints=true` — in the response rather than a new endpoint, so
  there is no second round trip and no way for the catalog to fall out of sync with the response it explains.
  It deliberately carries **no `severity`** (a function of the counts the consumer already has, and it would
  drift from them) and **no `kind`** (there is no informational class — all 88 eliminate).

  **What lands here when it ships.** MCP stops vendoring: `CONSTRAINT_CATALOG` is deleted and the response's
  `constraint_catalog` is filled from the API's instead. Because this PRD already normalizes conflicts into a
  catalog plus references, that changes **only where the catalog is populated from** — the tool's response
  contract is unaffected, and no test outside Phase 1 should need to move. The one thing MCP keeps is the
  **naming rename**: Core expresses levers in its own camelCase schema vocabulary (`attackerFilter.role`,
  `targetFilter.os`, `console.simulatorApproval`) while this tool exposes snake_case (`attacker_filter.role`,
  `target_filter.os`, `console.simulator_approval`) to match `step_overrides`. That mapping is mechanical, and
  worth writing down now so the migration is a rename rather than a surprise.

  **Partial adoption is expected.** SAF-35568 flags localization as an open question — `fixLever` is an enum
  and unaffected, but descriptions are user-facing prose the console may localize, so Core may ship the lever
  half first. MCP's resolver must therefore tolerate a catalog that supplies `fixLever` but not `description`,
  leaving `description: null` for those codes rather than treating a partial catalog as an error. Since MCP
  vendors no descriptions to fall back on, "partial" is the expected steady state for a while, not an edge
  case.
- **Acting on the zero-impact report** — dropping inapplicable attacks/simulators from the plan body being
  assembled. Explicitly out of scope here (§9); needs an owner, either a new SAF-34615 subtask or SAF-35484.
- **Correcting `quick_run` / `run_scenario` previews** to report runnable rather than expected counts. The
  layering makes this a one-parameter change, but it alters numbers two shipped tools already report, so it
  deserves its own decision and ticket.
- **Partial-impact and fail-rate conflicts with swap-or-proceed choices** — explicitly SAF-35484 (Story 2).
- **Automatic simulator shortlisting and filter-based selection** — parent story future scope.
- **Single-simulation re-run statistics** — the third code path (F7), via `systemFilter.simulations.values`.

---

## 11. Executive Summary

- **Issue/feature description**: MCP cannot answer "what will actually run in this configuration, and why
  not?" as a first-class question. The capability exists but is trapped inside a private pre-flight helper
  belonging to two test-running tools.
- **What was built**: `get_plan_statistics`, a read-only MCP tool over Core's `plan/statistics` endpoint. It
  accepts an ad-hoc plan body (or a `scenario_id`), exposes every query parameter, and returns per-step
  simulation, attack and simulator counts, translated constraint conflicts, and a zero-impact report. The
  existing private helper is refactored to route through the same code, so exactly one path to the endpoint
  exists.
- **Key technical decisions**: layer rather than rewrite, because 58 test references and two shipped tools
  depend on the existing helper's shape; runnable counts by default, since `includeDisabled=false` is the only
  setting that explains the gap; no MCP-side cache, because stale impact numbers are the exact failure being
  fixed; vendor the reason vocabulary by **emitted value**, since two of the 88 codes differ from their source
  key; and **MCP returns structure, Helm narrates** — the vendored translation table is **deleted** rather than
  extended, because vendoring is a pressure-release valve that has already let `ui-react`'s copy rot for years.
  What MCP keeps is the one fact it is the right owner of, a `fix_lever` per code; `severity` is computed from
  the counts rather than stored; and the conflict list is normalized into a catalog plus references so
  SAF-35568's API-served meanings drop in without a contract change.
- **Scope changes**: the constraint-description work is **out**, and SAF-35568 is now a **dependency** rather
  than a follow-up — a deliberate trade recorded in §9 R9/R10, which costs 14 codes their current descriptions
  in exchange for not creating a third copy of a vocabulary that demonstrably rots. Earlier, ACs 9/10 were **reworded** from "auto-removed" to "reported" (D3) — a statistics call
  reports what will and will not run; acting on that report is the plan-holder's job, and is now explicitly
  out of scope on the ticket. All 12 ACs are delivered. The *act* of removal still needs an owner (§9).
- **Business value delivered**: unblocks parent DoD items 2 and 5; gives Helm a non-destructive impact
  primitive it can call after every changed decision; and fixes three live defects — disconnected simulators
  counted as runnable, 74 of 88 conflict reasons leaking as raw `snake_case`, and a `TypeError` crash on large
  scenarios.

---

## 13. Change Log

| Date | Change Description |
|------|-------------------|
| 2026-08-26 | PRD created — initial draft |
| 2026-08-26 | DoD gate flagged TI-9/TI-10 as gaps. Root cause was the ticket's "auto-removed" wording, not the design: a statistics call reports, it does not act. Reworded SAF-35508 ACs 9/10 to "reported" (plus AC-5/AC-12 alignment, scope item 4, and the out-of-scope line); updated §7, §9, §10 and §11 to match. All 12 ACs now covered. |
| 2026-08-26 | **Deleted the vendored translation table (v4).** `CONSTRAINT_REASON_DESCRIPTIONS` is removed outright — including its 14 existing entries — rather than extended to 88. Rationale: a vendored table is a pressure-release valve, and `ui-react` proves an "interim" copy becomes permanent (57 real / 3 dead / 31 missing after years). What remains is `CONSTRAINT_FIX_LEVERS`: one closed-enum lever per emitted code, the fact a calling model cannot infer. No `description` is authored for any code; the response emits `description: null` explicitly so "not supplied" is distinguishable from "empty". Consequences recorded rather than hidden: SAF-35568 becomes a **dependency** (new R10) and 14 codes lose descriptions two shipped tools display today (new R9). R3 drops to Low (no meanings vendored, so none to drift); R7 narrows from descriptions to levers. Phase 1 shrinks from "author 88 descriptions from emit sites" to "delete the table, map 88 levers". Revised §1, §2, §3 A/D, §4, §7, §9, §10, §11, Phase 1. |
| 2026-08-26 | **Aligned to SAF-35568.** Filed the orchestrator follow-up and linked it *relates to* this sub-task, then pointed every forward reference at the ticket key instead of "§10 files a follow-up" (§2 solution + two alternatives rows, §9 R3 mitigation). Rewrote the §10 entry to match what the ticket actually proposes — `constraintCatalog` of `{ description, fixLever }` in the statistics response, gated on `getConstraints=true`, no `severity`, no `kind` — and added two things the ticket implies for this PRD: the **snake_case ↔ camelCase lever rename** MCP keeps after the migration, and the requirement that the resolver tolerate a **partial catalog** (levers without descriptions) since SAF-35568 may ship the lever half first while localization is resolved. |
| 2026-08-26 | **Correction — no `kind`, descriptions for all 88.** Checked the emit sites: every one of the 88 codes sets `valid = false` and the node is dropped from `filteredNodes` (`aws_validation.js:96-101`, `gcp_validation.js:77-81`). The `*_is_ignored` / `ignoring_*_variant` families are **variant-level de-duplication, not benign notes** — so the previous row's 72/16 `elimination`/`informational` split did not exist, and `kind` is removed entirely. Severity now derives from the counts alone. Because the names proved misleading, `description` is authored for **all 88** from their emit sites rather than ~20; the "self-describing majority" premise is retracted. R7 is rewritten from "misclassifying kind" to "descriptions written from names". `fix_lever` is no longer claimed to be MCP-specific — `attackerFilter`/`targetFilter` are Core's own `ValidatePlan` fields — so §10 now asks the API for `{ description, fixLever }` and drops the severity/catalog-endpoint proposal. T-37 tombstoned; T-1/T-3/T-36 rescoped. |
| 2026-08-26 | **Design revision — MCP is structured, Helm narrates.** Resolved the ticket's internal contradiction between scope item 1 ("no narrative fields — Helm interprets") and items 3/7 ("plain-language explanation + suggested fix") in favour of item 1. `CONSTRAINT_REASONS` (88 prose descriptions + 88 suggested fixes) becomes `CONSTRAINT_CATALOG` — `kind` + `fix_lever` for all 88, corrective `description` for ~20 only, `suggested_fix` dropped as model-derivable. Added computed `severity` (`blocking`/`reducing`/`none`), since blocker-ness is contextual per attack, not a property of the code. Normalized the response into a `constraint_catalog` + references, grouped by `(attack, code)`. Verified `unable_to_validate` cannot appear as a reason code, so no `indeterminate` severity. Added R7/R8; reframed R3 with the measured ui-react drift (3 dead entries, 31 gaps). Filed the orchestrator catalog follow-up in §10. Revised §2, §3 A/D, §4, §7, Phases 1 and 4. |
