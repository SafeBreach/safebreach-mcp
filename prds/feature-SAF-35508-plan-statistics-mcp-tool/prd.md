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
  3. **Explained** conflicts. Constraint-reason coverage goes from 14/88 to 88/88, with a suggested fix per
     code and a safe generic fallback so a raw `snake_case` code can never reach a user again.
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

1. **A vendored constraint classification catalog** (`CONSTRAINT_CATALOG`) covering all **88** emitted reason
   codes, keyed on the codes the API actually emits. Each entry carries `kind`
   (`elimination` | `informational`) and `fix_lever` — the two facts a calling model cannot derive — plus a
   `description` **only** for the ~20 codes whose plain reading is wrong or opaque. MCP does not narrate:
   Helm composes the sentence and the yes/no suggested fix from these structured facts (parent req 13).
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
| **Author a plain-language description and a suggested-fix sentence for all 88 codes** (the original plan) | Deterministic, testable prose; MCP fully self-describing. | Most codes are self-describing English sentences (`move_requires_zones_but_the_simulator_is_missing_zones`) — a calling model renders them better than a canned string, and can fill in real simulator UUIDs that a static sentence cannot. 88 hand-written descriptions also rot on every upstream rewording. Contradicts the ticket's own scope item 1 ("no narrative fields — Helm interprets"). | **Rejected** — carry only the non-derivable facts (`kind`, `fix_lever`, and ~20 corrective descriptions). |
| **Have the orchestrator API serve the catalog** (classification + descriptions) | Single source of truth; a new code is classified in the same commit that adds it; retires ui-react's duplicate table too. | Cross-team, multi-repo change on another release cadence — it would block a Stage 1 subtask scoped as "promote an existing helper". `fix_lever` is MCP-specific and would stay here regardless. | **Right long-term direction, deferred** — §10 files it as follow-up. Adopting the normalized catalog shape now makes that migration a drop-in with **no response-contract change**. |

### Decision rationale

The chosen shape is the only one that satisfies AC-6 without paying R2's regression cost, and it makes each
correctness fix independently reviewable. Naming (`get_plan_statistics`), the runnable default, and the
read-only/deferral posture are user decisions **D1–D3**, recorded in `context.md`.

---

## 3. Core Feature Components

### Component A — Vendored constraint classification catalog (`CONSTRAINT_CATALOG`)

**Purpose**: New data structure replacing the 14-entry `CONSTRAINT_REASON_DESCRIPTIONS`
(`studio_functions.py:2225`). Satisfies AC-7 and AC-8.

**The division of labour.** MCP carries only what a calling model cannot derive from the code string; Helm
composes the user-facing sentence. Most of the 88 codes are self-describing English
(`move_requires_zones_but_the_simulator_is_missing_zones`), and a model renders those better than a canned
string — it can name the actual simulator UUIDs a static sentence never could. Three things are **not** in the
code text, and those are what the catalog holds.

**Key features**
- **88 entries**, one per distinct emitted reason code, across the 21 validator groups in
  `orchestrator/src/server/sbGenerator/validators/constraints.js`.
- Each entry carries:
  - **`kind`** — `elimination` (this code means a simulator was excluded; 72 codes) or `informational` (a
    benign note that never excludes anything; **16** codes — the 12 `*_is_ignored` plus the 4
    `ignoring_*_variant`). Not derivable: read cold inside a list called "constraints",
    `move_does_not_require_zones_simulator_zone_is_ignored` looks like a problem when nothing is wrong. That
    is 18% of the vocabulary primed to generate false alarms.
  - **`fix_lever`** — a closed enum naming what fixes it: `attacker_filter.role`, `target_filter.os`,
    `*_filter.simulators`, `*_filter.connection`, `console.simulator_approval`, `console.license`,
    `console.advanced_actions`, `step.parameters`, or `null` for intrinsic incompatibility. Not derivable:
    `incompatible_os` is a step filter, `simulator_is_offline` is a console action, and
    `move_does_not_meets_license_requirements` is a licence — similar-looking codes, unrelated answers. A
    closed enum is also testable in a way free-text prose is not.
  - **`description`** — present for **only ~20** codes whose plain reading is wrong or opaque:
    `incompatible_package` is a *role* mismatch, not a software package; `simulator_is_offline` also covers
    **unapproved** simulators because `isEnabled = isConnected && approved`; `simulator_variant_is_*` uses
    internal vocabulary; `move_state_constraint` / `move_model_constraint_invalid_config` are opaque to
    anyone. **Its absence is a deliberate signal** — "this code says what it means, render it yourself."
