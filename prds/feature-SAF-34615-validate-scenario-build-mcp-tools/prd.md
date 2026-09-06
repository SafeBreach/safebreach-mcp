# MCP support for Validate scenario creation and update (Stage 1) — SAF-34615

## 1. Overview

- **Title**: MCP support for Validate scenario creation and update (Stage 1) — SAF-34615
- **Task Type**: Feature
- **Purpose**: **Rescoped 2026-09-06b — this repo's remaining share of SAF-34615 is read-only search parity.**
  The scenario-creation write path left this repo entirely: it is now a native Helm tool in `breach-genie`
  (see the companion PRD). What remains here is closing FR2's discovery gap — `get_playbook_attacks` gains
  attack-type, attack-phase and tag filters so the Helm skill can find the right attacks before assembling a
  scenario. No new tool, no write surface, no state.
- **Target Consumer**: Helm (SafeBreach's AI agent), and — through Helm — any SafeBreach customer or internal
  user who talks to Helm to build a scenario instead of using the console directly.
- **Target Roles (RBAC)**: No new roles. Every tool call carries the caller's own console API credentials
  (existing `get_auth_headers_for_console`/RBAC pattern); a user can only create scenarios their console
  account is already authorized to create.
- **Key Benefits**:
  1. Turns a 5-screen manual console flow into a guided conversation with the same underlying validation.
  2. Keeps impact and conflict numbers backed by one authoritative source (the Core statistics engine) instead of
     letting an AI agent estimate them.
  3. Structurally keeps Propagate scenarios and attacks out of this flow, regardless of account licensing.
  4. Exposes exactly **one** public entry point that can change anything, so there is a single place where
     console-parity validation, Propagate exclusion, and rate limiting are enforced.
- **Business Alignment**: Epic SAF-34231, "Helm Skills & Tools for CTEM answer quality." Stage 1 of 4
  (SAF-35484 Stage 2 — filter-based simulator selection; SAF-35485 Stage 3 — editing; SAF-35051 Stage 4 — asset
  association).
- **Originating Request**: [SAF-34615](https://safebreach.atlassian.net/browse/SAF-34615), reported by Tal Rotem.

> **Scope banner (2026-09-06b)**: this PRD originally specified nine mutating tools, then one (`create_plan`).
> On the owner's decision the write moved out of MCP altogether. Everything below about scenario creation is
> retained as **superseded design history** — clearly marked — because the investigation behind it (the platform's
> whole-body-only write API, the filter-key findings, the Propagate-exclusion reasoning) is what the
> `breach-genie` tool is now built on. The **live scope of this PRD is Section 3's Component D and Section 8's
> single phase.**

**Companion PRD**: the Helm-side orchestration — search strategy, step-grouping procedure, confirmation cadence,
conflict-to-plain-language translation, simulation-count presentation, and (new in this revision) **assembly of
the plan body this tool consumes** — is a separate deliverable in `breach-genie`, branch
`feature/SAF-34615-validate-scenario-building-skill`,
`prds/feature-SAF-34615-validate-scenario-building-skill/`. Same JIRA ticket, no subtask split, tracked as two
repos/branches/PRs by design (see this PRD's `context.md` §6 Decision 6). **This PRD's Section 5 (Example
Customer Flow) is omitted for that reason — the user-facing conversation is that PRD's content, not this one's.**

---

## 1.5. Document Status

| Field | Value |
|---|---|
| **PRD Status** | Draft |
| **Last Updated** | 2026-09-06 |
| **Owner** | AI Agent (Claude), planning session with Boris Berezovsky |
| **Current Phase** | N/A |

---

## 2. Solution Description

### Chosen Solution

**One enhanced read tool. No new tools, no write surface.**

`get_playbook_attacks` gains `attack_type_filter`, `attack_phase_filter` and `tags_filter`, applied Python-side
against the already-cached attack fetch. That closes FR2's CVE/named-threat-group discovery gap and gives the
Helm skill a search vocabulary that matches the plan body's filter vocabulary exactly — the same axis names
meaning the same thing on both sides of the flow.

#### Superseded design history — the write path (moved to `breach-genie` 2026-09-06b)

The material below described `create_plan`, which no longer ships from this repo. It is kept because the
`breach-genie` tool inherits its every substantive finding: the whole-body-only write API, `attacksFilter.playbook`
as the real explicit-id key (`methodIds` is unimplemented), the `Package` enum mapping, the `simulators` filter
key, the DAG requirement, and the Propagate-exclusion argument. Read it as the rationale the companion PRD's
Component H is built on, not as work planned here.

`create_plan(name, steps, console)` is a thin wrapper over `POST config/v3/accounts/{accountId}/plans`. It holds
no state, mints no draft id, and orchestrates nothing. It does exactly three things beyond the HTTP call:

1. **Mechanical body assembly** — generates the execution DAG (`actions`/`edges`) from the ordered step list, the
   same way `run_scenario`'s `_build_linear_dag(steps)` already does, and force-sets `type:'validate'` /
   `propagateDefinition:null`. The caller never hand-writes orchestrator-internal execution structures.
2. **Console-parity validation (FR9)** — themed step names, non-empty steps, attack-selection mutual
   exclusivity, no `tags` input surface, DB unique-constraint error shaping. This is the enforcement boundary;
   skill text is guidance, and guidance is not a guard.
3. **Rate limiting** — one `check_limit`/`record_action` pair, because this is the only mutating call in the
   feature.

Everything upstream of persistence is the skill's job: attack discovery via the existing read tools, step
grouping, presentation and confirmation, simulator selection, and the **pre-save preview** — which needs no new
tool, because SAF-35508's `get_scenario_simulation_counts` / `get_scenario_blocked_entities` /
`get_scenario_attack_blockers` already score an **ad-hoc, never-saved plan body** (`get_plan_statistics`'s `plan`
input exists precisely for this). Verified with the ticket owner: the statistics endpoint does not require
`actions`/`edges`, so the skill previews the same `{name, steps}` structure it later hands to `create_plan`.

`get_playbook_attacks` gains matching `attack_type_filter`/`attack_phase_filter`/`tags_filter` parameters so the
skill can discover which attacks match a filter while assembling the body.

### Alternatives Considered

| Alternative | Pros | Cons | Why not chosen |
|---|---|---|---|
| **Nine granular draft-mutation tools + an in-process draft cache** (this PRD's original design) | Small per-turn payloads; server holds the truth, so no LLM drift risk; one user decision = one tool call; matches `save_studio_attack_draft`/`update_studio_attack_draft` precedent | Nine public write tools, against the owner's explicit "one public entry point" requirement; a module-scope `maxsize=20` cache shared process-wide across all callers can LRU-evict a live draft mid-conversation; three redundant add/remove pairs are the exact shape Anthropic's tool-design guidance warns against | Superseded by the owner's decision (2026-09-06) that the skill orchestrates and MCP only persists. The shared-cache concurrency flaw independently favored dropping the draft |
| **One `build_scenario(spec, dry_run)` tool** — stateless, preview and persist in one contract | Single entry point; `dry_run` makes the save-gate intrinsic; mirrors `quick_run`'s evaluate→execute precedent | Still puts flow-shaped logic (preview semantics, spec normalization) inside MCP, when the flow genuinely lives in Helm; duplicates preview capability SAF-35508's tools already provide for ad-hoc bodies | Owner chose the thinner split: MCP persists, the skill orchestrates and previews through the existing statistics tools |
| **Persist immediately on a `create_scenario` call**, read-modify-write per mutation | Survives process restarts (state in Postgres, not memory) | Contradicts the console's own verified behavior (`context.md` §6.4 — Studio never persists before Save); publishes an unfinished scenario into the user's real catalog; a Validate plan cannot be created with zero steps (server-side 400), so "create empty, then add steps" is **impossible** | Product risk outweighs the benefit; also moot now that there is no incremental mutation surface at all |
| **`config/v2/plans`** instead of `v3` | Self-guards `type='validate'` automatically on create; exact console behavior, easiest to diff for FR9 parity | Flagged `// DELETE WHEN v2 IS REMOVED` in its own code | User chose the forward-looking surface; the self-guard is rebuilt explicitly in `create_plan` instead |

### Decision Rationale

Two constraints drove the shape, and one owner decision settled it.

The **platform constraint** is unchanged from the original investigation: `configuration`'s Plan write API has no
incremental step endpoint (`PUT` deletes and recreates **every** step on every save) and rejects a zero-step plan
outright. Nothing incrementally addressable exists server-side to model, so a scenario is only ever created as a
whole — which makes a single whole-body create the natural fit, not a compromise.

The **product constraint** is the owner's: exactly one public entry point for scenario creation, with
orchestration living in a Helm skill rather than in the MCP tool surface. That relocates the flow logic to where
it is actually expressible (natural-language procedure) and leaves MCP owning what only a server can own —
validation, credentials, and the write itself.

Studio-as-home and v3-as-surface remain user decisions (see `context.md` §7 Decisions 3-4).

---

## 3. Core Feature Components

### Component A — `create_plan` (the single public entry point)

**Purpose**: Persist a fully-assembled Validate scenario. The only tool in this story that changes anything.

**Key Features**:
- `create_plan(name: str, steps: list[dict], console: str) -> {scenario_id, name}`.
- **Stateless** — no draft id, no cache, no cross-call continuity. The caller supplies the whole scenario; the
  tool validates, assembles, POSTs, and returns. Nothing to evict, expire, or contend over between callers.
- **DAG assembly is the tool's job, not the caller's.** `planFields` includes `actions` and `edges` (the
  execution DAG). These derive mechanically from the ordered step list — `run_scenario` already builds them via
  `_build_linear_dag(steps)` — so the tool generates them rather than asking an LLM to hand-write internal
  execution structures it could get subtly, silently wrong.
- **Force-sets `type:'validate'` and `propagateDefinition:null`** on every request. `config/v3/plans` does not
  self-guard this the way `v2` does — `validatePlanShape`
  (`configuration/src/server/utils/model-validators.js:45-59`) requires the pairing, so it must be explicit.
- **`readOnlyHint=False`** with the standard rate-limit gate pair (`check_limit` after validation and before the
  POST; `record_action` only after the POST succeeds).
- Returns `{scenario_id, name}` plus a `hint_to_agent` pointing at `run_scenario` as the natural next action.

**Integration points**: `POST config/v3/accounts/{accountId}/plans` (`configuration`). No other external call.

### Component B — The Plan Body Contract

**Purpose**: Define precisely what `steps[]` must contain — the shape the skill assembles, the tool validates,
and SAF-35508's statistics tools score. This component builds no tool of its own; it is the contract three
parties agree on, and the reference the companion skill PRD encodes for Helm.

**Step shape** (one dict per step, order significant — it becomes the DAG):

```
{"name": "<themed name>", "attacksFilter": {...}, "attackerFilter": {...}, "targetFilter": {...}}
```

**Key Features**:
- **`name` is required and must be themed.** The console's own `getDefaultStep` names steps `"Step 1"`/`"Step 2"`
  (`planUtils.ts:160`) — exactly the anti-pattern `scenario-step-grouping.md` rule 1 forbids ("Never leave steps
  named 'Step 1', 'Step 2'"). `create_plan` rejects those defaults rather than replicating the console's
  behavior. This is a deliberate, documented divergence from console parity, in the stricter direction.
- **Attack selection is one mode per step, not a combination** — grounded in `scenario-step-grouping.md` rule 5
  ("a step can select attacks by criteria, explicit playbook_ids, or attack_tags" — a free choice). A step
  carrying both explicit ids and criteria filters is a validation error.
  - Explicit ids → `attacksFilter.playbook` with `{"operator": "is", "values": [...], "name": "playbook"}` —
    **verified** as the real, orchestrator-implemented explicit-id filter
    (`orchestrator/src/server/other/playbook_filter.js:53`,
    `valuesExtractorByFilter.playbook = move => move.id`). The schema's `methodIds` field has **no
    implementation anywhere in `orchestrator/src`** and must never be used.
  - Attack type → `attacksFilter.attackType`; attack phase → `attacksFilter.attackPhase`, where the
    caller-facing strings `infiltration|lateral|exfiltration|host_level` map to the orchestrator's `Package`
    enum `INFILTRATION=2|LATERAL=1|EXFILTRATION=0|HOST_LEVEL=5`. **The tool owns this mapping** — the skill
    supplies the readable string, and an unrecognized value is a validation error, never a silent drop.
  - Tags → `attacksFilter.tags[group]`, a generic group-keyed dict (e.g. `{"Threat Actor": ["APT29"]}`) covering
    Threat Actor, CVE, and custom tags without a dedicated parameter per group.
- **Simulator selection is explicit ids only** in Stage 1 — written into `attackerFilter.simulators` /
  `targetFilter.simulators`, using the real orchestrator-implemented key
  (`orchestrator/src/server/other/simulators_filter.js:6,17`,
  `valuesExtractorByFilter.simulators = simulator => simulator.id`). FR5 is explicit that "automatic simulator
  suggestion based on the planned attacks is out of scope for this story," and the ticket's Future Scope names
  filter-based simulator selection as Stage 2 (SAF-35484).
- **Scope note the tool description must carry**: `scenario-step-grouping.md` rule 5's `criteria` mode is
  attack type **+ OS** together. The OS half is a simulator-side filter, and FR5 restricts Stage 1 to manual
  simulator selection — so this contract only ever expresses the attack-side half of true "criteria" mode.

**Integration points**: this exact shape is what `get_scenario_simulation_counts` /
`get_scenario_blocked_entities` / `get_scenario_attack_blockers` consume as an ad-hoc `plan` body, and what the
`create_plan` POST body carries. One shape, three consumers — which is why the skill can preview and persist the
same structure without translation.

### Component C — Console-Validation Parity Guard (FR9, FR1/DoD3)

**Purpose**: Everything the console enforces that the raw `config/v3/plans` API does **not** — so this MCP path
is not a backdoor around console logic (FR9), and so no scenario can be created with a Propagate attack in it
regardless of license (FR1/DoD3). All of it lives inside `create_plan`, because a single entry point means a
single enforcement point.

**Key Features**:
- **`type:'validate'` / `propagateDefinition:null` force-set** on every request (Component A).
- **No `tags` input parameter exists** — this closes the legacy `tags:['ALM']` Propagate signal (verified:
  `orchestrator`'s `isPropagateTest` ORs `type==='propagate'` with `systemTags.includes('ALM')`, and plan `tags`
  become `systemTags` at fire time) by never exposing the input surface that could set it, rather than building
  a reject-filter for an input this story doesn't need.
- **DoD3's attack-level guard is structural, not a new check**: `get_scenario_blocked_entities` /
  `get_scenario_attack_blockers` reuse the exact orchestrator method (`PlanPreparation.filterMoves`) that strips
  every `ALM=1`-tagged move for any step where `!step.isPropagate` — and since this contract only ever builds
  `Plan.steps[]` (never `propagateDefinition`), that predicate is always true. Any Propagate attack a user asks
  for scores zero simulations and is caught during the skill's preview stage (DoD6).
- **Themed step names enforced**, per Component B.
- **DB-level unique-constraint failure handled** (`(name, accountId)` unique index,
  `configuration/src/server/models/plans.js:101-108`) with a clear, typed "name already in use" error rather
  than a raw Sequelize error. The console has no client-side pre-check for this either, so an MCP-side
  pre-check would be a nice-to-have, not parity.
- **Per-path validation errors.** A rejection names the offending path (`steps[2].name`), not just the fact that
  something was wrong — the whole-body shape must not cost the caller the error precision a per-field tool
  surface would have given.
- **Documented, not built, this story**: step-name length, most "is this scenario runnable" logic (branching
  validity, attacker+target presence) are **client-only in the console today** (verified — no server-side
  equivalent in `configuration`). Full parity is out of scope for Stage 1; Risk R4 names this so it isn't
  silently assumed done.

**Integration points**: `create_plan`'s own implementation; no additional files.

### Component D — Attack Search Parity

**Purpose**: Let the skill discover which attacks match a type/phase/tag while assembling the body, and close
FR2's CVE/named-threat-group bulk-search gap found during investigation.

**Key Features**:
- `get_playbook_attacks` (existing tool, `safebreach_mcp_playbook`) gains `attack_type_filter`,
  `attack_phase_filter`, `tags_filter` parameters, in the same style as its existing `mitre_technique_filter` /
  platform filters — comma-separated where applicable, applied Python-side against the already-cached full
  attack fetch (`_get_all_attacks_from_cache_or_api` → `filter_attacks_by_criteria`). No new upstream API call:
  the raw tag data is already present in every fetched attack; it is simply not carried through
  `transform_reduced_playbook_attack` today unless `include_tags=True`.
- This keeps the skill's search vocabulary and the plan body's filter vocabulary aligned — the same axis names
  mean the same thing on both sides.

**Integration points**: `safebreach_mcp_playbook/playbook_types.py`, `playbook_functions.py`.

### Component E — Impact/Conflict Integration (dependency, not built here)

**Purpose**: Document how the skill consumes SAF-35508's statistics tools — no new code in this PRD's scope, but
load-bearing for FR6/FR7/FR12/FR14/DoD2/DoD5/DoD6, and now for the **pre-save preview** that replaced this PRD's
original in-tool save gate.

**Key Features**:
- **Implemented and tested, as of 2026-09-03** — re-verified directly against
  `origin/feature/SAF-35508-plan-statistics-mcp-tool` (`de8afff`) and its `CLAUDE.md` catalog, not taken on a
  report. SAF-35508 retired its single `get_plan_statistics` tool for three narrow tools per owner decision D4:
  `get_scenario_simulation_counts` ("how many simulations?"), `get_scenario_blocked_entities` ("is anything
  fully blocked?" — a **five**-state verdict: entities blocked / nothing blocked / `clean_where_measured` /
  `partially_evaluated` / nothing evaluated, decided by `counts_computed`, never by list emptiness),
  `get_scenario_attack_blockers` ("why didn't attack #N run?" — **`attack_ids` is required**, enforced in the
  tool's JSON schema; six per-id dispositions: `ran`, `blocked`, `blocked_where_measured`, `not_computed`,
  `count_map_truncated`, `absent`). All three call the same shipped `sb_get_plan_statistics` plumbing (AC-6
  intact). 1932 tests passing; PR [#91](https://github.com/SafeBreach/safebreach-mcp/pull/91) is open (not
  draft) but currently has a real merge conflict against `main` — doesn't block this branch, which stacks on
  the feature branch directly, not `main`.
- **These tools score an ad-hoc, never-saved body** via `get_plan_statistics`'s `plan` input — which is what
  makes a pre-save preview possible without any new tool in this story. **Verified with the ticket owner
  (2026-09-06): the statistics endpoint does not require `actions`/`edges`**, so the skill previews the same
  `{name, steps}` structure it later passes to `create_plan`, and `create_plan` adds the DAG at persist time.
- **`fix_lever` was removed**, not shipped — SAF-35568 implemented it separately and dropped it as redundant
  against `description`. Conflict-fix composition must use `description` alone.
- **A disclosed, not-fixed edge case affects FR7's translation**: an attack the orchestrator never generates
  into a "move" reports `absent` even when the caller named it in the scenario's own filter — indistinguishable
  from a genuinely wrong ID at the response-shape level. Worth a note in the `breach-genie` skill's
  conflict-translation guidance; not something this repo's tools can fix (orchestrator-level).
- **AC-4 (console-number parity) is partially verified**: a real console run confirmed the tool's parameter
  mapping matches the console's own `getPlanStatistics` call exactly, on both `includeDisabled` settings — the
  risk that actually mattered. Reading the console UI's own rendered figure (T-35) remains an explicitly
  accepted gap on SAF-35508's side.
- **Who calls these**: the skill, not `create_plan`. This is the substantive change from this PRD's original
  design, where `save_scenario` itself required a fresh all-clear `get_scenario_blocked_entities` verdict before
  persisting. With orchestration in the skill, the preview-then-confirm sequence is the skill's procedure
  (companion PRD), and `create_plan` enforces structural validity rather than conversational sequence — see
  Risk R2.

**Integration points**: none in this repo's code — purely a contract dependency, against an implemented, tested
surface. Tracked as Risk R1.

---

## 4. API Endpoints and Integration

### Existing APIs Consumed

| API | URL | Method | Consumed by |
|---|---|---|---|
| Plan create | `config/v3/accounts/{accountId}/plans` | POST | `create_plan` (Component A) |
| Plan statistics (via three successor tools, dependency) | `orch/v1/accounts/{accountId}/plan/statistics` | POST | Indirectly — the skill feeds the same `{name, steps}` body to `get_scenario_simulation_counts`/`get_scenario_blocked_entities`/`get_scenario_attack_blockers` before calling `create_plan` |
| Playbook attacks (moves) | `{base_url}/api/kb/vLatest/moves?details=true` | GET | Component D, via the existing `get_playbook_attacks` fetch-all-and-cache path — no new call |
| Console simulators | existing `get_console_simulators` (Config server) | GET | The skill's simulator-selection stage — **no new tool**; the originally-planned `list_simulators` is dropped as redundant |

### New MCP Tools to Create

| Tool | Server | Input | Output | Errors |
|---|---|---|---|---|
| `create_plan` | `safebreach_mcp_studio` | `name: str`, `steps: list[dict]` (Component B shape), `console: str` | `{scenario_id, name, hint_to_agent}` | empty/missing name; zero steps; unthemed step name (`"Step 1"`-style); step with both explicit ids and criteria filters; unrecognized attack-phase string; DB unique-constraint violation on `(name, accountId)`; upstream 4xx/5xx |

`readOnlyHint=False`, with the standard rate-limiting gate pair. **This is the only new tool in this story** —
down from nine in the original design.

### Enhanced Existing Tool

| Tool | New parameters | Server |
|---|---|---|
| `get_playbook_attacks` | `attack_type_filter?: str`, `attack_phase_filter?: str`, `tags_filter?: dict[str, list[str]]` | `safebreach_mcp_playbook` |

---

## 6. Non-Functional Requirements

### Security & Compliance
- **Authentication**: `create_plan` uses the existing per-console auth pattern (`get_auth_headers_for_console`,
  `check_rbac_response`) — no new auth mechanism.
- **RBAC**: inherited from the caller's console API token; no new roles.
- **Compliance (Propagate/license)**: FR1/DoD3's guard (Component C) is structural — no `tags` input surface
  exists, and `create_plan` force-sets `type:'validate'`/`propagateDefinition:null` on every request,
  independent of the account's Propagate license state.

### Technical Constraints
- **Dependency, implemented (verified 2026-09-03)**: `get_scenario_simulation_counts` /
  `get_scenario_blocked_entities` / `get_scenario_attack_blockers` (SAF-35508 D4) are implemented, tested (1932
  passing), and partially verified against a real console — see Component E for the current contract (five-state
  blocked-entities verdict, required `attack_ids`, no `fix_lever`). Residual: PR #91 has an open merge conflict
  against `main`, worth resolving before this story's own PR is ready to merge.
- **Statelessness**: `create_plan` holds no state between calls. This removes the original design's in-process
  draft cache entirely — and with it the concurrency hazard that a module-scope `maxsize=20` cache, shared
  process-wide across all callers, could LRU-evict one user's in-flight draft because of another user's
  activity. There is no longer any deployment assumption about single-process operation.
- **Backward compatibility**: N/A — new tool; `get_playbook_attacks`'s new parameters are additive/optional.

### Performance
- One POST per scenario creation; no caching, no polling, no background work. The skill's preview stage costs
  whatever SAF-35508's statistics calls cost, unchanged by this story.

---

## 7. Definition of Done

**Rescoped 2026-09-06b** — the scenario-creation DoD items moved to the companion `breach-genie` PRD along
with the tool. What this repo owns:

**Core Functionality**
- [ ] `get_playbook_attacks` supports `attack_type_filter`, `attack_phase_filter` and `tags_filter`, with the
      exact tag group names (`"CVE"`, `"Threat Actor"`) documented in the tool description.
- [ ] The filter vocabulary matches the plan-body vocabulary the companion PRD's tool accepts — same axis names,
      same attack-phase strings — so an attack found here can be selected there without translation.
- [ ] `CLAUDE.md`'s `get_playbook_attacks` catalog entry and `CHANGELOG.md` are updated.

**Quality Gates**
- [ ] Every test in `test-plan.md` for this repo's scope is green, with evidence in `test-results/`.
- [ ] Each new filter is covered individually and in combination with the existing MITRE/platform filters.
- [ ] A mistyped tag group name returns zero results rather than erroring — asserted, since that silent-failure
      mode is what Risk R7 is about.

**Cross-repo (tracked, not owned here)**
- [ ] The scenario-creation DoD (DoD1/DoD3/DoD4, Propagate exclusion, themed step names, DAG assembly) is
      satisfied by the companion PRD's Phase 7 — this repo's DoD gate must reference it rather than restate it.

---

## 8. Implementation Phases

**Rescoped 2026-09-06b.** The write phase left this repo with the tool. One phase remains.

| Phase | Status | Completed | Commit SHA | Notes |
|---|---|---|---|---|
| ~~Phase 1: `create_plan`~~ | ❌ Removed | - | - | Moved to `breach-genie` as the native `createValidateScenario` tool (companion PRD Phase 7) |
| Phase 1: `get_playbook_attacks` filter parity | ⏳ Pending | - | - | The whole of this repo's remaining scope |

### ~~Phase 1: `create_plan`~~ — REMOVED (moved to `breach-genie`)

Retained below as design history; the companion PRD's Phase 7 implements this content as a native Helm tool.
Its substance is unchanged — validation, filter normalization, `Package` mapping, DAG assembly, forced
`type:'validate'`, unique-constraint shaping — only the language and the repo differ.

#### (superseded) `create_plan` — validation, DAG assembly, persistence

**Semantic Change**: Introduce the story's single public entry point — a stateless tool that validates a
caller-supplied scenario, assembles the wire body, and persists it as a real Validate plan.

**Deliverables**: `sb_create_plan` business function; the validation layer; the DAG assembler; `create_plan` tool
registration with rate-limit gates; docs; tests (unit against a mocked `config/v3/plans` response, plus e2e
against a real console per Risk R5's elevated scrutiny).

**Changes**:

| File | Change |
|---|---|
| `safebreach_mcp_studio/studio_functions.py` | Modified — add `sb_create_plan` (validation, DAG assembly, wire-body construction, DB-uniqueness error shaping) |
| `safebreach_mcp_studio/studio_types.py` | Modified — add `get_create_plan_response_mapping` |
| `safebreach_mcp_studio/studio_server.py` | Modified — register `create_plan` |
| `CLAUDE.md` | Modified — rate-limit gate row, Studio catalog entry |
| `CHANGELOG.md` | Modified — `### Added` bullet |
| `pyproject.toml` | Modified — version bump |

**Implementation Details**:
1. **Validate the input** before anything else, collecting per-path errors: `name` non-empty; `steps` non-empty;
   each step's `name` present, non-empty, and not a `"Step <n>"`-style console default; each step's attack
   selection using exactly one mode (explicit `attacksFilter.playbook` ids XOR criteria/tag filters); each
   attack-phase string in `{infiltration, lateral, exfiltration, host_level}`. Errors name the offending path
   (`steps[2].name`), never just the fact of failure.
2. **Normalize filters** into the orchestrator's wire shape — `{"operator": "is", "values": [...], "name": key}`
   per axis — and map the caller-facing attack-phase string onto the `Package` enum
   (`INFILTRATION=2|LATERAL=1|EXFILTRATION=0|HOST_LEVEL=5`).
3. **Assemble the DAG**: derive `actions`/`edges` from the ordered step list, reusing the existing
   `_build_linear_dag(steps)` helper rather than a second implementation.
4. **Assemble the wire body** from `planFields`, force-setting `type: "validate"` and
   `propagateDefinition: null` — never inherited from the caller, who has no surface to supply them.
5. **Rate-limit gate**: `check_limit` after validation, before the POST.
6. `POST config/v3/accounts/{accountId}/plans`.
7. `record_action` only after the POST succeeds.
8. On a DB unique-constraint violation (`(name, accountId)`), surface a clear "name already in use" error rather
   than the raw Sequelize error.
9. Return `{scenario_id, name}` plus a `hint_to_agent` pointing at `run_scenario`.

**What can go wrong**: a name collision; an upstream 4xx/5xx from `configuration`; a DAG shape that saves but
misbehaves at run time (why step 3 reuses the proven helper rather than reimplementing).

**Data flow**: skill → `create_plan` → validation → normalization → DAG assembly → `config/v3/plans` POST →
`{scenario_id, name}`.

**Git Commit**: `feat(studio): add create_plan tool for Validate scenario persistence`

### Phase 1: `get_playbook_attacks` filter parity — **the live phase**

**Semantic Change**: Extend the existing playbook search tool so the skill's discovery vocabulary matches the
plan body's filter vocabulary.

**Deliverables**: `attack_type_filter`/`attack_phase_filter`/`tags_filter` on `get_playbook_attacks`; tests.

**Changes**:

| File | Change |
|---|---|
| `safebreach_mcp_playbook/playbook_functions.py` | Modified — extend `filter_attacks_by_criteria` with the three new axes |
| `safebreach_mcp_playbook/playbook_types.py` | Modified — carry tag/type/phase data through `transform_reduced_playbook_attack` |
| `safebreach_mcp_playbook/playbook_server.py` | Modified — expose the new parameters |
| `CLAUDE.md` | Modified — update the `get_playbook_attacks` catalog entry |

**Implementation Details**: filters apply Python-side against the already-cached full attack fetch — no new
upstream API call, since the raw tag data is already present in every fetched attack and simply isn't carried
through the reduced transform today unless `include_tags=True`. Axis names and the attack-phase vocabulary match
Component B exactly, so a filter that finds attacks here expresses the same selection there.

**What can go wrong**: a mistyped tag group name returns zero results rather than erroring — call this out in the
tool description, and name the exact group strings (`"CVE"`, `"Threat Actor"`) so the skill can encode them.

**Data flow**: caller → `get_playbook_attacks` → cached attack list → Python-side filtering → paginated results.

**Git Commit**: `feat(playbook): add attack type, phase and tag filters to get_playbook_attacks`

---

## 9. Risks and Assumptions

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| R1 | **SAF-35508 dependency.** The three `get_scenario_*` tools are implemented and tested (1932 passing), re-verified against the live branch — but PR #91 has a real merge conflict against `main` (doesn't block this branch, which stacks on the feature branch). Contract specifics any implementation must match: `attack_ids` on `get_scenario_attack_blockers` is **required**; `get_scenario_blocked_entities`'s verdict is **five** states; `fix_lever` was removed, so conflict-fix composition uses `description` alone; AC-4 is partially verified. | Medium | Implementation targets the real, documented contract in `CLAUDE.md` catalog entries 25-27. Confirm PR #91's conflict is resolved before this story's PR is ready to merge. |
| R2 | **The preview-then-confirm sequence is now enforced by skill text, not by the tool.** The original design had `save_scenario` require a fresh all-clear `get_scenario_blocked_entities` verdict before persisting. With orchestration in the skill, `create_plan` enforces structural validity but cannot know whether the user actually saw and approved a preview — a caller that skips straight to `create_plan` gets a structurally valid scenario nobody reviewed. | Medium | Deliberate, owner-approved consequence of relocating orchestration. `create_plan` still refuses anything structurally invalid or Propagate-tainted, so the failure mode is "unreviewed", not "broken". The companion skill PRD owns the confirmation cadence; if this proves insufficient in practice, a `preview_token`-style handshake is the natural fast-follow. |
| R3 | **This story's tool contract deliberately diverges from FR13's literal text.** FR13 enumerates nine tools by name (`create_scenario`, `add_step`, `add_attacks_to_step`, …); this design ships one (`create_plan`) and relocates the rest into the Helm skill. This is a larger departure than the original PRD's (which diverged on `scenario_id`/`step_id` semantics but kept the tool names). | **High** | **Needs the ticket owner's explicit sign-off before implementation starts** — flagged as an open item, not an assumption. Section 2 and `context.md` document the reasoning (one-entry-point requirement, orchestration belongs where it's expressible, the platform's whole-body-only write API). A reviewer judging "done" against FR13's literal wording without this context would misjudge the implementation. |
| R4 | **Console validation parity is intentionally partial** (Component C) — step-name length and most "is this runnable" branching/attacker-target-presence logic are client-only in the console and are not rebuilt here. | Medium | Explicitly scoped out in Component C and this entry, not silently assumed covered; a fast-follow could add these if product asks. |
| R5 | **`config/v3/plans` has zero existing production callers anywhere in the codebase.** `create_plan` is its first real use — untested edge cases are more likely than on the console-verified `v2` surface. | Medium | Elevated test-plan scrutiny for `create_plan` specifically (unit + e2e against a real console). |
| R6 | **Update (PUT) is not in this story.** The ticket title says "creation **and update**", but with editing scoped to Stage 3 (SAF-35485) and no draft to re-open, `create_plan` is create-only. | Low-Medium | Named here rather than silently dropped; confirm with the ticket owner whether Stage 1 must carry an update path, in which case a sibling `update_plan` (PUT `config/v3/plans/{id}`) is a small addition to Phase 1. |
| R7 | **FR2's CVE/named-threat-group search remains only partially closed.** `tags_filter`'s generic group-keyed shape supports it, but there is no dedicated `cve_filter`/`threat_actor_filter` — the skill must know the exact tag group names. | Low-Medium | Document the exact group names in the tool description; the companion skill PRD encodes this vocabulary for Helm. |
| R8 | **The skill now owns plan-body assembly**, including filter nesting and step ordering. An LLM emitting a subtly wrong body is a new failure surface that the original nine-tool design didn't have (there, the server held the structure). | Medium | `create_plan`'s per-path validation is the backstop — a malformed body is rejected with the offending path named, never silently persisted. The DAG, the riskiest structure, is built by the tool rather than the model. The companion skill PRD carries the body contract as a `references/` file rather than relying on inline prose. |

---

## 10. Future Enhancements

- **`update_plan` (PUT)** for scenario editing — Stage 3, SAF-35485; see Risk R6 if Stage 1 must carry it.
- **A `preview_token`-style handshake** requiring a fresh statistics check before `create_plan` will persist, if
  R2's skill-enforced confirmation proves insufficient in practice.
- **Filter-based / criteria-based simulator selection** (the OS-half of `scenario-step-grouping.md` rule 5's
  "criteria" mode) — Stage 2, SAF-35484.
- **Automatic simulator shortlist suggestion** based on the planned attacks — Stage 2, SAF-35484.
- **Partial-impact / fail-rate conflict handling** with a configurable per-step threshold and swap-or-proceed
  choice — Stage 2, SAF-35484.
- **Edit-mode step placement**, **OOB-vs-custom scenario differentiation**, **`rename_scenario`/`delete_scenario`
  tools** — Stage 3, SAF-35485.
- **Data asset / proxy / impersonated-user association** — Stage 4, SAF-35051.
- **Dedicated first-class `cve_filter`/`threat_actor_filter` parameters** instead of routing through the generic
  `tags_filter` — candidate fast-follow if usage shows the generic shape is friction-prone.
- **Full console-validation parity** (step-name length, branching validity, attacker/target-presence at save
  time) — see Risk R4.

---

## 11. Executive Summary

- **Issue/Feature Description**: Enable Helm to build and save a custom Validate scenario entirely through
  conversation, with the conversation orchestrated by a Helm skill and persistence handled by a single MCP tool.
- **What Was Built**: One new mutating tool (`create_plan` — validation, DAG assembly, `config/v3/plans` POST)
  and one enhanced read tool (`get_playbook_attacks` gains type/phase/tag filters).
- **Key Technical Decisions**: exactly one public entry point, so validation, Propagate exclusion and rate
  limiting have a single enforcement point; the tool is stateless, which removes the original design's
  process-wide draft cache and its cross-user eviction hazard; the execution DAG is assembled by the tool rather
  than by the calling model; attack selection is one mode per step (explicit ids XOR criteria/tags), grounded in
  the ticket's own attached grouping spec; simulator selection stays explicit-id-only per FR5's scope boundary;
  Propagate exclusion (FR1/DoD3) is structural — no `tags` input surface exists to guard.
- **Scope Changes**: **This PRD was restructured on 2026-09-06.** The original design shipped nine granular
  draft-mutation tools backed by an in-process cache; the owner's decision that the Helm skill orchestrates and
  MCP only persists collapsed that to one tool. FR13's literal nine-tool contract is therefore substantially
  diverged from and **needs owner sign-off** (Risk R3). Earlier, FR13's server-assigned `scenario_id`/`step_id`
  semantics had already been found unimplementable (no incremental step API, no server draft, zero-step plans
  rejected). FR14 was added post-brainstorm as skill-layer behavior.
- **Business Value Delivered**: replaces a 5-screen manual console flow with a conversational one, backed by the
  same authoritative impact/conflict data the console itself uses, with Propagate scenarios structurally
  excluded regardless of account licensing.

---

## 13. Change Log

| Date | Change Description |
|---|---|
| 2026-09-02 16:49 | PRD created — initial draft |
| 2026-09-03 15:20 | Fetched latest SAF-35508 (PR #91, `de8afff`) at user request — the three `get_scenario_*` tools are now implemented (1932 tests passing), not "not yet implemented" as originally written. Corrected Component F, §6, and Risk R1: `attack_ids` on `get_scenario_attack_blockers` is required not optional; `get_scenario_blocked_entities`'s verdict is five states not three; `fix_lever` was removed (SAF-35568); AC-4 is partially verified; PR #91 has an open merge conflict against `main`. |
| 2026-09-06 | **Architecture restructured on owner decision**: exactly one public entry point for scenario creation, with the Helm skill as the flow orchestrator. Nine mutating tools + in-process draft cache → one stateless `create_plan` tool; the granular composition logic becomes private Python; `list_simulators` dropped (`get_console_simulators` covers it); the pre-save gate moves from inside the tool to the skill's preview stage, using SAF-35508's ad-hoc-body statistics tools (owner verified the statistics endpoint does not require `actions`/`edges`). Phases 7→2. New risks R2 (confirmation now skill-enforced), R3 (FR13 divergence, **needs owner sign-off**), R6 (update/PUT not in Stage 1), R8 (skill owns body assembly); former R2 (draft-cache single-worker state) retired with the cache. |
| 2026-09-06b | **Rescoped on owner decision: the write tool leaves this repo.** `create_plan` becomes `createValidateScenario`, a native Helm tool in `breach-genie` (companion PRD Component H / Phase 7), which gains a Zod-enforced body contract, `requireApproval: true` for a platform-enforced save confirmation, and an optional per-account `featureFlag` — none of which the MCP surface could offer. This repo's remaining scope is read-only search parity: `get_playbook_attacks` gains attack-type/phase/tag filters, one phase. Superseded write-path design is retained and clearly marked, because the companion tool inherits all of its findings. |
