# PRD — MCP support for Core plan statistics API (`get_plan_statistics`) — SAF-35508

## 1. Overview

- **Title**: MCP support for Core plan statistics API: ad-hoc plan impact, per-attack/simulator counts, and constraints — SAF-35508
- **Task Type**: feature + refactor (+ bug fix — three live defects in the existing private helper)
- **Purpose**: Helm must repeatedly answer, mid-conversation, *"given the configuration as it stands right
  now, what will actually run, what will not, and why?"* The orchestrator already answers this via
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
  3. **Explained** conflicts. Every reason code carries the authoritative `description` the orchestrator now serves in the
     `plan/statistics` response ([SAF-35568](https://safebreach.atlassian.net/browse/SAF-35568), delivered).
     Meanings are **not** MCP's to own: the vendored translation table is deleted outright and the API's
     catalog is relayed instead (§3 A, §10).
- **Business Alignment**: Implements functional requirements **6** and **7** of parent story SAF-34615
  ("MCP support for Validate scenario creation and update, Stage 1"), and covers parent Definition-of-Done
  items **2** and **5**. See §9 for the DoD-6 caveat introduced by the scope decision.
- **Originating Request**: [SAF-35508](https://safebreach.atlassian.net/browse/SAF-35508), subtask of
  [SAF-34615](https://safebreach.atlassian.net/browse/SAF-34615).

---

## 1.5 Document Status

| Field | Value |
|-------|-------|
| **PRD Status** | In Progress |
| **Last Updated** | 2026-09-03 |
| **Owner** | Boris Berezovsky (AI-assisted planning) |
| **Current Phase** | Phases 1–6 complete; every automatic test green, including the five e2e against a real console. **Phase 7 complete 2026-09-03; Phases 8–9 pending (decision D4)**: the single `get_plan_statistics` tool is decomposed into three question-shaped tools and its registration retired (§2 revision, §3 Component E, §8). **Remaining from 1–6: T-32, T-33, T-35 (Manual)** — T-35 is the only check that the numbers match what the console itself displays, and it is now owed against the counts tool rather than the retired one. |

---

## 2. Solution Description

### Chosen solution — a new raw fetch core, with the existing helper refactored on top of it

Four pieces, in dependency order:

1. **Delete the translation table; relay the orchestrator's catalog.** `CONSTRAINT_REASON_DESCRIPTIONS` is removed
   outright rather than extended — MCP stops owning constraint *meanings* altogether, and vendors **no**
   replacement of any kind. [SAF-35568](https://safebreach.atlassian.net/browse/SAF-35568) has delivered a
   `constraintCatalog` in the `plan/statistics` response itself, mapping every code that response references
   to its authoritative `description`. MCP relays it; Helm renders the sentence from that description (parent
   req 13). A code the API does not describe reports `description: null` and is still surfaced.
2. **A new low-level fetch function in `safebreach_mcp_core`** that performs the HTTP call, exposes **every**
   query parameter, and returns the **raw, null-safe** per-step response — including the `simulators` union map
   and `isLimitReached`, both of which the current helper never even extracts. `plan/statistics` is a general
   orchestrator API rather than a studio concern, and further clients are expected, so it ships as a shared
   core primitive from the start rather than being promoted later (§3 B).
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
| **Generate the translation table at runtime from `constraints.js`** | Never drifts from upstream. | `orchestrator` is not a dependency of `safebreach-mcp`, and the file is JavaScript. Would add a cross-repo build-time coupling to a differently-cadenced release. | **Rejected, and now moot** — SAF-35568 serves the same vocabulary in the response, which achieves never-drifts without the coupling. |
| **Describe only the ~20 codes whose plain reading misleads, and let a model infer the rest** | Smallest artifact; less to rot on an upstream rewording. | Rests on the other ~77 being self-describing, which is **false**. The `*_is_ignored` family reads as a benign note and in fact eliminates the node (`aws_validation.js:96-101`). Deciding per-code which names can be trusted is an unbounded judgement, and the failure mode is a *confidently wrong* explanation. | **Rejected** — but so was describing all 97; see the next two rows. |
| **Vendor a description for all 97, authored from their emit sites** | SAF-35508 ships self-sufficient; fixes the live raw-code leak immediately; no dependency on another team. | It is the largest authoring effort in the plan and **entirely throwaway** once SAF-35568 serves descriptions. Worse, it is a pressure-release valve: `ui-react` has carried an "interim" copy of this vocabulary for years — 57 real entries, 3 dead, 31 missing — precisely because vendoring removed the incentive to fix the API. A third copy would do the same. | **Rejected** — deleting is the only option that keeps the forcing function on SAF-35568. |
| **Delete the table; keep only the fix-lever map** | MCP stops owning meanings it is not the source of, with no throwaway authoring and no third copy. | Was chosen on the premise that SAF-35568 would serve **both** `description` and `fixLever`. It shipped `description` only — `fixLever` was built and then removed as redundant relative to it — so a lever map here would be a permanently MCP-owned artifact with no upstream counterpart, drifting against 97 codes forever and asserting a remedy from an enum never validated against the orchestrator's own `ValidatePlan` / `simulatorsFilter` fields. | **Superseded** by the row below, once SAF-35568's actual shape was known. |
| **Delete the table; relay the orchestrator's `constraintCatalog`** | MCP vendors nothing at all — no meanings, no levers, no coverage guard, nothing to drift. Descriptions arrive in the same payload as the codes they explain, at full coverage rather than the 14/97 MCP vendored. Satisfies AC-7 **and** AC-8's description half without authoring a word. | Descriptions now depend on the console's orchestrator version: one predating SAF-35568 sends no catalog, so those conflicts report `description: null` — including the 14 that had vendored prose (R9, R11). No lever is offered to any caller. | **Chosen.** The residual is a bounded, self-resolving deployment lag recorded in §9 R11, not an authoring debt. |
| **Classify each code as `elimination` vs `informational`** (a `kind` field) | Would let a consumer drop benign notes rather than report them as problems. | **No such class exists.** Every one of the 97 sets `valid = false` and the node is never pushed to `filteredNodes` — verified in `aws_validation.js:96-101` and `gcp_validation.js:77-81`. The apparent "informational" family is variant-level de-duplication, and the effect it was meant to capture is already covered by severity derived from the counts: a variant elimination on an attack that still runs is `reducing`. | **Rejected — premise was wrong.** No vocabulary metadata is needed for severity. |
| **Keep `fix_lever` MCP-side permanently** | The orchestrator serves no lever, so MCP would be the only place a remedy is stated at all. | `step_overrides` is only MCP's wrapper over `attackerFilter` / `targetFilter`, which are **The orchestrator's own `ValidatePlan` fields**, so the lever was never MCP-specific knowledge to begin with. SAF-35568 implemented `fixLever`, reviewed it, and **deleted it as redundant relative to `description`** — a well-written description already names the surface. Keeping it here would re-adopt a rejected design as a permanent single-repo artifact. | **Rejected** — no lever map is vendored; §9 R7 records the residual. |
| **Have the orchestrator API serve the catalog** | Single source of truth; a new code is described in the same commit that adds it; retires ui-react's duplicate table too. | Cross-team, multi-repo change on another release cadence; carried an unresolved localization question. | **Delivered as SAF-35568** — and consumed here. Because this PRD had already normalized conflicts into a catalog plus references, adopting it changed only *where the catalog is filled from*, with no response-contract change. Localization stayed open and does not block MCP (§10). |

### Decision rationale

The chosen shape is the only one that satisfies AC-6 without paying R2's regression cost, and it makes each
correctness fix independently reviewable. Naming (`get_plan_statistics`), the runnable default, and the
read-only/deferral posture are user decisions **D1–D3**, recorded in `context.md`. The decomposition into
three question-shaped tools and the retirement of the single one are user decision **D4** (2026-09-02).

---

### Revision — three question-shaped tools replace the single reporting tool

**2026-09-02, user decision D4.** The tool as delivered answers one broad question — *"report everything
about this scenario"* — and leaves the caller to find its own answer inside a report carrying counts,
zero-impact attacks, zero-impact simulators, every conflict blocking-first, and a constraint catalog. Helm
does not ask that question. It asks three narrow ones, and it asks them one at a time:

1. **"Why didn't these specific attacks run?"** — a named set of attack ids, and the constraints that blocked them.
2. **"Is there anything here that will not run at all?"** — the attacks and simulators contributing nothing.
3. **"How many simulations will this scenario produce?"** — the counts, and nothing else.

Each is answered today only by the caller reading past the other two. The decomposition gives each question
its own tool, its own narration, and its own defaults, so the answer arrives **filtered and concrete** rather
than as a report to be mined.

**The plumbing does not move.** All three tools call the shipped `sb_get_plan_statistics`, which keeps its
contract and keeps being the repo's **single** `plan/statistics` call site — **AC-6 is untouched by this
revision**, not re-satisfied by it. What is new is a projection layer between that report and the caller:
three pure functions that select the slice their question needs, and three narrators that render only that
slice. Nothing in the fetch core, the shaping layer, or the summariser changes.

**`get_plan_statistics` is retired as a registered tool** (D4). Its function survives as the shared plumbing
all three sit on, so the 31 test references that target `sb_get_plan_statistics` are unaffected; the ~10 that
target the *tool* are retargeted in Phase 8. Leaving it registered alongside the three was considered and
rejected — four tools competing to answer the same question is precisely the selection problem the
decomposition exists to remove, and the broad one would keep winning on the strength of its name.

**Caller-facing vocabulary becomes "scenario"** (D4). The three tools, their parameters, their descriptions
and the CLAUDE.md catalog say *scenario*; the ad-hoc-body parameter is `scenario`, alongside `scenario_id` for
a saved one. The orchestrator's endpoint genuinely is `plan/statistics` and the shipped internals
(`fetch_plan_statistics`, `_build_plan_statistics_report`, `sb_get_plan_statistics`) keep those names — they
name the API, not the concept, and renaming them would churn 31 green tests for no caller-visible gain. The
boundary is deliberate: MCP's outward vocabulary is the product's, its internal vocabulary is the API's.

| Alternative | Pros | Cons | Verdict |
|---|---|---|---|
| **Keep one tool; let the model filter the report itself** | Zero code change; the report already contains all three answers. | This is the status quo, and it is what prompted the request. The model pays for a full report — counts, both zero-impact lists, every conflict, the catalog — to answer "how many simulations", and a capped report can drop the very rows its question needed (`CONFLICTS_CAP` sorts blocking-first, but `ZERO_IMPACT_CAP` truncates at 50 with no notion of which attack was asked about). | **Rejected** — the filtering has to happen before the cap, which means server-side. |
| **Three tools as projections over the shipped report** | One fetch path, one shaping layer, one null-vs-zero rule, three narrow narrations. Each projection is a pure function over a dict and unit-testable with no console. Caps apply per question, so the counts tool cannot be truncated by conflicts it never renders. | A projection can only surface what the shaped report already carries; a future question needing raw response fields would have to extend the shaping layer first. | **Chosen** — the three questions are all answerable from the existing shape. |
| **Three tools, each fetching and shaping independently** | Each tool free to request exactly what it needs from the endpoint. | Triples the zero-impact, severity, cap and null-safety logic, so the R1 rule (`null` is not `0`) would need enforcing in three places instead of one — and **breaks AC-6**, which requires exactly one `plan/statistics` call site. | **Rejected** — violates an acceptance criterion of this same PRD. |
| **One tool with a `question` parameter, three thin registrations** | Same runtime behaviour as the chosen shape. | Collapses three independent projections into one branching function; a bug in one branch is reachable from all three tools, and the branches cannot be tested in isolation. | **Rejected** — no benefit over three pure functions. |

---

## 3. Core Feature Components

### Component A — Delete the vendored translation table; relay the orchestrator's catalog

**Purpose**: Remove `CONSTRAINT_REASON_DESCRIPTIONS` (`studio_functions.py:2225`) outright and fill the
response's `constraint_catalog` from the `constraintCatalog` the orchestrator now serves in the `plan/statistics` response
([SAF-35568](https://safebreach.atlassian.net/browse/SAF-35568), delivered). Satisfies AC-7 **and** AC-8's
description half. MCP vendors **no** constraint vocabulary of any kind — no meanings, no levers, no coverage
guard.

**Why relay rather than vendor.** MCP is not the source of truth for what a constraint code means —
`orchestrator` is, and as of SAF-35568 it says so in the response itself. Vendoring a meaning here would
create a third copy of one vocabulary, and the evidence that this does not stay "interim" is direct:
`ui-react` has carried its copy for years and it has drifted both ways (57 real entries, 3 dead, 31 missing,
4 commented out). A relay cannot drift at all: the catalog arrives in the same payload as the codes it
explains, so it is impossible for it to describe a different vintage of the vocabulary.

**How the relay works**
- The orchestrator returns a top-level `constraintCatalog`, keyed by emitted reason code, each entry `{ description }`,
  **scoped to the codes referenced in that response** and gated on `getConstraints=true` — which is this
  tool's default (§4). That is the same gate that populates `simulatorConstraints`, so there is no parameter
  combination in which conflicts arrive without their catalog.
- MCP renames only the wrapper key (`constraintCatalog` → `constraint_catalog`, snake_case per house style)
  and narrows it to the codes its own normalized conflict list actually emits — a subset whenever MCP
  suppresses conflicts, as on a limit-reached response. Code keys and description text pass through
  **verbatim**: MCP does not edit, re-word, truncate, or reformat them. Re-wording would quietly re-create the
  third copy this design deletes.
- **No `fix_lever`, for any code.** SAF-35568 implemented one and then removed it as redundant relative to
  `description`, so there is no API-served lever to relay — and MCP does not invent one. The remedy is
  derivable by the caller from the description plus the `step_overrides` schema it already holds. See §2's
  alternatives and §9 R7.
- **No `description` authored here, for any code.** Not for the 83 that were never translated, and not for the
  14 that had one — those are deleted too, so output is uniform rather than 14 locally-authored strings at one
  vintage and the API's at another.
- **No `kind` field.** All 97 codes eliminate the node: every one sets `valid = false`, after which the node is
  never pushed to `filteredNodes` (`aws_validation.js:96-101`, `gcp_validation.js:77-81`). The `*_is_ignored`
  and `ignoring_*_variant` families are variant-level de-duplication, not benign notes. An earlier draft
  asserted a 72/16 `elimination`/`informational` split; it was inferred from code names and is **wrong**.
- **Nothing is keyed by hand, so the key-versus-value trap is gone.** It was real: `constraints.js` declared
  **87 keys for 88 emitted values**, two of them emitting a string differing from their key
  (`some_cloned_advanced_actions_are_disabled` → **`some_duplicate_advanced_actions_are_disabled`**, and
  `move_does_not_require_location_simulator_location_is_ignored` → **`move_does_not_require_url_simulator_url_is_ignored`**).
  SAF-35568 renamed both at source and deleted 5 dead keys, leaving **97 codes across 24 groups with keys 1:1
  with emitted values**. A relay is immune either way: it keys off what the response contains, never off a
  locally enumerated list.
- **Fail-safe default**: a code with no catalog entry — an older console (R11), or one the orchestrator added after its own
  catalog — resolves to `description: null` and is **still surfaced** as a conflict. Never dropped, never given
  an invented meaning, and never rendered with the raw code standing in as its explanation.

**Blocker-ness is contextual and needs no vocabulary metadata.** A reason lives at `[simulatorId][moveId]` and
eliminates one node variant for one attack. An attack usually has several candidates, and `moves[id]` is
pre-seeded to 0 then incremented per survivor (F5), so nine of ten eliminated still yields a running attack.
Severity therefore falls straight out of the counts — see Component D — which is what makes a variant
de-duplication read as low-priority (`reducing`) without anyone classifying it.

**`unable_to_validate` is not a concern.** `validation_type.js` carries a third outcome, but it is returned
only from a catch block on the *generation* path (`sbGenerator/validators/index.js:60`), while
`simulatorConstraints` is populated exclusively by `StatisticsAggregator.addConstraintBySimulator` with reasons
from `constraints.js`. It is a separate return channel and cannot appear as a reason code.

### Component B — Shared fetch core (`fetch_plan_statistics`, in `safebreach_mcp_core`)

**Purpose**: New shared module `safebreach_mcp_core/plan_statistics.py`; the single point at which
`plan/statistics` is called, by any server. Satisfies AC-1, AC-2, AC-5 and AC-6.

**Why core rather than studio.** `plan/statistics` is a general orchestrator API, not a studio concept — it
answers "what would this plan do", which any server holding a plan may need. Studio is merely its first
consumer. The precedent is exact: `safebreach_mcp_core/queue_state.py` wraps the orchestrator queue endpoint
the same way and is imported by both `data_functions.py` and `studio_functions.py` (:3111), so the shape and
the import style are already established. Placing it in core from the start also avoids a later migration
becoming a breaking move: servers are strictly siloed — the only cross-package import anywhere is within
`data` — so a second consumer could not reach a studio-resident helper at all, and would force the promotion
under time pressure. A concrete candidate already exists: `config_types.py:351-358` tells the agent that
`total_attack_count` is indeterminate for criteria-based steps and to run a scenario to find out, which is
precisely what this function computes.

**Key features**
- **Public, not private.** Named `fetch_plan_statistics` with no leading underscore, because it is now
  cross-package API — matching `queue_state.get_orchestrator_test_state`. It takes and returns plain
  dicts/primitives with no studio-specific types in its signature, so no consumer inherits studio's vocabulary.
- **Nothing studio-specific inside it.** Constraint-catalog relaying, conflict normalization and zero-impact
  reporting are presentation and stay in studio (Component D). The orchestrator returns the response, null-safety and
  truncation facts; each consumer shapes its own output.
- Accepts a **plan body** (ad-hoc, no saved scenario needed) or a `scenario_id`. `planId` is present in the
  `ValidatePlan` schema but is **not** honoured by the controller and must not be used.
- **CORRECTED 2026-08-27 — `scenario_id` is a passthrough only for a custom plan, never for an OOB scenario.**
  This bullet previously read "the endpoint natively resolves a saved plan when the body carries `id` or
  `testId`, so `scenario_id` is a passthrough as `{id: ...}` — no client-side resolution", inferred from
  `plan_statistics.js:51-53`. Probing a live console falsified it: `ValidatePlan` types `id` as an
  **integer**, so `{"id": 1}` and `{"id": "1"}` are accepted (Ajv coerces the string) but
  `{"id": "<uuid>"}` returns **`400 /id must be integer`**, and `{"testId": "<uuid>"}` is rejected with
  *"TestSummary … doesn't have originalPlan"* — `testId` wants a **test**, not a scenario. An OOB scenario's
  UUID therefore has **no field on this endpoint that accepts it**.
  **Consequence**: the fetch core keeps its passthrough (an integer id still goes straight to the orchestrator, so
  **T-7 is unaffected**), and an OOB scenario is resolved to its steps **in studio** — where
  `_fetch_all_scenarios` already lives — and scored as an ad-hoc body. Client-side resolution is therefore
  required for OOB scenarios, contrary to the original claim, but it stays out of core and out of the
  fetch layer.
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
  switch to the relayed catalog, so both existing tools inherit full API-supplied coverage — every code the
  response references, not the 14 vendored today — plus the `description: null` safe fallback.

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
  the API-supplied `description`, relayed verbatim, per Component A — so it stays small,
  typically a handful rather than 97), and each per-conflict entry references it by `code`, carrying only what
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
- **`hint_to_agent`** on the ambiguous cases: limit-reached truncation, an empty-steps rejection, the
  expected-vs-runnable distinction when only one figure was requested, and — per R11 — the case where the
  console supplied no `constraintCatalog` at all, so a caller knows the missing descriptions mean "this
  console predates SAF-35568" rather than "these conflicts have no meaning".
- **Retired as a registered tool by decision D4 (2026-09-02).** Everything above still describes the
  **function** `sb_get_plan_statistics` and the report it builds — all of which survives unchanged as the
  plumbing the three tools in Component E sit on, and as the repo's single `plan/statistics` call site. What
  is withdrawn is only the MCP registration of that report as a tool in its own right, in Phase 8.

---

### Component E — Three question-shaped tools over the shipped report (D4)

**Purpose**: Give each of Helm's three actual questions its own tool, its own narration and its own defaults,
so the answer arrives filtered and concrete. Replaces Component D's single registration; Component D's
**function** is the shared plumbing all three sit on.

**Shape**: two layers, both pure, both above `sb_get_plan_statistics`.

- **Projections** — one pure function per question, taking the report dict Component D already builds and
  returning only the slice that question needs. No I/O, no console, no transport seam; unit-testable against a
  literal dict, exactly as Phase 4's shaping layer is.
- **Narrators** — one per projection, rendering that slice as markdown in the house style of every other
  studio tool. Each renders only its own sections, so the counts tool cannot be crowded out by conflicts it
  never asked for.

**The three tools**

| Tool | Question it answers | Renders | Deliberately omits |
|---|---|---|---|
| `get_scenario_simulation_counts` | "How many simulations will this produce?" | Counts mode, steps scored of plan size, per-step `simulation_count`, the total, truncation, and the attack/simulator coverage lines. | Conflicts, both zero-impact lists, the constraint catalog. |
| `get_scenario_blocked_entities` | "Is there anything here that will not run at all?" | `zero_impact_attacks` and `zero_impact_simulators` with their blockers, the coverage denominators that make "N of M" legible, only the catalog entries those blockers cite, and an explicit **"nothing is fully blocked"** verdict when both lists are empty and counts were computed. | The `reducing` conflicts — an attack that runs on fewer simulators than offered is not an answer to "will anything not run at all". |
| `get_scenario_attack_blockers` | "Why didn't attack #N run?" | For each requested id whose count is an integer `0`: its blocking constraints with the relayed descriptions. For each requested id that is **not** blocked: one line of disposition. | Everything about attacks the caller did not name. |

**Key features**

- **Full parameter pass-through on all three** (user decision). Each carries `console`, `scenario`,
  `scenario_id`, `test_id`, `include_disabled`, `both_counts`, `get_constraints`, `get_all_constraints`,
  `limit`, `use_cache` and `conflict_detail`. The split is in what each tool *renders*, not in what a caller
  may *ask for* — a narrowed surface would make a question unaskable rather than merely unasked.
- **Defaults differ where the question differs.** `get_scenario_simulation_counts` defaults
  `get_constraints=False`: it renders no conflicts, so evaluating them is pure cost, and the cost is not
  hypothetical — a single default step measured live returned 38 531 conflicts and an 11.8 MB result. The
  parameter is still exposed, so a caller who wants the constraint pass can have it; it simply is not paid for
  by default. The other two default `True`, as the shipped tool does, because their answer *is* the
  constraints.
- **`attack_ids` on `get_scenario_attack_blockers`**, comma-separated integers, matching `sb_quick_run`'s
  existing convention rather than inventing a second one. **Optional**: supplied, the tool answers about
  exactly those attacks; omitted, it reports every fully-blocked attack in the scenario and emits **no**
  disposition lines, because nothing was specifically asked.
- **Dispositions are for named ids only** (user decision). A caller who names attack #9012 and gets silence
  cannot tell "it ran fine" from "it isn't in this scenario" from "the orchestrator never scored it" — three
  different answers to "why didn't it run", only one of which is a constraint. So a named-but-not-blocked id
  reports one of exactly three lines: `ran — N simulations`, `not computed — SafeBreach stopped evaluating
  early`, or `not present in this scenario`. This is **not** `reducing`-constraint analysis, which stays out
  of scope: the tool says the attack ran, not why it ran on fewer simulators than offered.
- **Scope is fully-blocked attacks only** (user decision). `severity: blocking` — an integer `0` count — is
  the whole of this tool's subject. `reducing` conflicts remain reported by nothing in this ticket; they are
  SAF-35484's scope, unchanged by the decomposition.
- **The R1 null rule is inherited, not restated.** Every projection reads the same `counts_computed` flag the
  shaping layer already set, and none of them re-derives zero-ness. On a truncated response
  `get_scenario_blocked_entities` reports **"not evaluated"**, never "nothing is inapplicable" — the two are
  the identical-looking, opposite-meaning pair R1 exists to keep apart, and the decomposition makes the
  distinction *more* load-bearing, because a tool whose entire subject is emptiness must never mistake an
  unmeasured plan for a clean one.
- **Caps apply per question.** Today `ZERO_IMPACT_CAP = 50` truncates with no notion of which attack the
  caller cared about, so a named attack can fall off the list that was supposed to explain it. Filtering to
  the requested ids happens **before** the cap in `get_scenario_attack_blockers`, so a named attack is never
  truncated away by fifty it was not asked about.
- **`both_counts` is carried by all three** and behaves as it does today — two calls, both figures labelled.
  Its value is clearest on the counts tool, where runnable-versus-expected *is* the answer.
- **Registration**: all three `readOnlyHint=True, destructiveHint=False`, and **none** takes a rate-limiting
  gate — the CLAUDE.md gate table stays a table of write tools and is not extended. `get_plan_statistics` is
  unregistered in the same phase, so the studio server's tool count is 13 + 3 − 1 = 15.

---

## 4. API Endpoints and Integration

### Existing API consumed

- **API Name**: Get plan statistics (the orchestrator impact & validation engine)
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
| `getConstraints` | `false` | **`true`** | Populates `simulatorConstraints` **and** `constraintCatalog`; without it both keys are **absent entirely**. Required for AC-7/AC-8 to mean anything, and the reason conflicts can never arrive without their descriptions. |
| `getAllConstraints` | `false` | **`true`** | A **completeness** flag, not a grouping key. `false` chains validators so a simulator records only the *first* reason that eliminated it; `true` runs every validator against the full node set so it records *all* of them, and enables two extra emitters. Console parity. (Its swagger description said "Param to group constraints by" — corrected by SAF-35568 to state these semantics.) |
| `limit` | `0` | **`500000`** | Console parity (`PLAN_SIMULATIONS_STATISTICS_LIMIT`). Compared against the **rendered-move** count, not the simulation count. `0` disables the circuit breaker entirely — and with it the limit-reached path. |
| `useCache` | `true` | **`true`** | Server-side cache. Never sent by the current helper. |

**Request body**: a `ValidatePlan`. Only `name` is required. Per-step scoping via `attacksFilter`,
`attackerFilter` / `targetFilter` (`simulatorsFilter`), `systemFilter`, `successCriteria`, and `draft: true`
for Studio draft custom attacks.

**Response**: `{ data: { steps: StepStatistics[], constraintCatalog?: {...} } }`. `StepStatistics` requires
`simulationCount`, `moves`, `simulators`, `targetSimulators`, `attackerSimulators`; `isLimitReached` and
`simulatorConstraints` are optional. `constraintCatalog` is a **top-level sibling of `steps`**, not a per-step
field: `{ [reasonCode]: { description } }`, present only when `getConstraints=true` and scoped to the codes
that response references. An unrecognised code appears as `{}` (no `description` key), which MCP normalizes to
`description: null`.

SAF-35568 also **typed the previously bare maps**: `moves`, `simulators`, `targetSimulators` and
`attackerSimulators` are now `additionalProperties: {type: number, nullable: true}` — schema confirmation of
the `null`-versus-`0` distinction Component B preserves — and `simulatorConstraints` carries the nested
attacker/target shape below rather than a bare `"type": "object"`. Useful as documentation; MCP still validates
defensively at runtime rather than trusting the schema (R1).

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
    "incompatible_os":      { "description": "OS is incompatible." },
    "incompatible_package": { "description": "Role is incompatible." },
    "simulator_is_offline": { "description": "The simulator is offline and cannot run this move." },
    "move_does_not_require_credentials_simulator_credentials_is_ignored":
                            { "description": "This attack doesn't use AWS credentials, so only the default variant is used." }
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

The four description strings above are the orchestrator's own, relayed verbatim — MCP authors none of them. Note how the
last one earns its place: `move_does_not_require_credentials_simulator_credentials_is_ignored` reads as a
benign note, and the description says what actually happened (only the default variant was used). That is the
gap a caller cannot close from the code name.

`description` is `null` only when the API supplied no entry for that code: a console whose orchestrator
predates SAF-35568 (§9 R11), a `get_constraints=false` call, or a code the orchestrator itself does not recognise. The key
is always emitted rather than omitted, so "not supplied" stays distinguishable from "described as empty", and
a caller can tell it must not present the bare code as an explanation.

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
  "hint_to_agent": "the orchestrator hit its evaluation limit and stopped early: 1 of 3 steps returned, no counts computed. null means not-computed, NOT zero — nothing here indicates any attack or simulator is inapplicable."
}
```

Both zero-impact lists are empty **by construction** when `counts_computed` is false. Compare with step 0
above: an identical-looking "nothing will run", opposite meaning. Conflating the two is risk R1.

---

### The three tools' narrated output (D4)

All three project the same report shape above; the JSON is never the caller-facing artifact, so what follows
is the **markdown each tool returns**. The projections are what make these three views disjoint — none of them
renders a section another one owns.

**`get_scenario_simulation_counts`** — the answer is the number, and the honesty about whether it is one:

```markdown
## Scenario Simulation Counts

**Counts mode:** runnable (`includeDisabled=false`)
**Steps scored:** 3 of 3
**Total simulations:** 1,971

- **Step 0** — 0 simulations. Coverage: 0 of 12 attacks, 0 of 5 target simulators produce simulations.
- **Step 1** — 1,824 simulations. Coverage: 9 of 12 attacks, 5 of 5 target simulators produce simulations.
- **Step 2** — 147 simulations. Coverage: 2 of 12 attacks, 3 of 5 target simulators produce simulations.

**Hint:** these are runnable counts — what would run right now. Offline, disabled and unapproved simulators
are excluded. Call again with include_disabled=true for expected counts; neither is derivable from the other.
```

Note step 0's `0`: the counts tool reports that a step produces nothing, but does **not** say why — that is
`get_scenario_blocked_entities`' question, and the hint routes there. With `get_constraints=False` by default
it has no constraint data to answer with, which is the point rather than a limitation.

**`get_scenario_blocked_entities`** — a yes/no question, so it answers yes or no before it answers anything else:

```markdown
## Scenario Blocked Entities

**Counts mode:** runnable (`includeDisabled=false`) — **Steps scored:** 3 of 3

**Verdict:** 4 attacks and 1 simulator contribute nothing to this scenario.

### Step 0 — 8 of 12 attacks, 4 of 5 target simulators produce simulations
- **Attacks contributing nothing** (4 of 4) — still in the scenario:
  - #9012 (Write EICAR to disk) — blocked by `incompatible_os` (target, 3 sim)
- **Simulators contributing nothing** (1 of 1):
  - e5f6... — `simulator_is_offline` (target, 7 attack(s))

### Constraint catalog
- `incompatible_os` — OS is incompatible.
- `simulator_is_offline` — The simulator is offline and cannot run this move.

**Hint:** these entities remain in the scenario — this tool reports, it removes nothing.
```

The clean case is a first-class answer rather than an empty section: `**Verdict:** nothing is fully blocked —
every attack and simulator in this scenario contributes at least one simulation.` And the truncated case is
neither of those two: `**Verdict:** not evaluated — SafeBreach stopped before scoring 2 of 3 steps, so nothing
here indicates any attack or simulator is inapplicable.` Three outcomes, three sentences, no two of which can
be confused for each other — this is R1 restated where it now matters most.

**`get_scenario_attack_blockers`** — named ids in, dispositions out:

```markdown
## Scenario Attack Blockers

**Counts mode:** runnable (`includeDisabled=false`) — **Steps scored:** 3 of 3
**Asked about:** #9012, #1234, #7777, #4321

### Blocked — did not run anywhere
- **#9012 (Write EICAR to disk)**, step 0 — blocked by:
  - `incompatible_os` (target, 3 simulators) — OS is incompatible. — `{"actual": "LINUX", "required": "WINDOWS"}`

### Not blocked
- **#1234** — ran, 240 simulations in step 1.
- **#7777** — not present in this scenario.
- **#4321** — not computed; SafeBreach stopped evaluating before its step was scored.

**Hint:** only fully-blocked attacks (a count of exactly 0) are analysed. #1234 ran on fewer simulators than
were offered; that is a reduction, not a block, and is not reported here.
```

The **Not blocked** section exists only because ids were named. Called without `attack_ids` the tool lists
every fully-blocked attack and emits no such section at all — there is no caller expectation to correct.

---

## 6. Non-Functional Requirements

**Code reuse**
- Reuses `get_api_base_url(console, 'orchestrator')`, `get_api_account_id(console)`,
  `get_auth_headers_for_console(console)`, `check_rbac_response(response)`.
- Attack-name resolution reuses `_build_attack_name_map(console)` (:2286), which reads the playbook cache via
  `_get_all_attacks_from_cache_or_api`. Names are cosmetic — that helper already degrades to `{}` on failure.
- **Placement splits on generality.** The fetch core is a general orchestrator-API wrapper and lives in
  `safebreach_mcp_core` (§3 B). The constraint-catalog builder/resolver and the zero-impact shaping are
  presentation, live in `safebreach_mcp_studio` alongside their only consumers, and are not vendored
  vocabulary — nothing outside the studio server reads constraint reasons today.

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
- `CONSTRAINT_REASON_DESCRIPTIONS` is superseded by the API-served catalog, not by another local table. Its 14
  strings are **deleted**, and against a console carrying SAF-35568 both existing tools' output gains the orchestrator's
  authoritative `description` for every referenced code — a strict improvement in coverage, though the wording
  for those 14 changes to the orchestrator's. Against an older console those 14 report `description: null` (§9 R11). Only
  `_summarize_constraints` reads the table directly (`:2333`, `:2334`);
  `_summarize_constraints_aggregated` inherits via `:2357`.

**Observability**
Follows the module's existing `logger` usage: one info line per call with step count, console, and the
parameter set actually used, and an error line carrying the full response body on failure.

---

## 7. Definition of Done

**Core functionality**
- [x] `get_plan_statistics` evaluates an **ad-hoc plan body** with no saved scenario. *(AC-1)*
- [x] It also accepts a `scenario_id`, passed to the orchestrator as `{id}` rather than resolved client-side. *(AC-1)*
- [x] A plan with no steps surfaces a typed, explanatory error rather than an unhandled 400. *(AC-1)*
- [ ] The response surfaces per-step `simulationCount`, per-attack `moves`, and per-simulator `simulators`,
      `attackerSimulators` and `targetSimulators` counts, plus `isLimitReached` and structured constraints. *(AC-2)*
- [ ] `limit`, `includeDisabled`, `getConstraints`, `getAllConstraints` and `useCache` are all pass-through
      with the documented defaults in §4. *(AC-2)*
- [x] Runnable counts are returned by default (`includeDisabled=false`); expected counts are available; a
      both-counts mode issues both calls and labels each result; the response states that expected cannot be
      derived from a runnable response. *(AC-3)*
- [ ] Numbers match the console per view and per parameter set — Add Simulators Checkout tab with
      `includeDisabled=true, getConstraints=true`, and run gating with `includeDisabled=false`. *(AC-4)*
- [ ] When `isLimitReached` is true the tool reports it explicitly, preserves `null` (not computed) versus `0`
      (runs nowhere), surfaces that the returned step list is shorter than the plan's, and performs no
      zero-impact reporting. *(AC-5)*
- [x] `plan/statistics` is called from exactly one place in the repo — `safebreach_mcp_core/plan_statistics.py`;
      `_get_scenario_statistics` and its two callers route through it rather than forming a parallel
      implementation. *(AC-6)*
- [x] That fetch core ships in `safebreach_mcp_core` as a shared primitive: no studio-specific types in its
      signature or return value, and importable by any server as `queue_state` already is. *(AC-6, §3 B)*
- [x] `CONSTRAINT_REASON_DESCRIPTIONS` is **deleted**, including its 14 existing entries. No constraint
      meaning — and no `fix_lever` map either — is vendored in this repo. *(AC-7)*
- [ ] `constraint_catalog` is filled from the response's own `constraintCatalog`, with code keys and
      `description` text relayed **verbatim**. A test fails if MCP re-words, truncates, or substitutes a
      description. *(AC-7)*
- [x] No `description` is fabricated for any code. Meanings are the orchestrator's, served per response by SAF-35568; a
      code the API does not describe reports `description: null`. *(AC-7, §9 R9)*
- [x] An absent `constraintCatalog` — a console predating SAF-35568, or `get_constraints=false` — degrades to
      `description: null` for every code with the conflicts still surfaced, and never raises. *(AC-7, §9 R11)*
- [x] Conflicts are returned **normalized** — a `constraint_catalog` of the codes present in the response, plus
      per-conflict references carrying only `severity`, `attack_id`, `side`, `simulator_count` and `values`. *(AC-8)*
- [x] `severity` is **computed** from the counts alone — `blocking` when the attack's count is an integer `0`,
      `reducing` when it still runs — consulting no vocabulary metadata. *(AC-8)*
- [ ] Every conflict is surfaced — an unrecognised code resolves to `description: null` and is still reported,
      never dropped and never given an invented meaning. *(AC-8)*
- [ ] When a meaning is **not supplied**, the response says so with an explicit `null` rather than omitting the
      key, so a caller can tell "no description available" from "described as empty" and does not present the
      bare code as an explanation to a user. *(AC-8, §9 R9, R11)*
- [ ] An attack with `moves[id] === 0` is **reported** as inapplicable with a plain-language explanation of why
      it runs nowhere; reporting does not block save, and a `null` value is never reported as zero-impact. *(AC-9)*
- [ ] A simulator with `simulators[id] === 0` is **reported** the same way, read from the **union** `simulators`
      map rather than a single role map. *(AC-10)*
- [ ] The tool performs no caching of its own, so any change to an earlier decision produces a fresh call. *(AC-11)*
- [ ] ~~Registered as `get_plan_statistics` with `readOnlyHint=True`~~ — **superseded by D4**: registered as
      **three** read-only tools (see the decomposition block below), and documented in the CLAUDE.md tool
      catalog. The rate-limiting gate table is **not** extended — read-only tools are outside that contract.
      AC-12's substance (read-only registration + catalog entry) is unchanged; only the count and the names
      move. *(AC-12, D4)*

**Tool decomposition (D4, phases 7–9)**
- [ ] Three tools are registered, each answering one question and rendering only its own slice:
      `get_scenario_simulation_counts`, `get_scenario_blocked_entities`, `get_scenario_attack_blockers`. All
      three are `readOnlyHint=True, destructiveHint=False` and take **no** rate-limiting gate. *(D4)*
- [ ] `get_plan_statistics` is **unregistered** as an MCP tool. `sb_get_plan_statistics` survives unchanged as
      the shared plumbing all three call, so AC-6 still holds: exactly one `plan/statistics` call site. *(D4, AC-6)*
- [x] Each tool projects the shipped report through a **pure** function — no second fetch path, no duplicated
      zero-impact, severity, cap or null-safety logic. A test asserts the three tools produce their answers
      from one `sb_get_plan_statistics` call each. *(D4)*
- [x] All three carry the full parameter surface (`console`, `scenario`, `scenario_id`, `test_id`,
      `include_disabled`, `both_counts`, `get_constraints`, `get_all_constraints`, `limit`, `use_cache`,
      `conflict_detail`); only the defaults differ, and only where the question differs. *(D4)*
- [x] `get_scenario_simulation_counts` defaults `get_constraints=False` — it renders no conflicts, so it does
      not pay for them — and the parameter is still exposed for a caller who wants the pass. *(D4)*
- [x] `get_scenario_blocked_entities` answers its yes/no question with an explicit verdict in all
      states, none of which can be read as another: entities are blocked, nothing is blocked, nothing is blocked
      *among the steps that were measured*, only some steps were scored, or nothing was evaluated. Neither
      the truncated state nor a capped map ever reports an empty list as a clean scenario. *(D4, AC-5, §9 R1)*
- [x] `get_scenario_attack_blockers` accepts optional comma-separated `attack_ids`. Supplied, every named id
      that is **not** blocked gets exactly one disposition line — ran with N simulations, not computed, or not
      present in this scenario — so silence never stands in for an answer. Omitted, it reports every
      fully-blocked attack and emits no disposition section. *(D4)*
- [x] Filtering to the requested ids happens **before** the `ZERO_IMPACT_CAP` truncation, so a named attack is
      never dropped from the list that exists to explain it. *(D4)*
- [x] Only fully-blocked attacks (an integer `0` count) are analysed; `reducing` conflicts stay out of scope
      and the hint says so, rather than the tool being silently narrow. *(D4)*
- [ ] Caller-facing vocabulary is **scenario**, not plan: tool names, parameter names, tool descriptions and
      the CLAUDE.md catalog. The ad-hoc-body parameter is `scenario`. Shipped internals
      (`fetch_plan_statistics`, `_build_plan_statistics_report`, `sb_get_plan_statistics`) keep their names —
      they name the API, which genuinely is `plan/statistics`. *(D4)*
- [ ] CLAUDE.md entry 25 is replaced by three entries, and the rate-limiting gate table is **not** extended. *(D4, AC-12)*
- [ ] The registration and e2e tests that named the retired tool (T-24…T-27, T-28…T-31, T-40) are retargeted
      rather than deleted, and the manual tests still owed (T-32, T-33, T-35) are re-aimed at the tool that now
      answers their question — T-35 at `get_scenario_simulation_counts`. *(D4, §9 R14)*

**Quality gates**
- [ ] Every test in `test-plan.md` for this feature is green, with evidence in `test-results/`.
- [ ] `sb_quick_run` and `sb_run_scenario` are verified behaviourally unchanged.
- [ ] A test asserts descriptions are relayed verbatim, and that an absent or partial catalog degrades to
      `description: null` with conflicts intact. No vendored-vocabulary coverage guard exists to maintain,
      because no vocabulary is vendored. *(AC-7)*
- [ ] CLAUDE.md tool catalog updated.

**Deployment readiness**
- [ ] No feature flag, migration, or infrastructure change — additive read-only tool.
- [ ] No orchestrator change.

---

## 8. Implementation Phases

| Phase | Status | Completed | Commit SHA | Notes |
|-------|--------|-----------|------------|-------|
| Phase 1: Relay the orchestrator's constraint catalog (delete vendored table) | ✅ Complete | 2026-08-27 | 1a69fe0 | Scope extended with user approval: `fixable` dropped with the table; `studio_server.py` renderer guarded against the now-nullable `description`; `CLAUDE.md` constraint-diagnostics wording corrected. T-39's Phase-4 clauses deferred — see §8 Phase 4. |
| Phase 2: Raw fetch core | ✅ Complete | 2026-08-27 | 4dadfd1 | Relays the response-root `constraintCatalog` as `constraint_catalog` — not in §8's Outputs list, but required so Phase 3 does not regress Phase 1's relay. `Environment needs: repo-harness` is wrong for T-6…T-12 (all mock the transport) — ran as uv-pytest. |
| Phase 3: Refactor summariser onto the core | ✅ Complete | 2026-08-27 | d53320b, a49190e | AC-6 satisfied. Three crash sites, not the two §8 names — `sum(counts)` in the log line was the third. Scope extended with user approval: both callers' `sum(step_counts)` also had to be guarded, or the crash simply moved one frame up. |
| Phase 4: Translation + zero-impact reporting layer | ✅ Complete | 2026-08-27 | 58d7a29 | Four owner-approved deviations from §4's response example, which needs correcting — see the change log. `summary`/`per_attack` differ only by name resolution, because T-23 requires `attack_id` on every conflict. |
| Phase 5: Public function + tool registration | ✅ Complete | 2026-08-27 | 1714dba, 900db94 | All 32 cumulative tests green. The five e2e tests executed against `zircon-piculet` with **zero skips** after the `scenario_id` fix — see `test-results/phase-5.md` Addendum. |
| Phase 6: Documentation | ✅ Complete | 2026-08-27 | 31afb33 | Catalog entry 25 added; the rate-limiting gate table deliberately unchanged. T-34's gate-table half was green before and after — it guards an omission. |
| Phase 7: Three question projections + public functions (D4) | ✅ Complete | 2026-09-03 | 2ed9a3b, 1c4f5c2 | 1873 passed / 0 failed; the 1771 pre-existing all untouched. **Six review rounds, nine severity-6/7 defects**, every one an instance of the same fault: three aggregations of "what is blocked" that could disagree over one scoring. Now one shared rule. Scope extended twice with owner approval — `_build_plan_statistics_report` (a pre-existing catalog defect the split made load-bearing) and four plan tests added at the planning gate. Three regressions were introduced by earlier rounds' own fixes and caught by later rounds. |
| Phase 8: Three narrators, three registrations, retire `get_plan_statistics` (D4) | ⏳ Pending | — | — | The only phase that changes the MCP surface: 13 tools → 15. T-24…T-27, T-28…T-31 and T-40 are **retargeted, not deleted**; the 31 `sb_get_plan_statistics` references stay untouched by design. |
| Phase 9: Documentation (D4) | ⏳ Pending | — | — | CLAUDE.md entry 25 → three entries. Gate table deliberately unchanged, as in Phase 6. |

### Phase 1 — Delete the translation table; relay the orchestrator's catalog

**Semantic change**: Remove the vendored constraint meanings entirely and fill the catalog from the API
response instead. MCP ends this phase vendoring no constraint vocabulary at all.

**Deliverables**: `CONSTRAINT_REASON_DESCRIPTIONS` deleted; a catalog builder that reads `constraintCatalog`
off the raw response; a resolver that returns the API's description or `null` and never authors a meaning.

**Implementation details**
- **Delete `CONSTRAINT_REASON_DESCRIPTIONS` (`:2225`) outright**, all 14 entries. Do not carry any of them
  forward. Output becomes uniform across every code the API describes rather than 14 special cases, and MCP
  stops asserting meanings it is not the source of.
- **Add no replacement map** — no lever map, no partial table, not even "just the misleading ones". The catalog
  is built per response, so there is no vendored artifact to keep in step with upstream and no coverage guard
  to maintain. This is the whole point of the phase; adding a "temporary" local map would recreate exactly the
  pressure-release valve §3 Component A rejects.
- Build the catalog by intersecting the response's `constraintCatalog` with the codes MCP's own normalized
  conflict list emits, preserving each `description` **verbatim**. Read it from the top level of the response
  body, not from a step.
- Introduce a resolver used by every consumer: given a code and the response's catalog it returns
  `{description}` — the orchestrator's string, or `null` when the catalog has no entry (or an entry with no `description`,
  which is how the orchestrator represents a code it does not itself recognise). On an unknown code the conflict is still
  reported. It **never** returns the code as an explanation and never fabricates a meaning. Replaces
  `...get(code, {}).get('description', code)` at `:2333`.
- **Repoint one function, not two.** `_summarize_constraints` (:2299) is the *only* direct reader — the table is
  referenced at exactly `:2333` and `:2334`, both inside it. `_summarize_constraints_aggregated` (:2350)
  consumes it transitively at `:2357` and inherits the change automatically.
- **This changes shipped output** for `quick_run` and `run_scenario` previews, in both directions. Against a
  console carrying SAF-35568 the 14 codes that had vendored prose now show the orchestrator's wording instead, and the
  other 83 gain a description they never had. Against an older console all of them report `description: null`
  — the bounded regression in §9 R11. Not a contract break either way: the key set is unchanged and
  `description` is nullable by design.

**What can go wrong**: treating an absent `constraintCatalog` as an error rather than as `description: null`
breaks the tool outright against every console that has not taken SAF-35568. Reading the catalog from a step
rather than the response root silently yields an empty catalog on every call. "Improving" a relayed
description recreates the third copy this design deletes, on a slow drift path no test would catch. And a
resolver that falls through to the code violates AC-8 — `incompatible_package` is a *role* mismatch,
`*_is_ignored` is variant de-duplication, so the code name misleads precisely where it matters most.

**Changes**

| File | Description |
|---|---|
| `safebreach_mcp_studio/studio_functions.py` | Delete `CONSTRAINT_REASON_DESCRIPTIONS` (:2225); add the response-catalog builder + resolver; repoint `_summarize_constraints` (:2333-:2334) |

**Git commit**: `feat(studio): relay the orchestrator's constraint catalog, delete vendored descriptions`

### Phase 2 — Raw fetch core

**Semantic change**: Introduce the single, fully-parameterised, null-safe call site for `plan/statistics`.

**Deliverables**: `safebreach_mcp_core/plan_statistics.py`, exposing `fetch_plan_statistics`.

**Implementation details**
- **Inputs**: `console`; either a plan body or a `scenario_id`; the five query parameters; nothing else.
- **Body construction**: a caller-supplied body is used as-is, defaulting `name` to `""` when absent. A
  `scenario_id` becomes `{"name": "", "id": <scenario_id>}` — a passthrough, because the controller resolves
  `id` or `testId` itself. Never populate `planId`; the controller ignores it.
- **Steps**: reject a body with no steps **before** the HTTP call, with a typed error explaining that the orchestrator
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
| `safebreach_mcp_core/plan_statistics.py` | **New file** — add `fetch_plan_statistics` (module docstring with a Usage block, per `queue_state.py`) |

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
| `safebreach_mcp_studio/studio_functions.py` | Rewrite `_get_scenario_statistics` (:2400) body onto `fetch_plan_statistics`, imported from `safebreach_mcp_core.plan_statistics` |

**Git commit**: `refactor(studio): route _get_scenario_statistics through the fetch core`

### Phase 4 — Translation + zero-impact reporting layer

**Semantic change**: Turn a raw statistics response into the caller-facing report.

**Deliverables**: a per-step shaping function producing translated constraints and zero-impact lists.

**Implementation details**
- **Normalize conflicts**: walk `attackerConstraints` and `targetConstraints` treating the map as **sparse**
  and each leaf as an **array**. Group by `(attack_id, code)`, merging the two sides and recording which
  side(s) and how many simulators produced each — never one row per simulator. Emit a `constraint_catalog`
  containing one entry per code **present in this response**, built by Phase 1's builder from the response's
  own `constraintCatalog` (verbatim descriptions; `null` where the API supplied none); each conflict references
  the catalog by `code` and carries only `severity`, `attack_id`, `side`, `simulator_count` and the API's
  `values`. Attach attack names where resolvable, degrading silently.
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

### Phase 7 — Three question projections and their public functions

**Semantic change**: The report stops being the only answer. Three pure projections select the slice each
question needs, and three public functions expose them. Nothing is registered yet, so the MCP surface is
unchanged at the end of this phase and every existing test still passes untouched.

**Deliverables**: `_project_simulation_counts`, `_project_blocked_entities`, `_project_attack_blockers` in
`studio_functions.py`, plus `sb_get_scenario_simulation_counts`, `sb_get_scenario_blocked_entities` and
`sb_get_scenario_attack_blockers` that call `sb_get_plan_statistics` and project its result.

**Implementation details**
- Each projection is a **pure function of the report dict** — no console, no I/O, no transport seam. This is
  the same property Phase 4's shaping layer has, and the reason both are testable against a literal dict.
- `_project_simulation_counts` keeps `counts_mode`, `plan_step_count`, `returned_step_count`, `truncated`,
  `params_used`, and per step its `step_index`, `simulation_count`, `counts_computed`, `is_limit_reached` and
  the three coverage denominators. It drops `conflicts`, both zero-impact lists and `constraint_catalog`.
- `_project_blocked_entities` keeps both zero-impact lists with their blockers plus the coverage lines, and
  narrows `constraint_catalog` to **only the codes those blockers cite** — a catalog listing codes no reported
  blocker references would be padding on a tool whose whole job is a short answer. It drops the conflicts
  list, which carries the `reducing` rows that are not this question's subject.
- `_project_blocked_entities` also computes the **verdict** in mutually exclusive states, decided
  from `counts_computed` and **never** from list emptiness (the lists are empty by construction on an
  unscored step): blocked, clean, **clean-where-measured**, **partially-evaluated**, or not-evaluated.
  *Revised during Phase 7 — this
  clause specified three states, and a code review reproduced the gap: a report with one step scored clean
  and one never scored fell through to `clean` and asserted that every attack and simulator in the scenario
  contributes at least one simulation — a blanket claim over unmeasured steps, and the same silent
  over-claim the execution side refuses. The fourth state reports findings over the scored steps only.
  Pinned by T-53.*
- `_project_attack_blockers` takes the parsed id list. For each id it resolves one disposition in this
  order: **ran** (an integer > 0 anywhere), **blocked** or **blocked-where-measured** (an integer `0`),
  **not computed** (`None`), **count-map-truncated**, **absent**. *Revised during Phase 7 — this clause
  ordered blocked before ran, which would file an attack scored `0` in one step and 240 in another under a
  heading reading "did not run anywhere", making the answer depend on which step the scenario lists first.
  Pinned by T-49.* Blocked ids carry their blockers from `zero_impact_attacks`; the others carry one line each.
- **A capped map answers "unknown", never "no".** The counts map is truncated at `COUNT_MAP_CAP` by ascending
  id, so an id's absence from it means the map stopped before reaching that id — not that the step lacks it.
  Every scenario-wide judgement therefore distinguishes *confirmed* from *unconfirmable*: an id a truncated
  map might be hiding a positive count for resolves to **`blocked_where_measured`** rather than `blocked`, and
  a report with no confirmed blockage but some unconfirmable entity yields the verdict
  **`clean_where_measured`** rather than the flat clean claim, stating how many entities it could not vouch
  for. An entity named in a step's own zero-impact list is accounted for in that step and stays plainly
  blocked. *Added during Phase 7 — a review reproduced an attack that ran 240 times being reported as
  contributing nothing, because "ran anywhere" was read from the capped map. This is the null-versus-zero
  rule applied to the map as well as to the counts inside it. Pinned by T-54.*
- **Filtering precedes capping, and neither cap implies the other.** `zero_impact_attacks` is capped at
  `ZERO_IMPACT_CAP = 50` and the `attacks` count map at `COUNT_MAP_CAP = 100`, and an id can fall outside
  either one independently: blocked with no entry to explain it, or fully explained while sorting out of the
  counts map entirely. The disposition is therefore resolved from the **union** of both, with the zero-impact
  entry itself taken as proof of an integer `0`. *Revised during Phase 7 — reading only the counts map made
  this tool report "can't tell" about an attack whose full blocker list was in hand, and return an empty
  blocked list on a scenario where the blocked-entities tool, from the same scoring, correctly said
  "blocked".* Whether the counts map is whole is a fact about the map, not about the counts in it, so it is
  established even on a step nobody scored — an absent id and a truncated-away id are different answers.
- `attack_ids` parsing reuses the comma-separated-integer convention `sb_quick_run` already implements;
  invalid input raises `ValueError` with the offending token, as that function does.
- The three public functions pass every parameter through to `sb_get_plan_statistics` unchanged, except that
  `sb_get_scenario_simulation_counts` defaults `get_constraints=False`.

**Changes**

| File | Description |
|---|---|
| `safebreach_mcp_studio/studio_functions.py` | Three projections + three public `sb_*` functions |
| `safebreach_mcp_studio/tests/test_studio_functions.py` | Projection unit tests against literal report dicts |

**Git commit**: `feat(studio): project the scenario statistics report into three question-shaped answers`

---

### Phase 8 — Three narrators, three registrations, and the retirement

**Semantic change**: The MCP surface changes. Three tools appear, one disappears, and the studio server's tool
count goes from 13 to 15.

**Deliverables**: three narrators in `studio_server.py`; three `@self.mcp.tool` registrations; the
`get_plan_statistics` registration removed; the tests that named it retargeted.

**Implementation details**
- Each narrator renders **only its own sections**, per §4. They share the existing null-safe helpers
  (`_format_count`, `_format_simulation_count`, `_coverage`, `_shown_of`, `_render_constraint_reason`) rather
  than restating the null rule three more times.
- Tool descriptions must make the three **mutually exclusive to a reading model**. Each opens by naming the
  one question it answers and pointing at its siblings for the other two — the failure mode being guarded
  against is a model reaching for the blocked-entities tool to get a count (§9 R13).
- **Delete the `get_plan_statistics` registration**, its description block, and `_format_plan_statistics` /
  `_format_one_report` / `_format_statistics_step` **only if** no narrator reuses them; where a narrator does,
  the helper stays and the tool-level entry point goes. `sb_get_plan_statistics` and everything below it is
  **not** touched.
- **Retarget, do not delete, the tests that named the tool.** T-24…T-27 (registration) assert the three new
  names, the retired one's absence, and that none of the three references the rate limiter. T-28…T-31 and T-40
  (e2e) re-aim at whichever of the three answers their assertion: T-28's shape at all three, T-29's by-id
  agreement and T-30's `includeDisabled` inversion at `get_scenario_simulation_counts`, T-31's typed error at
  all three (it is raised in the shared plumbing), T-40's verbatim relay at `get_scenario_blocked_entities`,
  which is now the tool that renders the catalog.
- The 31 references to `sb_get_plan_statistics` in `test_studio_functions.py` and `test_rate_limiting.py`
  **are not touched** — the function is unchanged, and that is the property this phase must preserve.

**Changes**

| File | Description |
|---|---|
| `safebreach_mcp_studio/studio_server.py` | Three narrators + three registrations; `get_plan_statistics` unregistered |
| `safebreach_mcp_studio/tests/test_studio_functions.py` | Registration tests retargeted to the three names |
| `safebreach_mcp_studio/tests/test_e2e_plan_statistics.py` | e2e cases re-aimed at the tool that answers each |

**Git commit**: `feat(studio): three scenario-statistics tools replace the single reporting tool`

---

### Phase 9 — Documentation

**Semantic change**: The tool catalog stops describing a tool that no longer exists.

**Implementation details**: replace CLAUDE.md's Studio Server entry 25 with three entries — one per tool —
each stating the question it answers, its parameter surface, its default `get_constraints`, and the
null-means-not-computed rule. Say explicitly that `get_plan_statistics` is retired and that the three replace
it, so a reader of the catalog does not go looking. The rate-limiting gate table stays untouched: all three
are read-only and take neither gate, which is a property to preserve rather than create.

**Changes**

| File | Description |
|---|---|
| `CLAUDE.md` | Entry 25 replaced by three entries; gate table deliberately unchanged |

**Git commit**: `docs: replace the plan-statistics catalog entry with the three scenario tools`

---

## 9. Risks and Assumptions

### Technical risks

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| **R1** | **Misreading a limit-reached response.** The controller returns a sentinel step with `simulationCount: null` and **every** `moves[id] = null`, and returns early so the step list is shorter than the plan's. Treating falsy as zero, or assuming positional alignment, would report the user's entire selection as zero-impact. | **High** | Integer-`0` predicate everywhere; zero-impact reporting suppressed entirely when counts are not computed; truncation reported explicitly (AC-5). Severity is reduced from the original ticket by D3 — the tool now only *reports*, so the worst case is a wrong report rather than a destroyed configuration. |
| **R2** | **Regressing the two existing callers.** 58 test references, ~20 with hardcoded `@patch` return values, plus `sb_quick_run` and `sb_run_scenario`. | **High** | Contract-preserving layering (§2); `includeDisabled=true` and `limit=500000` passed explicitly in Phase 3; Phase 3's intended visible delta is zero. |
| **R3** | **Vendored-catalog drift — measured, not hypothetical, and now avoided entirely.** The vocabulary lives in `orchestrator`, on a different release cadence. The console has been vendoring the same vocabulary for years in `ui-react/src/containers/Studio/utils/constants.ts:166` and has demonstrably drifted **in both directions**: **3 dead entries** for codes orchestrator no longer emits (`incompatible_simulator_version`, `assume_role_incompatible_simulator_version`, `move_does_not_support_simulation_user_and_simulator_does_not_allows_default_system_user`), and **31 codes** it cannot translate at all, plus 4 explicitly commented out. | **Closed** (was Medium-High) | Eliminated structurally by relaying: MCP vendors no vocabulary at all — no meanings, no levers — so there is nothing to drift and no coverage guard to keep honest. The catalog arrives in the same payload as the codes it explains, so it cannot describe a different vintage than the response. The residual is not drift but **absence** on a console predating SAF-35568 — tracked as R11. |
| **R4** | **"Matches the console" is not one number.** Checkout uses `includeDisabled=true`, run gating `false`. | **Medium** | AC-4 is per-view and per-parameter-set; §4 tabulates which parameters correspond to which view. |
| **R5** | **Cost of correctness.** `getAllConstraints=true` disables the validator short-circuit; both figures need two round trips, against a 120 s timeout. | **Medium** | Runnable default is one call; the second is opt-in (D2); every parameter is overridable for a cheap count-only call. |
| **R6** | **Vendoring by key rather than by value** would ship two impossible codes, miss two real ones, and still pass a naive count-based coverage test. | **Closed** | Resolved twice over. Upstream: SAF-35568 renamed both mismatched keys at source and deleted 5 dead ones, so `constraints.js` is now 1:1 (97 codes, 24 groups). Here: MCP enumerates nothing, so it has no local list to key wrongly — the relay keys off what the response actually contains. Retained as the record of *why* the catalog is built from the response rather than a local enumeration. |
| **R7** | **A remedy inferred from a code's name rather than its emit site sends someone down a dead end.** `*_is_ignored` reads like a setting the user could change, when in fact it is variant de-duplication and nothing the caller controls affects it. The console shows this trap in production — it renders that one family three inconsistent ways ("… are not supported" / "… are ignored" / "Select a non-service account"). | **Low** (was Medium) | No longer MCP's exposure. `fixLever` was dropped upstream as redundant relative to `description` (SAF-35568 Phase 5) and no lever is vendored here, so MCP asserts **no remedy at all** — it cannot assert a wrong one. The relayed description carries the emit-site meaning, authored and reviewed at source, and the caller derives the remedy from it plus the `step_overrides` schema. Residual: a caller can still misread a description, but the text is the orchestrator's rather than MCP's inference. |
| **R8** | **Asserting severity per code** instead of computing it from the attack's count would label every `reducing` conflict a blocker — pulling SAF-35484's partial-impact scope into this ticket by accident and over-reporting zero-impact attacks. | **Medium** | Severity is derived in Phase 4 from `attacks[attack_id]` alone; the catalog holds no severity-like field to be tempted by. Covered by a test asserting the same code resolves `blocking` and `reducing` within one step. |

| **R9** | **Meanings are not MCP's to supply, so their availability is someone else's deployment.** Deleting the table removes the 14 descriptions two shipped tools display today. If the API supplied nothing, a caller would be left rendering from the code — and the code names mislead (`incompatible_package` is a *role* mismatch; `*_is_ignored` is variant de-duplication), so the explanation would be wrong exactly where it matters most. | **Low** (was Medium-High) | Resolved by SAF-35568 shipping: every code a response references now arrives with an authoritative `description`, at full coverage rather than the 14-of-97 MCP vendored — a net gain of 83 codes that previously leaked raw. The 14 change wording (to the orchestrator's) rather than losing it. What remains is the version-dependent case, split out as R11. |
| **R10** | **SAF-35568 was on Stage 1's critical path** — MCP had no meanings of its own to fall back on. | **Closed** | Delivered. `constraintCatalog` ships `{ description }` per referenced code, gated on `getConstraints=true`. Two details of *how* it landed matter here and are handled: it shipped **without** the `fixLever` half (removed as redundant), which is why this PRD carries no lever map; and the localization question it flagged was **deferred, not answered**, which does not block MCP — the relay is agnostic to which string the orchestrator serves (§10). |
| **R11** | **Console-version straddle.** MCP talks to consoles on their own upgrade cadence. One whose orchestrator predates SAF-35568 returns no `constraintCatalog`, so every conflict reports `description: null` — including the 14 that carried vendored prose before this ticket. This is the residue of R3/R9, and it is a real (if bounded) regression on those consoles. | **Medium** | Designed for rather than discovered: the absent-catalog path is the *same* `description: null` contract as an unrecognised code, so it degrades instead of raising, and the conflict is always still surfaced. `hint_to_agent` states when no catalog was supplied, so a caller says *"a compatibility conflict was reported"* rather than guessing from the code name. Self-resolving as consoles take the orchestrator change, and cheap to verify — one field's presence. |
| **R12** | **Retiring a shipped tool is a breaking change for whoever already calls it.** `get_plan_statistics` is registered, documented as CLAUDE.md entry 25, and has been exercised live against `zircon-piculet`. Any Helm prompt, saved Claude Desktop conversation or client config naming it breaks silently — an MCP client gets "unknown tool", not a redirect. | **Medium** | The retirement is a deliberate user decision (D4), not a side effect, and is confined to Phase 8 so it is bisectable on its own. The three replacements ship in the same phase, so there is no window with no answer to the question. CLAUDE.md states in Phase 9 that the tool is retired **and** which three replace it, so the catalog redirects rather than merely omitting. The tool is weeks old and internal-only — its only documented consumer is Helm, whose prompts are updated with it. |
| **R13** | **Three tools competing for one question is a new failure mode the single tool did not have.** A model asked "how many simulations?" can plausibly reach for `get_scenario_blocked_entities`, get a verdict and no total, and either answer wrongly or burn a second call. Decomposition trades a mining problem for a selection problem. | **Medium** | Each description opens by naming the one question it answers and points at its siblings for the other two, so the routing information is in the tool the model is reading rather than only in the catalog. The narrations reinforce it: the counts tool's step-0 line routes explicitly to the blocked-entities tool for *why*, and the blockers tool's hint says what it does **not** cover. Selection is checked by T-24…T-27's description assertions rather than left to prose review. |
| **R14** | **The tests still owed are aimed at a tool that will not exist.** T-32, T-33 and T-35 are Manual and have never run; T-35 is the only check in the whole plan that the numbers match what the console itself displays, and it is written against `get_plan_statistics`. Retiring the tool before running them could quietly convert "never verified" into "no longer verifiable". | **Medium** | Phase 8 retargets rather than deletes, and §7's decomposition block makes the re-aiming a checked item: T-35 lands on `get_scenario_simulation_counts`, which is the tool that now reports the numbers it compares. AC-4 stays **unchecked** either way — the decomposition does not discharge it, and this PRD must not let a refactor look like verification. |


### Assumptions under question

- **MCP no longer depends on the code list being complete or current** — it relays whatever the response
  describes, so a code added upstream tomorrow arrives already explained. For reference, the shipped vocabulary
  is **97 codes across 24 groups, keys 1:1 with emitted values**, measured against SAF-35568's
  `constraints.js` (its Phase 6 invariant: 102 declared keys − 5 dead = 97; 101 distinct emitted values − 4 =
  97). Note that SAF-35568's own narrative sections still quote the pre-implementation estimate of **88**,
  inherited from this PRD's earlier drafts; **97** is the implementation-verified figure and the one used
  throughout here.
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
  plan/statistics response: delivered, and consumed by this PRD rather than anticipated by it.** Recorded here
  because it began as this section's follow-up and moved onto the critical path (R9, R10) once the vendored
  table was deleted; it is no longer an enhancement. The orchestrator's response now carries a `constraintCatalog` mapping
  each code **referenced in that response** to `{ description }`, gated on `getConstraints=true` — in the
  response rather than behind a new endpoint, so there is no second round trip and no way for the catalog to
  fall out of sync with the response it explains. It deliberately carries **no `severity`** (a function of the
  counts the consumer already has, and it would drift from them) and **no `kind`** (there is no informational
  class — all 97 eliminate).

  **Two things landed differently than this section predicted**, both absorbed above rather than left as
  surprises. It ships **no `fixLever`**: one was implemented and then removed on review as redundant relative
  to `description`. The camelCase↔snake_case lever rename this section reserved is therefore moot, and MCP
  vendors no lever map either — see §2's alternatives and §3 Component A. And the vocabulary is **97 codes
  across 24 groups with keys 1:1 with emitted values**, not 88 with two key/value mismatches: SAF-35568 fixed
  both spellings at source and deleted 5 dead keys, which closes R6 upstream.

  **What actually landed here.** MCP vendors nothing: no table, no lever map, no coverage guard. Because this
  PRD had already normalized conflicts into a catalog plus references, adopting the API's catalog changed
  **only where the catalog is filled from** — the tool's response contract is unaffected, and no change outside
  Phase 1 was needed. The one adaptation is the wrapper-key rename (`constraintCatalog` → `constraint_catalog`).

  **Localization remains open**, and is now the only unresolved question from that ticket. Descriptions are
  user-facing prose the console may want localized, and the orchestrator currently serves one English string per code;
  SAF-35568 deferred the decision to its own follow-up rather than answering it. MCP is unaffected by the
  outcome — the relay passes through whatever string arrives — but a caller rendering for a non-English user
  should treat the text as English until that is settled.
- **Config server resolving its own indeterminate attack counts.** `config_types.py:351-358` currently returns
  `total_attack_count: None` for criteria-based steps and hints the agent to run a scenario to find out. With
  the fetch core in `safebreach_mcp_core` (§3 B) that server can import `fetch_plan_statistics` and answer it
  directly — no promotion, no migration, just an import. Left out of this ticket because it changes
  `get_scenarios`' cost profile (a statistics call per indeterminate scenario) and so deserves its own decision.
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
- **What was built**: `get_plan_statistics`, a read-only MCP tool over the orchestrator's `plan/statistics` endpoint. It
  accepts an ad-hoc plan body (or a `scenario_id`), exposes every query parameter, and returns per-step
  simulation, attack and simulator counts, constraint conflicts explained by the orchestrator's own catalog, and a
  zero-impact report. The
  existing private helper is refactored to route through the same code, so exactly one path to the endpoint
  exists.
- **Key technical decisions**: layer rather than rewrite, because 58 test references and two shipped tools
  depend on the existing helper's shape; runnable counts by default, since `includeDisabled=false` is the only
  setting that explains the gap; no MCP-side cache, because stale impact numbers are the exact failure being
  fixed; and **MCP returns structure, Helm narrates** — the vendored translation table is **deleted** rather
  than extended, because vendoring is a pressure-release valve that has already let `ui-react`'s copy rot for
  years. MCP vendors nothing in its place: constraint descriptions are relayed from the `constraintCatalog`
  The orchestrator now serves in the same response ([SAF-35568](https://safebreach.atlassian.net/browse/SAF-35568)), so
  there is no local vocabulary to drift and no `fix_lever` map — that half was built upstream and removed as
  redundant relative to the description. `severity` is computed from the counts rather than stored, and the
  conflict list is normalized into a catalog plus references, which is what made adopting the API's catalog a
  change of source rather than of contract.
- **Scope changes**: the constraint-description authoring work is **out** — SAF-35568 was a **dependency**
  rather than a follow-up (§9 R9/R10) and has since delivered, so MCP relays meanings instead of owning them.
  The trade that once cost 14 codes their descriptions now nets **83 codes gaining one**, with the loss
  confined to consoles whose orchestrator predates that change (§9 R11). Earlier, ACs 9/10 were **reworded** from "auto-removed" to "reported" (D3) — a statistics call
  reports what will and will not run; acting on that report is the plan-holder's job, and is now explicitly
  out of scope on the ticket. All 12 ACs are delivered. The *act* of removal still needs an owner (§9).
- **Business value delivered**: unblocks parent DoD items 2 and 5; gives Helm a non-destructive impact
  primitive it can call after every changed decision; and fixes three live defects — disconnected simulators
  counted as runnable, 83 of 97 conflict reasons leaking as raw `snake_case`, and a `TypeError` crash on large
  scenarios.

---

## 13. Change Log

| Date | Change Description |
|------|-------------------|
| 2026-09-03 | **Phase 7 complete (`2ed9a3b`, `1c4f5c2`).** Three pure projections plus their public functions; nothing registered, so the MCP surface is unchanged and all 1771 pre-existing tests pass untouched (1873 total, 0 failed). **Six review rounds surfaced nine severity-6/7 defects, and they were all one fault**: three aggregations answering "what is blocked" — the verdict, the listing, and the per-id disposition — that could disagree about a single scoring. They now share one rule. The individual symptoms, in the order found: `clean` asserted over steps nobody scored; a blocked attack past `ZERO_IMPACT_CAP` reported `absent` while its blocker list sat in hand; an empty blocker list reading as "the console found no reason" when none was requested or detail was truncated; a false "listing is partial" hint from comparing distinct ids against per-step occurrence sums; and — the one that would have shipped — **an attack that ran 240 times reported as contributing nothing**, because "ran anywhere" was read from a counts map capped at 100 by ascending id. That last one generalised the feature's own doctrine: absence from a *truncated map* is unknown, not zero, so the null-versus-zero rule governs the map as well as the counts inside it. Two hedged outcomes now exist rather than confident wrong ones — `blocked_where_measured` and `clean_where_measured`. **Three of the nine were regressions from earlier rounds' own fixes**, each caught by a later round. **Two owner-approved scope extensions**: four plan tests added at the planning gate (T-49…T-52, joined later by T-53/T-54), and a one-line fix to `_build_plan_statistics_report` — a pre-existing defect where a constraint the console *did* describe reported `description: null`, because the catalog was built only from the capped conflicts list. That repair also fixes the shipped `get_plan_statistics`. §3 Component E revised to match what shipped, each deviation traced to the test that pinned it. |
| 2026-09-02 | **Decomposed into three question-shaped tools; `get_plan_statistics` retired (v7, decision D4).** The shipped tool answers one broad question — *report everything about this scenario* — and Helm asks three narrow ones, so the caller had to mine a report carrying counts, both zero-impact lists, every conflict and the catalog to find any one answer. Phases **7–9** appended: three projections + public functions (P7), three narrators + registrations + the retirement (P8), documentation (P9). **The plumbing does not move** — all three call the shipped `sb_get_plan_statistics`, so **AC-6 is untouched rather than re-satisfied**, and the 31 tests targeting that function are deliberately not edited; only the ~10 targeting the *tool* are retargeted. **Four user decisions recorded as D4**: retire the single registration rather than keep it as a fourth overlapping tool; full parameter pass-through on all three (the split is in what each *renders*, not what a caller may *ask for*); `get_scenario_attack_blockers` covers **fully-blocked attacks only** (`reducing` stays SAF-35484's scope) and emits a disposition line **only for ids the caller named**, since silence cannot distinguish *ran fine* from *not in this scenario* from *never scored*; and caller-facing vocabulary becomes **scenario** — tool names, parameters (`scenario` for the ad-hoc body), descriptions and CLAUDE.md — while the shipped internals keep `plan` because that is the API's own name for the endpoint. **One default differs**: `get_scenario_simulation_counts` sends `get_constraints=False`, since it renders no conflicts and the cost is not hypothetical (38 531 conflicts / 11.8 MB measured live on a single default step). **Two correctness points the decomposition sharpens rather than inherits**: the blocked-entities verdict must distinguish *nothing is blocked* from *nothing was evaluated* — identical-looking, opposite meaning, R1 on a tool whose entire subject is emptiness — and filtering to named ids must precede `ZERO_IMPACT_CAP`, or a named attack falls off the list that exists to explain it. New risks **R12** (retiring a shipped tool is breaking for existing callers), **R13** (three tools introduce a selection problem the single tool did not have), **R14** (T-32/T-33/T-35 are owed against a tool that will not exist — retargeted, and **AC-4 stays unchecked**: a refactor must not look like verification). Revised §1.5, §2, §3 D/E, §4, §7, §8, §9. `test-plan.md` reconciliation follows via `authoring-test-plan`. |
| 2026-08-27 | **Phase 5 complete — the e2e suite ran for the first time and passed 8/8 with zero skips.** Executed against `zircon-piculet.dev.sbops.com` in 99.6s: T-28, T-29 (2 cases), T-30 (2), T-31, T-40 (2). **Zero skips is the load-bearing fact** — T-30 and T-40 each carry a deliberate skip path for a console that cannot demonstrate their precondition, and neither fired, so the disabled-simulator half of T-30 and the relay assertions of T-40 genuinely ran rather than being waved through. The suite **could not have passed before `900db94`**: five of its eight cases pass an OOB scenario UUID, which returned 400 until the client-side resolution landed. Two corrections this run forced: an earlier probe reported "no custom plans on this console" and was wrong — it queried the wrong endpoint, and `test_custom_plan_integer_string_id_is_accepted` passed rather than skipping; and phase-5.md's smell #5 recorded the uncapped maps as "a PRD decision, not a code fix", which was **a wrong judgement** — live data showed an 11.8 MB response and it was a defect (fixed in `a4a0800`). Phase 5 -> ✅. **AC-4 stays unchecked**: T-35, the only test comparing the tool's numbers against the console's own Checkout tab, is Manual and has not run — everything verified so far establishes self-consistency, not correctness. |
| 2026-08-27 | **`scenario_id` fixed for OOB scenarios (`900db94`); §3 Component B corrected.** The tool's own first documented example — `get_plan_statistics(console=..., scenario_id="3b8eade5-…")` — returned `400 /id must be integer`, so the primary documented route to a saved scenario did not work. Root cause: `ValidatePlan` types `id` as an integer. Probed live: `{"id": 1}` accepted, `{"id": "1"}` accepted (Ajv coerces), `{"testId": "<uuid>"}` rejected ("doesn't have originalPlan" — it wants a *test*), `{"id": "<uuid>"}` rejected. An OOB scenario has **no field that accepts it**. **Fix**: `_resolve_scenario_to_plan` reads the scenario's steps via the existing `_fetch_all_scenarios` and scores them as an ad-hoc body; an integer plan id is still left for the orchestrator. **Placement matters** — the resolution is in *studio*, not the fetch core, so the core's passthrough is unchanged and **T-7 ("no scenario-fetch call was made") still holds**, since it tests the core. An earlier note in this log said the fix would contradict T-7; that was wrong. Unknown ids and step-less scenarios are rejected before any scoring call. **Verified live on zircon-piculet**: the UUID that returned 400 now scores 3 steps, and **T-29's agreement claim holds — by-id `[0,0,6]` == ad-hoc `[0,0,6]`** — at 41.7 KB with the new caps active (54 conflicts, 50 shown, total stated). **Test-plan follow-up**: T-29's Expected still says "the integer-as-string id is accepted as readily as a scenario UUID", which is now true only because MCP resolves the UUID itself — worth rewording via `authoring-test-plan`, and no `T-<n>` yet covers the resolution path (6 tests written without one). |
| 2026-08-27 | **T-30 verified live on zircon-piculet — the includeDisabled inversion is now observed, not inferred.** Scoring one ad-hoc step twice against the orchestrator with the parameter flipped: `includeDisabled=false` (runnable) returned **1,971 simulations across 5 in-scope simulators with 173,034 `simulator_is_offline` reasons**; `includeDisabled=true` (expected) returned **578,148 simulations across 14 simulators with exactly 0 `simulator_is_offline`**. Both of T-30's claims hold: runnable <= expected (a 293x gap), and the offline reason is reported **only** in the runnable answer — indeed it is the sole code present in one and absent from the other. This settles §9 R4, whose stated risk was that the parameter's behaviour "was read from source rather than observed" and that a wrong reading would make the default ask for the wrong number. It did not. The inversion that §8 Phase 5, the tool description and CLAUDE.md all assert is now backed by observation. **Four of the five e2e concerns are settled against reality** (T-28 shape, T-31 typed error, T-40 relayed descriptions, T-30 inversion); T-29 remains broken on the OOB-scenario UUID path. |
| 2026-08-27 | **First live run against a real console (zircon-piculet) — one design premise falsified, one severity-1 defect found and fixed (`a4a0800`).** The deployed mcp-proxy advertises 13 studio tools including `get_plan_statistics`. **Verified live:** T-40 passes — 26 constraint codes, **all 26 with non-null descriptions from the orchestrator, zero nulls** (`incompatible_os` -> "OS is incompatible."), so the relay design is confirmed rather than assumed, and the wording differs from the deleted vendored table, proving it is genuinely the orchestrator's. T-36 verified live — 4 codes carry **both** `blocking` and `reducing` in one step, and only those two values appear, confirming §4's `"none"` is stale. T-23 verified — 0 conflicts carry a `description`. T-31 verified — the typed error verbatim. **Defect 1 (fixed):** a single default step returned **38,531 conflicts, 9,613 attacks, 7,976 zero-impact attacks — an 11.8 MB result (24.5 MB on the wire)**, unusable for the conversational caller the tool exists to serve. Conflicts, both zero-impact lists and the four count maps are now capped with their true totals stated; conflicts sort blocking-first so a cap keeps what explains a zero; caps apply after blockers are derived. Measured on a payload of the real shape: **18.5 KB, a 630x reduction**, with `conflict_detail='full'` lifting every cap. **Defect 2 (open): `scenario_id` is broken for OOB scenarios.** Probing the orchestrator directly: `{"id": 1}` accepted, `{"id": "1"}` accepted (Ajv coerces), `{"testId": "<uuid>"}` rejected ("doesn't have originalPlan"), `{"id": "<uuid>"}` rejected ("/id must be integer"). So custom plans work but **an OOB scenario UUID has no field that accepts it** — §3 Component B's "passthrough as {id}, no client-side resolution" is wrong, and fixing it requires fetching the scenario's steps and sending an ad-hoc body, which also contradicts **T-7**'s no-lookup assertion. Needs a PRD amendment before code. |
| 2026-08-27 | **Phase 6 implemented (`31afb33`) — all six phases now implemented.** CLAUDE.md gains catalog entry 25 covering the runnable default and the `include_disabled` inversion, the report-not-remove posture, the null-means-not-computed rule, the normalized catalog-plus-references conflict shape with computed severity, and the no-MCP-cache decision. The rate-limiting gate table is deliberately untouched — the tool is read-only and takes neither gate. T-34 green (5 cases), split red/green as a documentation guard should be: the three catalog assertions were RED before the edit, the two gate-table assertions GREEN before *and* after, since "the gate table is left alone" is a property to preserve rather than create. Full suite 1710 passed / 0 failed — evidence in `test-results/phase-6.md`. **The feature is NOT signed off.** Eight tests have never run for want of a Validate console environment: T-28…T-31 and T-40 (automatic e2e, authored and collecting) plus T-32, T-33 and T-35 (manual, `Passes after: Final`). **The documentation is now ahead of the verification** — CLAUDE.md states as fact that descriptions are "relayed verbatim from the orchestrator", which only T-40 can confirm, and T-35 is the only test that checks the numbers are *right* rather than merely self-consistent. Provisioning is the next step: `design-test-environment` → `instantiate-test-environment`. |
| 2026-08-27 | **Phase 5 implemented (`1714dba`) — code complete, 5 tests blocked.** `get_plan_statistics` is registered as the 13th studio tool with `readOnlyHint=True`, `destructiveHint=False` and **zero rate-limiter references** (the property holds by construction, not by assertion). T-24…T-27 green (27 cases); full suite 1705 passed / 0 failed — evidence in `test-results/phase-5.md`. **T-28…T-31 and T-40 are BLOCKED on a Validate console environment that has never been provisioned for SAF-35508.** They are authored in `test_e2e_plan_statistics.py` and collect cleanly, with every scenario and plan id discovered at runtime; they run the moment a console exists. **T-40 is the only test in the whole plan that can falsify the relay design** — until it runs, "the orchestrator supplies the descriptions we relay" is an assumption. **Three owner-approved deviations:** the tool returns a **dict**, not the markdown all 12 sibling studio tools return (§4 specifies JSON and the PRD's own principle is "MCP is structured, Helm narrates"); `studio_types.py` was extended, though §8's Phase-5 Changes table omits it, so the both-counts hints point at the sibling key instead of advising a call already made; and `conflict_detail` is exposed, though §8's parameter list omits it, because §3 Component D requires it and Phase 4's `per_attack`/`full` modes would otherwise be permanently unreachable. **Found in review — a real boundary bug:** blank-string arguments (how a calling model routinely fills an unused optional) both defeated the `plan`/`scenario_id` exclusivity check and sent `{"id": ""}` to the orchestrator; verified, then fixed with the same guard `sb_run_scenario` already used. **The limit-reached crash had a third frame.** Phase 3 fixed the helper and both callers and phase-3.md claimed it verified end-to-end — but that check ran `sb_run_scenario` directly, not through the registered tool, and the renderer's `f"{count:,}"` still raised. Fixed at four sites plus a `> 0`, and the truncated refusal no longer claims "No matching simulators or attacks found" — a measured verdict on a path where nothing was measured. **Open for the owner:** `_get_scenario_statistics` drops `truncated`/`counts_computed`, which cannot be surfaced without changing T-13's seven-key golden; and the raw count maps are relayed uncapped (twice under `both_counts`), which §4 and T-20/T-21 currently require. |
| 2026-08-27 | **Phase 4 implemented (`58d7a29`).** The shaping layer lands as a pure function over the Phase 2 fetch core — no I/O, no transport seam, no console, which is why its `Environment needs: none` is the first environment column in this plan that matches reality. Tests T-18…T-23 and T-36 green (50 cases incl. 14 branch tests); full suite 1676 passed / 0 failed — evidence in `test-results/phase-4.md`. Also closes Phase 1's dead-code smell: `_build_plan_statistics_report` is `_build_constraint_catalog`'s first production consumer. **§4's response example needs correcting — four owner-approved deviations.** (1) **`severity: "none"` is not emitted.** §4 shows it for an attack whose count is 240, which §3 Component D, §7, §8 Phase 4 and §9 R8 all say is `reducing`; it is residue from the `informational` classification §2's alternatives table rejects as "premise was wrong", the same premise that tombstoned T-37. (2) `zero_impact_simulators` blockers carry `attack_count` — how many attacks that node was eliminated from — rather than a constant `simulator_count: 1`. (3) `simulator_name` is omitted when unresolvable: no source for it exists in this repo, since servers are siloed and `_build_attack_name_map` is attack-only. (4) `is_limit_reached` is always emitted rather than only on truncated steps, so its absence is never ambiguous. **A fifth item needs a decision:** §8 says `summary` "groups by code with counts", but T-23 requires `attack_id` on every conflict and T-36 requires two severities for one shared code — severity is per-attack by construction, so a code-only grouping fails both reviewed tests. The grouping unit is `(attack_id, code)` in all three modes, which means §8's "the default must stay cheap" goal is only partly met. Either §8 is reworded or a genuine code-level summary needs its own `T-<n>`. **Found in review:** `counts_mode` was a free-form parameter duplicating `params_used['includeDisabled']`, so a wrong argument would have made the response assert "these are runnable counts" over numbers fetched as expected; it is now derived, never passed. **Open plan gaps:** no `T-<n>` covers `conflict_detail` at all (14 branch tests written without one, after a review found every non-default branch untested); T-39's catalog-absent conflict-shape clause is still open; nothing exercises the fetch-core → shaping seam until Phase 5. |
| 2026-08-27 | **Phase 3 implemented (`d53320b`, `a49190e`).** `_get_scenario_statistics` now summarises over `fetch_plan_statistics` instead of calling HTTP. **AC-6 satisfied** — T-16 confirms exactly one `plan/statistics` call site. Tests T-13…T-17 green; full suite 1626 passed / 0 failed — evidence in `test-results/phase-3.md`. **The refactor's evidence is the ordering:** T-13/T-14/T-17 are guards, not red-first tests, so their goldens were captured from the shipped implementation *before the first edit* and pass identically before and after (12 of them, full dict equality across four branches plus the `sb_run_scenario` preview). T-15 and T-16 were genuinely red. **Two findings beyond §8.** (1) **There were three crash sites, not two** — besides the `sum(1 for v in ... if v > 0)` and `sorted(key=lambda x: -x[1])` the PRD names, `sum(counts)` in the closing log line would have kept T-15 red after both named fixes. (2) **Fixing the helper alone did not fix the crash** — it moved one frame up into `sum(step_counts)` in *both* `sb_run_scenario` and `sb_quick_run`, which T-15's Verify (helper-boundary only) and T-17's fully-computed goldens both miss. Verified by running the real caller, then fixed under an approved scope extension with `_sum_computed_counts` / `_runs_anywhere` and two caller-level cases. **Deferred to Phase 4:** `predicted_simulations` now reports `0` on a truncated response where the honest answer is *not computed* (`predicted_per_step` keeps `None`); Phase 4 owns the truncation explanation. **Open plan gaps:** `repo-harness` is wrong for T-13…T-17 too (third phase running); nine seam-bound tests needed migration, not the five predicted, because `requests` is one module object but the console resolvers are imported per-module; and no `T-<n>` covers the caller-level crash. |
| 2026-08-27 | **Phase 2 implemented (`4dadfd1`).** New `safebreach_mcp_core/plan_statistics.py` exposing `fetch_plan_statistics`, shaped after `queue_state.py`. Tests T-6…T-12 green (36 cases; full repo suite 1604 passed / 0 failed) — evidence in `test-results/phase-2.md`. **One addition beyond §8's Outputs list:** the response-root `constraintCatalog` is relayed as a top-level `constraint_catalog` (`None` when absent, `{}` when empty). §8 Phase 2 enumerates only per-step fields plus step counts/truncation/params, but T-6's title says the response is returned *unreduced*, and after Phase 3 this layer is the **only** place the catalog is reachable — dropping it would silently regress Phase 1's relay, and neither T-13 nor T-17 would reliably catch it. The orchestrator reimplements the two-line guard rather than importing studio's `_raw_constraint_catalog`, which would invert the package dependency. **Security fix found in review:** `_build_url` originally hand-joined the query string with no escaping while `limit` was only *annotated* `int` — since Phase 5 puts this behind an MCP tool whose arguments arrive as JSON from an LLM, a `limit` of `"1&getConstraints=false"` would have rewritten the other four parameters. Now `urlencode` plus an `int()` coercion; verified the payload is rejected before the URL is built. **Open plan gaps** (for `authoring-test-plan`): T-6…T-12 carry `Environment needs: repo-harness` though every one mocks the transport and needs no backing service — correct value is `none`, and the runner's uv-pytest dispatch row needs `integration` added; the `planned:` markers are stale; and no `T-<n>` covers the `constraint_catalog` passthrough, the `plan`/`scenario_id` mutual exclusion, or the 403 → `PermissionError` path (all three written as implementing cases). **AC-6 stays unsatisfied until Phase 3** — two call sites exist meanwhile, and the old helper keeps its live `TypeError` until then. |
| 2026-08-27 | **Catalog-absent hint removed (owner decision).** PRD owner: every console will serve SAF-35568's `constraintCatalog`, so the no-catalog case does not occur in practice. `CONSTRAINT_CATALOG_ABSENT_HINT`, `_constraint_catalog_hint()`, the `constraint_catalog_hint` field on `_get_scenario_statistics`' step result, its `run_scenario` preview line, and `test_hint_names_the_missing_catalog` are all deleted. **Null-safety is unchanged and still tested** — an absent or empty catalog still degrades to `description: null` without raising, and conflicts are still surfaced; `description: null` also remains reachable via a code the catalog does not list (T-3), so the resolver guards and the renderer's null branch stay. **Two owner follow-ups this opens:** **§9 R11** names the hint as its mitigation — if older consoles are genuinely out of scope, R11 should be closed rather than left citing a hint that no longer exists; and **T-39**'s `Expected` requires "`hint_to_agent` states that no catalog was supplied", a clause nothing now satisfies — rescope T-39 to its no-raise / keys-present / conflicts-surfaced assertions (all green) via `authoring-test-plan`. |
| 2026-08-27 | **Phase 1 implemented (`1a69fe0`).** `CONSTRAINT_REASON_DESCRIPTIONS` deleted outright with no replacement map; `_raw_constraint_catalog` / `_resolve_constraint_description` / `_build_constraint_catalog` / `_constraint_catalog_hint` added; both summarisers take the catalog. Tests T-1/T-3/T-38/T-39 green (25 cases; full repo suite 1438 passed / 0 failed) — evidence in `test-results/phase-1.md`. **Three scope extensions beyond §8's Changes table, approved by the PRD owner before implementation.** (1) **`fixable` is dropped with the table** — §8 Phase 1 did not say what became of it; with the table gone its only fallback was `True`, which would assert "fixable via `step_overrides`" for all 97 codes including those that are not — a worse vendored claim than the table being removed. Consequence: `run_scenario` previews lose the "*(not via step_overrides)*" tags and the "⚠ N attacks require configuration" footers (§9 R7-sanctioned, but user-visible). (2) **`safebreach_mcp_studio/studio_server.py` added to the phase** — `:1279`/`:1308` indexed `description` directly, so a null printed the literal string `None` on every reason line of any pre-SAF-35568 console (R11). A `_render_constraint_reason` guard renders the code as an identifier with an explicit not-supplied marker, keeping described-as-empty distinct from never-supplied. (3) **`CLAUDE.md:434-435` corrected** — it documented the deleted behaviour ("14 constraint reason codes… Each tagged as fixable") as shipped, which became false at this phase rather than at Phase 6. **Deferred to Phase 4:** T-39's `Expected` also asserts `severity`, `side`, `simulator_count` and `hint_to_agent`, all of which §8 builds in Phase 4 — its provable half is green now; either re-assert the conflict-shape clauses at Phase 4 or move T-39's `Passes after`. **Open plan gaps** (for `authoring-test-plan`): T-1/T-3/T-38/T-39 still carry a stale `Automation lives in: planned:` prefix; no `T-<n>` covers the preview renderer (4 tests written without a plan item — its lack of coverage let an empty-string/never-supplied conflation through the first review); and **§8 Phase 2's output contract omits `constraintCatalog`**, which would silently regress this phase's relay when Phase 3 routes through the core. |
| 2026-08-27 | **Fetch core moved to `safebreach_mcp_core` (v6).** User decision: `plan/statistics` is a general orchestrator API and further clients are expected, so the fetch core ships as a shared primitive rather than a studio-private helper promoted later. Phase 2 now delivers a new file `safebreach_mcp_core/plan_statistics.py` exposing **`fetch_plan_statistics`** — public, no leading underscore, since it is cross-package API — mirroring `core/queue_state.py`, which wraps the orchestrator queue endpoint and is already imported by both `data_functions.py` and `studio_functions.py` (:3111). Phase 3 imports it instead of defining it. The split is on generality: core owns the HTTP call, null-safety and truncation facts; the constraint-catalog relay, conflict normalization and zero-impact shaping stay in studio as presentation, and core's signature carries no studio-specific types. Rationale recorded in §3 B — servers are strictly siloed (the only cross-package import anywhere is inside `data`), so a second consumer could not reach a studio-resident helper and would force the move under pressure; `config_types.py:351-358` is an already-visible candidate, now noted in §10. AC-6 is unaffected — still exactly one call site, now in core. Revised §2, §3 B, §6, §7, §8 Phases 2-3, §10. `test-plan.md` retargeted T-6…T-12 and T-16 to `safebreach_mcp_core/tests/test_plan_statistics.py` with a Change Coverage row for the new module; no test added, removed or re-phased. |
| 2026-08-27 | **Relay the orchestrator's catalog; no vendored vocabulary at all (v5).** Reviewed [SAF-35568's PR](https://bitbucket.org/safebreach/orchestrator/pull-requests/2299) and aligned to what it actually shipped, which differs from what v4 assumed in two ways. (1) It serves `{ description }` only — `fixLever` was implemented in its Phase 1 and **removed in its Phase 5** as redundant relative to the description. v4's chosen option ("delete the table, keep a fix-lever map") rested on the API serving both, so `CONSTRAINT_FIX_LEVERS` is dropped entirely: MCP now vendors **no** constraint vocabulary — no meanings, no levers, no coverage guard — and fills `constraint_catalog` by relaying the response's own `constraintCatalog` verbatim. (2) The vocabulary is **97 codes across 24 groups with keys 1:1 with emitted values**, not 88 with two key/value mismatches — its Phase 6 renamed both spellings at source and deleted 5 dead keys. Consequences: R3 and R6 **close** (nothing vendored to drift, nothing keyed by hand); R7 drops to Low (MCP asserts no remedy at all); R9 drops to Low and R10 **closes** (SAF-35568 delivered — descriptions now arrive for every referenced code, 83 more than MCP ever vendored); new **R11** records the one genuine residual, a console whose orchestrator predates the change sending no catalog, which degrades to `description: null` with conflicts still surfaced plus a `hint_to_agent`. Also folded in: `getConstraints=true` gates the catalog as well as `simulatorConstraints`, the `getAllConstraints` swagger description is no longer stale, and the four count maps are now typed at the source. Revised §1, §2, §3 A/C/D, §4, §5, §6, §7, §9, §10, §11, Phase 1, Phase 4. `test-plan.md` was updated to match in the same revision — T-1/T-3/T-23 rescoped, T-2/T-5 tombstoned, T-38/T-39/T-40 added, validator clean. |
| 2026-08-26 | PRD created — initial draft |
| 2026-08-26 | DoD gate flagged TI-9/TI-10 as gaps. Root cause was the ticket's "auto-removed" wording, not the design: a statistics call reports, it does not act. Reworded SAF-35508 ACs 9/10 to "reported" (plus AC-5/AC-12 alignment, scope item 4, and the out-of-scope line); updated §7, §9, §10 and §11 to match. All 12 ACs now covered. |
| 2026-08-26 | **Deleted the vendored translation table (v4).** `CONSTRAINT_REASON_DESCRIPTIONS` is removed outright — including its 14 existing entries — rather than extended to 88. Rationale: a vendored table is a pressure-release valve, and `ui-react` proves an "interim" copy becomes permanent (57 real / 3 dead / 31 missing after years). What remains is `CONSTRAINT_FIX_LEVERS`: one closed-enum lever per emitted code, the fact a calling model cannot infer. No `description` is authored for any code; the response emits `description: null` explicitly so "not supplied" is distinguishable from "empty". Consequences recorded rather than hidden: SAF-35568 becomes a **dependency** (new R10) and 14 codes lose descriptions two shipped tools display today (new R9). R3 drops to Low (no meanings vendored, so none to drift); R7 narrows from descriptions to levers. Phase 1 shrinks from "author 88 descriptions from emit sites" to "delete the table, map 88 levers". Revised §1, §2, §3 A/D, §4, §7, §9, §10, §11, Phase 1. |
| 2026-08-26 | **Aligned to SAF-35568.** Filed the orchestrator follow-up and linked it *relates to* this sub-task, then pointed every forward reference at the ticket key instead of "§10 files a follow-up" (§2 solution + two alternatives rows, §9 R3 mitigation). Rewrote the §10 entry to match what the ticket actually proposes — `constraintCatalog` of `{ description, fixLever }` in the statistics response, gated on `getConstraints=true`, no `severity`, no `kind` — and added two things the ticket implies for this PRD: the **snake_case ↔ camelCase lever rename** MCP keeps after the migration, and the requirement that the resolver tolerate a **partial catalog** (levers without descriptions) since SAF-35568 may ship the lever half first while localization is resolved. |
| 2026-08-26 | **Correction — no `kind`, descriptions for all 88.** Checked the emit sites: every one of the 88 codes sets `valid = false` and the node is dropped from `filteredNodes` (`aws_validation.js:96-101`, `gcp_validation.js:77-81`). The `*_is_ignored` / `ignoring_*_variant` families are **variant-level de-duplication, not benign notes** — so the previous row's 72/16 `elimination`/`informational` split did not exist, and `kind` is removed entirely. Severity now derives from the counts alone. Because the names proved misleading, `description` is authored for **all 88** from their emit sites rather than ~20; the "self-describing majority" premise is retracted. R7 is rewritten from "misclassifying kind" to "descriptions written from names". `fix_lever` is no longer claimed to be MCP-specific — `attackerFilter`/`targetFilter` are the orchestrator's own `ValidatePlan` fields — so §10 now asks the API for `{ description, fixLever }` and drops the severity/catalog-endpoint proposal. T-37 tombstoned; T-1/T-3/T-36 rescoped. |
| 2026-08-26 | **Design revision — MCP is structured, Helm narrates.** Resolved the ticket's internal contradiction between scope item 1 ("no narrative fields — Helm interprets") and items 3/7 ("plain-language explanation + suggested fix") in favour of item 1. `CONSTRAINT_REASONS` (88 prose descriptions + 88 suggested fixes) becomes `CONSTRAINT_CATALOG` — `kind` + `fix_lever` for all 88, corrective `description` for ~20 only, `suggested_fix` dropped as model-derivable. Added computed `severity` (`blocking`/`reducing`/`none`), since blocker-ness is contextual per attack, not a property of the code. Normalized the response into a `constraint_catalog` + references, grouped by `(attack, code)`. Verified `unable_to_validate` cannot appear as a reason code, so no `indeterminate` severity. Added R7/R8; reframed R3 with the measured ui-react drift (3 dead entries, 31 gaps). Filed the orchestrator catalog follow-up in §10. Revised §2, §3 A/D, §4, §7, Phases 1 and 4. |