- **`kind` is static; blocker-ness is not.** A reason lives at `[simulatorId][moveId]` and means "this
  simulator was eliminated for this attack". An attack usually has several candidates, and `moves[id]` is
  pre-seeded to 0 then incremented per survivor (F5). So ten candidates with nine eliminated by
  `incompatible_os` still yields a running attack. Whether an elimination **blocks** is therefore contextual
  and computed per (attack, step) — see Component D. The existing helper already encodes this distinction via
  `unmatched = sum(... if v == 0)` and its per-attack-versus-aggregated branch.
- **Keyed on emitted values, not source keys.** The critical correctness detail (F14): the source file has
  **87 distinct keys but 88 distinct values**, and two entries emit a value differing from their key —
  `some_cloned_advanced_actions_are_disabled` → **`some_duplicate_advanced_actions_are_disabled`**, and
  `move_does_not_require_location_simulator_location_is_ignored` (web-application group) →
  **`move_does_not_require_url_simulator_url_is_ignored`**. A key-derived table would ship two codes that can
  never occur while missing the two that do — and a naive coverage test would still report 88/88.
- Two codes are **shared across groups** (`incompatible_framework_version` appears in both
  `moveFrameworkConstraintValidator` and `mailSimulationValidator`), so an entry must not assume a single
  owning validator group.
- The 14 existing descriptions are preserved verbatim where they remain (all 14 are real codes; F15 confirms
  **zero** dead entries), since two shipped tools already display them.
- **Fail-safe default**: an unrecognised code — one added upstream after this ticket — resolves to
  `kind: elimination`, `fix_lever: null` and no description. It **over-reports** rather than hides: a spurious
  flag is recoverable, a silently-swallowed blocker is not. The code is never presented as the explanation.
- **`unable_to_validate` is not a concern.** `validation_type.js` carries a third outcome, but it is returned
  only from a catch block on the *generation* path (`sbGenerator/validators/index.js:60`), while
  `simulatorConstraints` is populated exclusively by `StatisticsAggregator.addConstraintBySimulator` with
  reasons from `constraints.js`. It is a separate return channel and cannot appear as a reason code, so no
  `indeterminate` severity is required.

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
  construction the `severity: blocking` subset. An `informational` code therefore **cannot** be offered as the
  reason something runs nowhere, and neither can a `reducing` one; the guarantee is derived from the counts
  rather than statically asserted. Two further correctness rules:
  - Simulators are read from the **union `simulators` map**, never a single role map — a node present on only
    one side is `undefined` in the other, never `0` (F5). The current helper never extracts this map at all.
  - An entry is reported **only** when its value is an integer `0`. `None` never qualifies.
  - When the response is limit-reached, zero-impact reporting is **suppressed entirely** and the truncation is
    surfaced instead.
- **Normalized conflicts — a catalog plus references.** The response carries a top-level
  `constraint_catalog` holding one entry per code **actually present in this response** (so it stays small,
  typically a handful rather than 88), and each per-conflict entry references it by `code`, carrying only what
  varies: the computed `severity`, `attack_id`, `side`, `simulator_count`, and the API's own `values` detail
  (which genuinely differs per simulator — `required: WINDOWS, actual: LINUX` versus `actual: MAC`).
  This matters for two reasons beyond payload size. It makes a single code's **contextual** severity legible
  without contradiction — the same `incompatible_os` can be `blocking` for one attack and `reducing` for
  another, because the static and contextual halves now live in different places. And it makes the eventual
  migration to an API-served catalog (§10) a **drop-in with no response-contract change** — only where MCP
  fills the catalog from.
- **Computed `severity` per conflict**, derived rather than asserted: `blocking` (an `elimination` code on an
  attack whose count is `0`), `reducing` (an `elimination` code on an attack that still runs, on fewer
  simulators than offered), or `none` (`informational`). This ticket **acts on** `blocking` only —
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
    "incompatible_os":      { "kind": "elimination", "fix_lever": "target_filter.os" },
    "incompatible_package": { "kind": "elimination", "fix_lever": "attacker_filter.role",
                              "description": "Simulator role mismatch — requires infiltration/exfiltration." },
    "simulator_is_offline": { "kind": "elimination", "fix_lever": "console.simulator_approval",
                              "description": "Disconnected or not approved — excluded from runnable counts." },
    "move_does_not_require_credentials_simulator_credentials_is_ignored":
                            { "kind": "informational", "fix_lever": null }
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
  gains `kind`/`fix_lever` without losing wording they already display. Only `_summarize_constraints` reads the
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
- [ ] All **88** emitted reason codes carry a `kind` (`elimination` / `informational`) and a `fix_lever` from
      the closed enum, keyed on the codes the API emits — including the two whose emitted value differs from
      their source key. The **16** informational codes are classified as such. A test fails if any emitted code
      lacks an entry. *(AC-7)*
- [ ] The ~20 codes whose plain reading is wrong or opaque carry a corrective `description`; the remaining
      self-describing codes deliberately do not. *(AC-7)*
- [ ] Conflicts are returned **normalized** — a `constraint_catalog` of the codes present in the response, plus
      per-conflict references carrying only `severity`, `attack_id`, `side`, `simulator_count` and `values`. *(AC-8)*
- [ ] `severity` is **computed** per (attack, step) — `blocking` when the attack's count is `0`, `reducing` when
      it still runs, `none` for informational — never asserted statically per code. *(AC-8)*
- [ ] A bare reason code is never presented as the explanation; an unrecognised code fails safe to
      `kind: elimination`, `fix_lever: null`, over-reporting rather than hiding. *(AC-8)*
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

### Phase 1 — Vendored classification catalog + fail-safe resolver

**Semantic change**: Replace the 14-entry description table with an 88-entry classification catalog that can
always answer, and stop the raw-code fallback.

**Deliverables**: `CONSTRAINT_CATALOG`; a resolver that returns a classified entry for any input; the single
direct consumer switched onto it.

**Implementation details**
- Build the entry set from the **emitted values** of the 21 exported groups in orchestrator's
  `constraints.js`. Enumerate by value, not by key: 87 keys, 88 values, two entries emitting a different
  string than their key (§3 Component A names both). Deduplicate — `incompatible_framework_version` is
  emitted by two groups.
- Each entry carries `kind` and `fix_lever`; a `description` **only** where the code's plain reading is wrong
  or opaque (~20 codes). Do **not** author prose for the self-describing majority, and do not author
  `suggested_fix` at all — Helm composes the sentence from `fix_lever` plus `values`.
- Classification is largely patternable by validator family, which is what makes 88 rows tractable: the
  AWS/Azure/GCP/Bedrock/web-application `*_is_ignored` set and the `ignoring_*_variant` set are
  `informational` / `fix_lever: null`; the `move_requires_X_but_the_simulator_is_missing_X` family is
  `console.*`; the OS/role/connection families map to their corresponding `*_filter.*` lever. Verify each row
  rather than trusting the pattern blindly, but the pattern is the starting point.
- Preserve the 14 existing description strings verbatim wherever they survive into the ~20 — two shipped
  tools already display them.
- Introduce a resolver used by every consumer. On a miss it fails safe to `kind: elimination`,
  `fix_lever: null`, no description — over-reporting rather than hiding — and **never** echoes the code as an
  explanation. Replaces `...get(code, {}).get('description', code)` at `:2333`.
- **Repoint one function, not two.** `_summarize_constraints` (:2299) is the *only* direct reader — the table
  is referenced at exactly `:2333` and `:2334`, both inside it. `_summarize_constraints_aggregated` (:2350)
  consumes it transitively: at `:2357` it calls `_summarize_constraints` and copies the resolved fields off the
  result, so it inherits the fix automatically. Both must keep emitting their current keys so Component C's
  contract holds; new fields are additive.

**What can go wrong**: enumerating by key silently ships two impossible codes and misses two real ones, and a
key-based coverage test still reports 88/88 — the guard must compare against emitted values. Misclassifying an
`*_is_ignored` code as `elimination` reintroduces the false-alarm class. A resolver that falls through to the
code violates AC-8.

**Changes**

| File | Description |
|---|---|
| `safebreach_mcp_studio/studio_functions.py` | Replace `CONSTRAINT_REASON_DESCRIPTIONS` (:2225) with `CONSTRAINT_CATALOG`; add fail-safe resolver; repoint `_summarize_constraints` (:2333-:2334) |

**Git commit**: `feat(studio): classify all 88 constraint reason codes with kind and fix lever`

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
- **Compute `severity`** per conflict from the catalog `kind` plus the attack's own count: `none` when the
  code is `informational`; otherwise `blocking` when `attacks[attack_id]` is an integer `0`, and `reducing`
  when it is a positive integer. Never derive severity from the code alone — the same code is legitimately
  `blocking` for one attack and `reducing` for another in the same step.
- **`conflict_detail`**: `summary` (default) groups by code with counts; `per_attack` keys by
  `(attack, code)`; `full` adds a capped `simulator_ids` sample. The default must stay cheap.
- **Zero-impact attacks**: entries of `attacks` whose value is an integer `0`, each carrying its `blockers` —
  the `severity: blocking` subset only. An `informational` or `reducing` conflict can never appear here.
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
| **R3** | **Vendored-catalog drift — measured, not hypothetical.** The vocabulary lives in `orchestrator`, on a different release cadence. The console has been vendoring the same vocabulary for years in `ui-react/src/containers/Studio/utils/constants.ts:166` and has demonstrably drifted **in both directions**: **3 dead entries** for codes orchestrator no longer emits (`incompatible_simulator_version`, `assume_role_incompatible_simulator_version`, `move_does_not_support_simulation_user_and_simulator_does_not_allows_default_system_user`), and **31 of 88 codes** it cannot translate at all, plus 4 explicitly commented out. This PRD adds a **third** copy. | **Medium-High** | Interim: fail-safe default (over-report, never hide), the coverage guard (AC-7), and the drift test (T-5). Structural: §10 files the orchestrator ticket to serve the catalog, and the normalized response shape makes that migration a drop-in. Residual, stated plainly — none of this *prevents* drift; it makes it loud and safe. The only real fix is the API serving the classification, which is deliberately out of scope here. |
| **R4** | **"Matches the console" is not one number.** Checkout uses `includeDisabled=true`, run gating `false`. | **Medium** | AC-4 is per-view and per-parameter-set; §4 tabulates which parameters correspond to which view. |
| **R5** | **Cost of correctness.** `getAllConstraints=true` disables the validator short-circuit; both figures need two round trips, against a 120 s timeout. | **Medium** | Runnable default is one call; the second is opt-in (D2); every parameter is overridable for a cheap count-only call. |
| **R6** | **Vendoring by key rather than by value** ships two impossible codes, misses two real ones, and passes a naive coverage test. | **Medium** | Called out explicitly in §3 Component A and Phase 1; the guard compares against emitted values (T-2). |
| **R7** | **Misclassifying `kind`.** Marking one of the 16 `informational` codes as `elimination` reintroduces the false-alarm class the catalog exists to prevent; marking an `elimination` code as `informational` hides a real blocker. | **Medium** | The 16 are a closed, pattern-identifiable set (`*_is_ignored`, `ignoring_*_variant`) enumerated in §3 Component A; the fail-safe default is `elimination`, so an *omission* over-reports rather than hides. A misclassification in the other direction is the one failure the defaults do not cover — hence per-row verification in Phase 1 rather than trusting the family pattern. |
| **R8** | **Asserting severity statically per code** instead of computing it from the attack's count would label every `reducing` conflict a blocker — pulling SAF-35484's partial-impact scope into this ticket by accident and over-reporting zero-impact attacks. | **Medium** | Severity is derived in Phase 4 from `attacks[attack_id]`; the catalog carries only `kind`. Covered by a test asserting the same code resolves `blocking` and `reducing` within one step. |

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

- **Serve the constraint catalog from the orchestrator API** — the structural fix for R3, and the most
  valuable follow-up here. Today three repos vendor the same vocabulary at three different coverage levels:
  orchestrator 88 (source), ui-react 57 real + 3 dead, safebreach-mcp 14 → 88. Classification belongs where
  the constraint is defined, so a developer adding a reason classifies it in the same commit and every consumer
  inherits it. Concretely: `constraints.js` maps `key → code` today and would map `key → { code, severity }`,
  surfaced either inline per reason in the statistics response or via a catalog endpoint. Then ui-react retires
  its table and MCP keeps only `fix_lever` — which is genuinely MCP-specific, since Core has no concept of
  `step_overrides`. Because this PRD already normalizes the response into a catalog, that swap changes **only
  where MCP fills the catalog from**, not the response contract.
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
  key; and **MCP returns structure, Helm narrates** — the catalog carries only what a model cannot derive
  (`kind`, `fix_lever`, ~20 corrective descriptions), with `severity` computed per attack rather than asserted
  per code, and the whole conflict list normalized into a catalog plus references so an API-served catalog can
  later drop in without changing the contract.
- **Scope changes**: ACs 9/10 were **reworded** from "auto-removed" to "reported" (D3) — a statistics call
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
| 2026-08-26 | **Design revision — MCP is structured, Helm narrates.** Resolved the ticket's internal contradiction between scope item 1 ("no narrative fields — Helm interprets") and items 3/7 ("plain-language explanation + suggested fix") in favour of item 1. `CONSTRAINT_REASONS` (88 prose descriptions + 88 suggested fixes) becomes `CONSTRAINT_CATALOG` — `kind` + `fix_lever` for all 88, corrective `description` for ~20 only, `suggested_fix` dropped as model-derivable. Added computed `severity` (`blocking`/`reducing`/`none`), since blocker-ness is contextual per attack, not a property of the code. Normalized the response into a `constraint_catalog` + references, grouped by `(attack, code)`. Verified `unable_to_validate` cannot appear as a reason code, so no `indeterminate` severity. Added R7/R8; reframed R3 with the measured ui-react drift (3 dead entries, 31 gaps). Filed the orchestrator catalog follow-up in §10. Revised §2, §3 A/D, §4, §7, Phases 1 and 4. |
