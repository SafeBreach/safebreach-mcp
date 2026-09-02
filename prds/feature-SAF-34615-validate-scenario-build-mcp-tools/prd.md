# MCP support for Validate scenario creation and update (Stage 1) — SAF-34615

## 1. Overview

- **Title**: MCP support for Validate scenario creation and update (Stage 1) — SAF-34615
- **Task Type**: Feature
- **Purpose**: Today, building a custom Validate scenario is a manual, multi-screen console flow (Studio, Add
  Simulators Select/Checkout, Requirements Status). This story exposes that flow as a set of discrete, low-level
  MCP tools so Helm can guide a user through building a scenario conversationally — proposing an attack plan
  grouped into themed steps, letting the user pick simulators, surfacing only conflicts that actually matter, and
  saving a fully configured, ready-to-run scenario. Running or scheduling the scenario is explicitly excluded.
- **Target Consumer**: Helm (SafeBreach's AI agent), and — through Helm — any SafeBreach customer or internal
  user who talks to Helm to build a scenario instead of using the console directly.
- **Target Roles (RBAC)**: No new roles. Every tool call carries the caller's own console API credentials
  (existing `get_auth_headers_for_console`/RBAC pattern); a user can only build/save scenarios their console
  account is already authorized to create.
- **Key Benefits**:
  1. Turns a 5-screen manual console flow into a guided conversation with the same underlying validation.
  2. Keeps impact and conflict numbers backed by one authoritative source (the Core statistics engine) instead of
     letting an AI agent estimate them.
  3. Structurally keeps Propagate scenarios and attacks out of this flow, regardless of account licensing.
- **Business Alignment**: Epic SAF-34231, "Helm Skills & Tools for CTEM answer quality." Stage 1 of 4
  (SAF-35484 Stage 2 — filter-based simulator selection; SAF-35485 Stage 3 — editing; SAF-35051 Stage 4 — asset
  association).
- **Originating Request**: [SAF-34615](https://safebreach.atlassian.net/browse/SAF-34615), reported by Tal Rotem.

**Companion PRD**: the Helm-side orchestration this capability is designed for — search strategy, step-grouping
procedure, confirmation cadence, conflict-to-plain-language translation, and simulation-count presentation — is a
separate deliverable in `breach-genie`, branch `feature/SAF-34615-validate-scenario-building-skill`,
`prds/feature-SAF-34615-validate-scenario-building-skill/`. Same JIRA ticket, no subtask split, tracked as two
repos/branches/PRs by design (see this PRD's `context.md` §6 Decision 6). **This PRD's Section 5 (Example
Customer Flow) is omitted for that reason — the user-facing conversation is that PRD's content, not this one's.**

---

## 1.5. Document Status

| Field | Value |
|---|---|
| **PRD Status** | Draft |
| **Last Updated** | 2026-09-02 16:49 |
| **Owner** | AI Agent (Claude), planning session with Boris Berezovsky |
| **Current Phase** | N/A |

---

## 2. Solution Description

### Chosen Solution

Eight new mutating MCP tools plus one enhanced read tool, all in `safebreach_mcp_studio`, built around an
**in-process draft cache**: `create_scenario` mints a `draft_id` and seeds a `ValidatePlan`-shaped body
(`{name, steps: []}`) in a new bounded `SafeBreachCache`. Every subsequent tool (`add_step`,
`add_attacks_to_step`, `add_simulators_to_step`, and their `remove_*` counterparts) takes `draft_id` and mutates
that cached body locally — no server write happens until `save_scenario`, which assembles the final
`config/v3/plans` request (adding `type:'validate'` and `propagateDefinition:null`, fields the draft never
carries), POSTs/PUTs it, and evicts the draft.

Attack selection on `add_attacks_to_step` accepts either explicit `attack_ids[]` (→ `attacksFilter.playbook`) or
exactly one of `attack_type_filter`/`attack_phase_filter`/`tags_filter` (→ `attacksFilter.attackType`/
`attackPhase`/`tags[group]`) — never both in one call. Simulator selection on `add_simulators_to_step` accepts
**only** explicit `simulator_ids[]` — no filter escape hatch, because FR5 explicitly restricts Stage 1 to manual
simulator selection (filter-based selection is Stage 2, SAF-35484). `get_playbook_attacks` gains matching
`attack_type_filter`/`attack_phase_filter`/`tags_filter` parameters so Helm can discover which attacks match a
filter before committing it live into a step.

### Alternatives Considered

| Alternative | Pros | Cons | Why not chosen |
|---|---|---|---|
| **Stateless — Helm holds the full plan body across calls** (mirrors `get_plan_statistics`'s own ad-hoc-body input) | Zero new infra; no cache expiry/eviction/multi-worker risk at all | Every mutating call round-trips a potentially large nested JSON body; risks the LLM mangling a large structure over many turns | Draft-cache is closer to FR13's literal contract and to the console's own throwaway-uuid draft model; the token/fidelity cost was judged worse than the cache's documented restart risk |
| **Persist immediately on `create_scenario`** (real `scenario_id` from turn one, read-modify-write PUT per `add_*` call) | Matches FR13's literal text most closely; survives process restarts (state in Postgres, not memory) | Contradicts the console's own verified behavior (§6.4 of `context.md` — Studio never persists before Save); publishes an unfinished scenario into the user's real catalog before they've agreed to save it; a Validate plan cannot even be created with zero steps (server-side 400), so "create empty, then add steps" is not just undesirable but **impossible** this way | Product risk (half-built scenarios visible/nameable in the customer's catalog) outweighs the console-restart benefit |
| **Config server** (co-locate with `get_scenarios`/`get_scenario_details`/`get_console_simulators`) | Architecturally closer to the backend service that actually owns Plan/Step CRUD; keeps scenario read+write together | Splits the build→check→run arc across two servers; would be Config's first-ever mutating tool | Studio already owns `get_plan_statistics`'s successors and `run_scenario`; keeping build-check-run in one server won out |
| **`config/v2/plans`** instead of `v3` | Self-guards `type='validate'` automatically on create; exact console behavior, easiest to diff for FR9 parity | Flagged `// DELETE WHEN v2 IS REMOVED` in its own code | User chose the forward-looking surface; the self-guard is rebuilt explicitly in `save_scenario` instead |

### Decision Rationale

The draft-cache design is the only one of the three storage alternatives consistent with a hard platform
constraint: `configuration`'s Plan write API has no incremental step endpoint (`PUT` deletes and recreates
**every** step on every save) and rejects a zero-step plan outright. Building anything that assumes an
incrementally-addressable server-side scenario would not work against the real API. Studio-as-home and
v3-as-surface were user decisions (see `context.md` §7 Decisions 3-4) made with full knowledge of their
tradeoffs, not default picks.

---

## 3. Core Feature Components

### Component A — Draft Scenario Store

**Purpose**: New infrastructure. Holds an in-progress, not-yet-saved scenario's accumulating `name`/`steps[]`
across multiple tool calls in one conversation, standing in for the server-side draft concept that does not
exist in the underlying platform.

**Key Features**:
- A new bounded `SafeBreachCache` instance in `safebreach_mcp_studio` (e.g. `scenario_draft_cache`), following
  the `studio_draft_cache` pattern (`studio_functions.py:51`) but sized and TTL'd for a multi-turn conversational
  build rather than a single attack-draft edit — proposed starting values `maxsize=20`, `ttl=3600` (60 min),
  flagged as tunable pending real usage data.
- `create_scenario(name?: str, console: str) -> draft_id, seeded body` — mints a `uuid4` draft id, stores
  `{"name": name or "", "steps": []}`.
- Every mutating tool below reads-modifies-writes this cache entry by `draft_id`; a `draft_id` not found in the
  cache (evicted by TTL, or the process restarted) is a clear, typed error — never a silent no-op.
- `save_scenario` is the only tool that evicts an entry (on success) or leaves it in place (on failure, so the
  user doesn't lose work to a transient save error).

**Integration points**: none outside this repo. Pure new Python state, no new external API call.

### Component B — Step & Attack Composition

**Purpose**: Build up the themed steps and their attack selections that make up a scenario, before any
simulator is chosen (FR4's ordering).

**Key Features**:
- `add_step(draft_id, step_name: str) -> updated draft`. **`step_name` is required with no default** — the
  console's own `getDefaultStep` names steps `"Step 1"`/`"Step 2"` (`planUtils.ts:160`), which is exactly the
  anti-pattern `scenario-step-grouping.md` rule 1 forbids ("Never leave steps named 'Step 1', 'Step 2'"). This
  tool must not replicate that console behavior.
- `remove_step(draft_id, step_name) -> updated draft`. Removes the step and its attacks/simulators.
- `add_attacks_to_step(draft_id, step_name, attack_ids?: list[int], attack_type_filter?: str,
  attack_phase_filter?: str, tags_filter?: dict[str, list[str]]) -> updated step attack selection`.
  - `attack_ids` is mutually exclusive, per call, with the three filter parameters combined — grounded directly
    in `scenario-step-grouping.md` rule 5 ("a step can select attacks by criteria, explicit playbook_ids, or
    attack_tags" — a free choice, not a combination). Passing both is a validation error.
  - `attack_ids` → merges into `attacksFilter.playbook.values` (`operator:'is'`) — **verified** as the real,
    orchestrator-implemented explicit-id filter (`orchestrator/src/server/other/playbook_filter.js:53`,
    `valuesExtractorByFilter.playbook = move => move.id`); the schema's `methodIds` field has no implementation
    anywhere in `orchestrator/src` and must not be used.
  - `attack_type_filter` → `attacksFilter.attackType`; `attack_phase_filter` → `attacksFilter.attackPhase`
    (accepts `infiltration|lateral|exfiltration|host_level`, mapped internally to the orchestrator's `Package`
    enum `INFILTRATION=2|LATERAL=1|EXFILTRATION=0|HOST_LEVEL=5`); `tags_filter` → `attacksFilter.tags[group]`,
    a generic group-keyed dict (e.g. `{"Threat Actor": ["APT29"]}`) covering Threat Actor, CVE, and custom tags
    without needing a dedicated parameter per group.
  - Repeated calls against the same axis (e.g. two `attack_ids` calls) **extend** that axis's `values`, they
    don't replace it.
  - **Scope note carried into the tool description**: `scenario-step-grouping.md` rule 5's `criteria` mode is
    defined as attack type **+ OS** together. The OS half is a simulator filter, and FR5 restricts Stage 1 to
    manual simulator selection only — so this tool only ever builds the attack-side half of true "criteria"
    mode. The tool's own description must say this plainly.
- `remove_attacks_from_step(draft_id, step_name, attack_ids: list[int]) -> updated step attack selection`.
  Removes ids from `attacksFilter.playbook.values` only — removing from a criteria-based filter isn't a
  well-defined operation without negation logic Stage 1 doesn't need.

**Integration points**: none outside this repo at call time (pure local mutation); the resulting `attacksFilter`
shape is exactly what `get_scenario_simulation_counts`/`get_scenario_blocked_entities`/`get_scenario_attack_blockers`
(Component F dependency) and the final `save_scenario` POST/PUT consume.

### Component C — Simulator Composition

**Purpose**: Let the user browse and manually pick simulators for a step, per FR5.

**Key Features**:
- `list_simulators(filters?: dict) -> candidate simulator list`. Read-only (`readOnlyHint=True`, no rate-limit
  gate). Reuses `get_console_simulators`'s existing filter vocabulary (connected status, OS, name) — browse-only,
  never auto-suggests based on the planned attacks (explicitly out of scope, FR5).
- `add_simulators_to_step(draft_id, step_name, role: 'attacker'|'target', simulator_ids: list[str]) -> updated
  step simulator selection`. **Explicit ids only — no filter escape hatch on the simulator side**, unlike
  `add_attacks_to_step`. This is a deliberate asymmetry, not an oversight: FR5's text is explicit that
  "automatic simulator suggestion based on the planned attacks is out of scope for this story," and the ticket's
  own Future Scope section names "filter based simulator selection... matching the console's Add Simulators
  flow" as Stage 2 (SAF-35484). `role` determines **which** filter object the selection is written into
  (`attackerFilter.simulators` vs `targetFilter.simulators`) — it is not itself a filter value; both use the
  same real, orchestrator-implemented key (`orchestrator/src/server/other/simulators_filter.js:6,17`,
  `valuesExtractorByFilter.simulators = simulator => simulator.id`).
- `remove_simulators_from_step(draft_id, step_name, role, simulator_ids: list[str]) -> updated step simulator
  selection`.

**Integration points**: `list_simulators` proxies the existing `get_console_simulators` business logic
(`safebreach_mcp_config/config_functions.py`) rather than duplicating it.

### Component D — Attack Search Parity

**Purpose**: Let Helm discover which attacks match a type/phase/tag before committing that filter live into a
saved step (closing the "select blind" gap the escape hatch in Component B would otherwise create), and close
FR2's CVE/named-threat-group bulk-search gap found during investigation as a side effect.

**Key Features**:
- `get_playbook_attacks` (existing tool, `safebreach_mcp_playbook`) gains `attack_type_filter`,
  `attack_phase_filter`, `tags_filter` parameters, in the same style as its existing `mitre_technique_filter`/
  platform filters — comma-separated where applicable, applied Python-side against the already-cached full
  attack fetch (`_get_all_attacks_from_cache_or_api` → `filter_attacks_by_criteria`). No new upstream API call:
  the raw tag data (including these axes) is already present in every fetched attack; it is simply not carried
  through `transform_reduced_playbook_attack` today unless `include_tags=True`.

**Integration points**: `safebreach_mcp_playbook/playbook_types.py`, `playbook_functions.py`.

### Component E — Console-Validation Parity Guard (FR9, FR1/DoD3)

**Purpose**: Everything the console enforces that the raw `config/v3/plans` API does **not** — so this MCP path
is not a backdoor around console logic (FR9), and so no scenario can be created with a Propagate attack in it
regardless of license (FR1/DoD3).

**Key Features**:
- **`save_scenario` force-sets `type:'validate'` and `propagateDefinition:null`** on every create and update
  request. `config/v3/plans` does **not** self-guard this the way `v2` does — `validatePlanShape`
  (`configuration/src/server/utils/model-validators.js:45-59`) requires the pairing, so this must be explicit,
  not inherited.
- **No tool accepts a `tags` input parameter in Stage 1** — closes the legacy `tags:['ALM']` Propagate signal
  (verified: `orchestrator`'s `isPropagateTest` ORs `type==='propagate'` with `systemTags.includes('ALM')`,
  and plan `tags` become `systemTags` at fire time) by never exposing the input surface that could set it,
  rather than building a reject-filter for an input this story doesn't need.
- **DoD3's attack-level guard is structural, not a new check**: `get_scenario_blocked_entities`/
  `get_scenario_attack_blockers` (Component F's dependency) already reuse the exact orchestrator method
  (`PlanPreparation.filterMoves`) that strips every `ALM=1`-tagged move for any step where `!step.isPropagate`
  — and since these tools only ever build `Plan.steps[]` (never `propagateDefinition`), that predicate is
  always true. Any Propagate attack a user asks for scores zero simulations and is caught by DoD6's removal
  flow (Component F). `save_scenario` must therefore require a fresh, all-clear `get_scenario_blocked_entities`
  check immediately before persisting — not merely offer one.
- **`save_scenario` handles the DB-level unique-constraint failure** (`(name, accountId)` unique index,
  `configuration/src/server/models/plans.js:101-108`) with a clear, typed error — the console has no
  client-side pre-check for this either, so an MCP-side pre-check would be a nice-to-have, not parity.
- **Every step created by `add_step` requires a real, themed name** (Component B) — the one console default
  this story deliberately does not mirror.
- **Documented, not built, this story**: step-name length/uniqueness-within-scenario, and most "is this
  scenario runnable" logic (branching validity, attacker+target presence) are **client-only in the console
  today** (verified — no server-side equivalent found in `configuration`). Building full parity for all of
  these is out of scope for Stage 1; Section 9 (Risks) names this explicitly so it isn't silently assumed done.

**Integration points**: `save_scenario`'s implementation in Component A/F; no new files beyond what those
components already touch.

### Component F — Impact/Conflict Integration (dependency, not built here)

**Purpose**: Document how this story's tools consume SAF-35508's statistics tools — no new code in this PRD's
scope, but load-bearing for FR6/FR7/FR12/FR14/DoD2/DoD5/DoD6.

**Key Features**:
- **Dependency, not yet implemented as of this PRD's writing.** SAF-35508 (`feature/SAF-35508-plan-statistics-
  mcp-tool`, this branch's base) is retiring its single `get_plan_statistics` tool for three narrow tools per
  owner decision D4 (2026-09-02, confirmed by the user as the plan to design against, verified directly against
  the uncommitted diff in that worktree — not yet pushed): `get_scenario_simulation_counts` ("how many
  simulations?"), `get_scenario_blocked_entities` ("is anything fully blocked?" — three-state verdict:
  blocked / nothing blocked / nothing evaluated), `get_scenario_attack_blockers` ("why didn't attack #N run?").
  All three call the same shipped, untouched `sb_get_plan_statistics` plumbing.
- **FR12's "re-check after any change"** may now require calling more than one of the three (e.g.
  `get_scenario_blocked_entities` for the verdict, `get_scenario_simulation_counts` for the number) — this
  story's tools don't call these themselves (that orchestration is Helm's job per FR13), but their response
  shapes (the accumulating draft body) must be exactly what those three tools expect as an ad-hoc `scenario`
  input.
- **FR14 (added post-brainstorm)**: presenting the resulting count to the user is skill-layer behavior
  (`breach-genie`), not a tool change — noted here only so the draft body's shape is confirmed compatible with
  what `get_scenario_simulation_counts` needs.

**Integration points**: none in this repo's code — purely a contract dependency. Tracked as Risk R1 (Section 9).

---

## 4. API Endpoints and Integration

### Existing APIs Consumed

| API | URL | Method | Consumed by |
|---|---|---|---|
| Plan create/update | `config/v3/accounts/{accountId}/plans[/{id}]` | POST / PUT | `save_scenario` (Component E) |
| Plan statistics (via three successor tools, dependency) | `orch/v1/accounts/{accountId}/plan/statistics` | POST | Indirectly — this story's draft body is designed to be fed to `get_scenario_simulation_counts`/`get_scenario_blocked_entities`/`get_scenario_attack_blockers` by Helm, not called directly by these tools |
| Playbook attacks (moves) | `{base_url}/api/kb/vLatest/moves?details=true` | GET | Component D, via the existing `get_playbook_attacks` fetch-all-and-cache path — no new call |
| Console simulators | proxied via existing `get_console_simulators` | — | Component C (`list_simulators`) |

### New MCP Tools to Create

All in `safebreach_mcp_studio`, `readOnlyHint=False` unless noted, each with a rate-limiting gate
(`check_limit` before the mutating step, `record_action` only after success — `CLAUDE.md`'s documented pattern).

| Tool | Input | Output | Errors |
|---|---|---|---|
| `create_scenario` | `name?: str`, `console: str` | `draft_id`, seeded `{name, steps: []}` | — |
| `add_step` | `draft_id`, `step_name: str` (required) | updated draft, new step's identity within it | draft not found; duplicate step name in this draft |
| `remove_step` | `draft_id`, `step_name` | updated draft | draft/step not found |
| `add_attacks_to_step` | `draft_id`, `step_name`, `attack_ids?: list[int]` XOR (`attack_type_filter?`, `attack_phase_filter?`, `tags_filter?`) | updated step attack selection | draft/step not found; both id-list and filter params supplied (mutually exclusive) |
| `remove_attacks_from_step` | `draft_id`, `step_name`, `attack_ids: list[int]` | updated step attack selection | draft/step not found; id not present |
| `list_simulators` | `filters?: dict` (connected status, OS, name) | candidate simulator list | — (**`readOnlyHint=True`, no rate-limit gate**) |
| `add_simulators_to_step` | `draft_id`, `step_name`, `role: 'attacker'\|'target'`, `simulator_ids: list[str]` | updated step simulator selection | draft/step not found; invalid role |
| `remove_simulators_from_step` | `draft_id`, `step_name`, `role`, `simulator_ids: list[str]` | updated step simulator selection | draft/step not found |
| `save_scenario` | `draft_id`, `save_as_new: bool`, `name?: str` (required if `save_as_new`) | `scenario_id`, `name` | draft not found; unclean `get_scenario_blocked_entities` verdict; DB unique-constraint violation on `(name, accountId)`; upstream 4xx/5xx |

### Enhanced Existing Tool

| Tool | New parameters | Server |
|---|---|---|
| `get_playbook_attacks` | `attack_type_filter?: str`, `attack_phase_filter?: str`, `tags_filter?: dict[str, list[str]]` | `safebreach_mcp_playbook` |

---

## 6. Non-Functional Requirements

### Security & Compliance
- **Authentication**: every tool uses the existing per-console auth pattern (`get_auth_headers_for_console`,
  `check_rbac_response`) — no new auth mechanism.
- **RBAC**: inherited from the caller's console API token; no new roles.
- **Compliance (Propagate/license)**: FR1/DoD3's guard (Component E) is structural — no tool accepts a `tags`
  input, and `save_scenario` force-sets `type:'validate'`/`propagateDefinition:null` on every request,
  independent of the account's Propagate license state.

### Technical Constraints
- **Hard dependency, not yet implemented**: `get_scenario_simulation_counts`/`get_scenario_blocked_entities`/
  `get_scenario_attack_blockers` (SAF-35508 D4, phases 7-9 "not started" as of this writing). This story's
  implementation phases can proceed on Components A-E independently, but Component F's contract, and therefore
  full DoD3/DoD5/DoD6/FR14 verification, is blocked until those tools exist.
- **Backward compatibility**: N/A — all new tools; `get_playbook_attacks`'s new parameters are additive/optional.
- **Deployment**: the draft cache assumes the single-process deployment `start_all_servers.py` runs today
  (verified — asyncio, one process, five ports, no `workers`/gunicorn). A future multi-worker deployment would
  break `draft_id` continuity across requests; not a concern for this story's target environment.

### Performance
- Draft cache sized for a multi-turn conversational build (proposed `maxsize=20`, `ttl=3600`), larger than
  `studio_draft_cache`'s `5`/`1800` (a single attack-draft edit is a much shorter-lived, lower-concurrency use
  case). Values are a starting proposal, not empirically validated — flagged for adjustment once real usage
  data exists.

---

## 7. Definition of Done

**Core Functionality**
- [ ] A user can, through conversation with Helm alone, build from scratch and save a fully configured,
      ready-to-run Validate scenario using only this story's tools (DoD1).
- [ ] No scenario is created with a `type='propagate'` plan or a `tags`-carried `'ALM'` marker through this
      flow, and no ALM-tagged attack survives into a saved scenario, regardless of the account's Propagate
      license (DoD3/FR1).
- [ ] No association of data assets, proxies, or impersonated users is handled by this flow (DoD4 — explicitly
      out of scope, covered by SAF-35051).
- [ ] `create_scenario`, `add_step`/`remove_step`, `add_attacks_to_step`/`remove_attacks_from_step`,
      `list_simulators`, `add_simulators_to_step`/`remove_simulators_from_step`, `save_scenario` are all
      registered, documented in `CLAUDE.md` (catalog entry + rate-limit gate row where applicable), and
      versioned in `CHANGELOG.md`.
- [ ] `get_playbook_attacks` supports `attack_type_filter`/`attack_phase_filter`/`tags_filter`.

**Quality Gates**
- [ ] Every test in `test-plan.md` for this feature is green, with evidence in `test-results/`.
- [ ] Draft-cache eviction and "draft not found" error paths are covered (process-restart / TTL-expiry
      simulation).
- [ ] `save_scenario`'s force-set of `type:'validate'`/`propagateDefinition:null` and its rejection of any
      `tags` input are covered by tests independent of SAF-35508's own test suite.
- [ ] `attack_ids` vs filter-parameter mutual exclusivity on `add_attacks_to_step` is covered (both-supplied
      rejection; each mode individually).

**Deployment Readiness**
- [ ] Rate-limiting gate table (`CLAUDE.md`) updated for all eight mutating tools.
- [ ] Dependency on SAF-35508's `get_scenario_*` tools is either merged and verified, or this story's own
      Phase 7 DoD gate documents the residual risk explicitly (Section 9, R1) rather than silently assuming it.

---

## 8. Implementation Phases

| Phase | Status | Completed | Commit SHA | Notes |
|---|---|---|---|---|
| Phase 1: Draft store + `create_scenario` | ⏳ Pending | - | - | |
| Phase 2: `add_step` / `remove_step` | ⏳ Pending | - | - | |
| Phase 3: `add_attacks_to_step` / `remove_attacks_from_step` | ⏳ Pending | - | - | |
| Phase 4: `get_playbook_attacks` filter parity | ⏳ Pending | - | - | Independent of Phase 3, sequenced after it to reuse the same filter vocabulary |
| Phase 5: `list_simulators` | ⏳ Pending | - | - | |
| Phase 6: `add_simulators_to_step` / `remove_simulators_from_step` | ⏳ Pending | - | - | |
| Phase 7: `save_scenario` | ⏳ Pending | - | - | Blocked on SAF-35508's `get_scenario_blocked_entities` for full verification (Risk R1) |

### Phase 1: Draft store + `create_scenario`

**Semantic Change**: Introduce the bounded in-process draft cache and the tool that creates an entry in it.

**Deliverables**: `scenario_draft_cache` instance; `sb_create_scenario` business function; `create_scenario`
tool registration; rate-limit gate; docs; tests.

**Implementation Details**:
- `safebreach_mcp_studio/studio_functions.py`: instantiate `scenario_draft_cache = SafeBreachCache(name=
  "scenario_drafts", maxsize=20, ttl=3600)` at module scope, alongside the existing `studio_draft_cache`.
- Add `sb_create_scenario(name: str | None, console: str) -> dict`: generates a `uuid4` string as `draft_id`;
  builds the seed body `{"name": name or "", "steps": []}`; stores it in `scenario_draft_cache` keyed by
  `draft_id`; applies the rate-limit gate (`check_limit` before the cache write, `record_action` after — this
  is a local operation, so "success" means the cache write succeeded, not an upstream API call); returns
  `{draft_id, name, steps: []}`.
- `safebreach_mcp_studio/studio_types.py`: add `get_create_scenario_response_mapping(draft_id, body) ->
  dict[str, Any]` following the existing flat dict-mapping pattern (no pydantic/TypedDict).
- `safebreach_mcp_studio/studio_server.py`: register `create_scenario` with
  `ToolAnnotations(readOnlyHint=False, destructiveHint=False)`, a thin wrapper formatting the markdown response,
  `except ValueError`/`except Exception` arms matching every other tool in the file.
- `CLAUDE.md`: add a rate-limiting gate table row for `create_scenario`; add a numbered catalog entry under
  Studio Server; add a bullet to the Caching Strategy section noting the new `scenario_drafts` cache
  (`maxsize=20`, `ttl=3600`).
- `CHANGELOG.md` / `pyproject.toml`: new `### Added` bullet, minor version bump.

**What can go wrong**: a `name` collision is not checked here (the DB-level unique constraint is Phase 7's
concern) — two drafts can share a proposed name simultaneously, since nothing is persisted yet.

**Data flow**: caller → `create_scenario` tool → `sb_create_scenario` → `scenario_draft_cache.set(draft_id,
body)` → response. No external HTTP call in this phase.

**Git Commit**: `feat(studio): add create_scenario tool and the scenario draft cache`

### Phase 2: `add_step` / `remove_step`

**Semantic Change**: Let a draft accumulate named steps.

**Deliverables**: `sb_add_step`, `sb_remove_step`; two tool registrations; tests.

**Implementation Details**:
- `sb_add_step(draft_id: str, step_name: str, console: str) -> dict`: reads the draft from
  `scenario_draft_cache`, raising a clear "draft not found" error if absent (evicted or unknown id); rejects an
  empty/whitespace-only `step_name` (mirrors the console's own `disallowEmpty` client check, since nothing
  server-side enforces this); rejects a `step_name` already present among the draft's steps (case-sensitive
  match, mirroring the console's `forbiddenValues` sibling-name check); appends a new step object
  `{"name": step_name, "attacksFilter": {}, "attackerFilter": {}, "targetFilter": {}}` (`attacksFilter`/
  `attackerFilter`/`targetFilter` start empty, matching `getStepsForApi`'s base-object convention rather than
  being omitted); writes the updated draft back to the cache; returns the full updated step list.
- `sb_remove_step(draft_id, step_name, console)`: same draft lookup; raises if `step_name` is not found; removes
  the step (and, implicitly, whatever attacks/simulators it held); writes back; returns the updated step list.
- Tool registrations follow Phase 1's pattern; both are rate-limited.

**What can go wrong**: removing a step that doesn't exist raises rather than silently no-opping — matches this
repo's convention of never masking a caller error as success.

**Data flow**: caller → tool → draft cache read → local list mutation → draft cache write → response. No
external HTTP call.

**Git Commit**: `feat(studio): add add_step and remove_step tools`

### Phase 3: `add_attacks_to_step` / `remove_attacks_from_step`

**Semantic Change**: Let a step accumulate an attack selection, by explicit id or by type/phase/tag filter.

**Deliverables**: `sb_add_attacks_to_step`, `sb_remove_attacks_from_step`; the `attacksFilter` construction
helper; tests covering both selection modes and the mutual-exclusivity rejection.

**Implementation Details**:
- A small internal helper builds/merges a `Filter` object (`{"operator": "is", "values": [...], "name": key}`)
  for a given `attacksFilter` key, extending `values` if the key already exists on the step rather than
  overwriting it.
- `sb_add_attacks_to_step(draft_id, step_name, attack_ids: list[int] | None, attack_type_filter: str | None,
  attack_phase_filter: str | None, tags_filter: dict[str, list[str]] | None, console)`:
  1. Look up the draft and the named step (raise if either is missing).
  2. Validate exactly one selection mode is present: `attack_ids` non-empty XOR at least one of the three
     filter parameters non-empty. Reject with a clear message if both or neither are supplied.
  3. If `attack_ids`: merge into the step's `attacksFilter.playbook` (key `"playbook"`, not `"methodIds"`).
  4. If `attack_type_filter`: merge into `attacksFilter.attackType`.
  5. If `attack_phase_filter`: map the input string (`infiltration|lateral|exfiltration|host_level`) to the
     orchestrator's `Package` integer (`INFILTRATION=2|LATERAL=1|EXFILTRATION=0|HOST_LEVEL=5`); merge into
     `attacksFilter.attackPhase`. An unrecognized phase string is a validation error, not a silent drop.
  6. If `tags_filter`: for each `{group: values}` entry, merge into `attacksFilter.tags[group]`.
  7. Write the draft back; return the step's updated `attacksFilter` (full, so the caller can see the
     accumulated state, not just what this call added).
- `sb_remove_attacks_from_step(draft_id, step_name, attack_ids: list[int], console)`: removes the given ids
  from `attacksFilter.playbook.values` only; raises if `attacksFilter.playbook` doesn't exist or an id isn't
  present in it (criteria-based removal is out of scope, per Component B's design note).

**What can go wrong**: a phase string outside the four known values; both `attack_ids` and a filter parameter
supplied together; removing an id that was never added.

**Data flow**: same local cache read-mutate-write shape as Phase 2; no external HTTP call.

**Git Commit**: `feat(studio): add add_attacks_to_step and remove_attacks_from_step tools`

### Phase 4: `get_playbook_attacks` filter parity

**Semantic Change**: Let the existing attack-search tool filter by the same type/phase/tag axes Phase 3
introduced, so Helm can discover matching attacks before committing a filter live into a step.

**Deliverables**: three new optional parameters on `get_playbook_attacks`; corresponding filtering logic; tests.

**Implementation Details**:
- `safebreach_mcp_playbook/playbook_types.py`: extend `filter_attacks_by_criteria` to accept
  `attack_type_filter`, `attack_phase_filter`, `tags_filter`, applied against the **raw** per-attack tag data
  (the same nested `[{id, name, values}]` shape `_transform_tags` already parses) — this requires threading the
  raw tags through to the filter step, since `transform_reduced_playbook_attack` currently drops them unless
  `include_tags=True`.
- `safebreach_mcp_playbook/playbook_functions.py`: add the three parameters to `sb_get_playbook_attacks`'s
  signature; pass them through to the extended filter function; same comma-separated, OR-logic, case-sensitive-
  where-applicable style as `mitre_technique_filter`/the platform filters.
- `safebreach_mcp_playbook/playbook_server.py`: update the tool's registered parameter list and description.
- `CLAUDE.md`: update `get_playbook_attacks`'s catalog entry.

**What can go wrong**: an attack with no tag data for a requested axis should be excluded (not error), matching
the existing platform-filter behavior for attacks with `None` platform.

**Data flow**: no new upstream call — filtering happens against the already-cached full attack fetch.

**Git Commit**: `feat(playbook): add attack_type_filter, attack_phase_filter, tags_filter to get_playbook_attacks`

### Phase 5: `list_simulators`

**Semantic Change**: Expose a browse-only simulator listing scoped to scenario building.

**Deliverables**: `sb_list_simulators`; tool registration (`readOnlyHint=True`).

**Implementation Details**:
- `sb_list_simulators(filters: dict | None, console) -> list[dict]`: delegates to the existing
  `get_console_simulators` business logic in `safebreach_mcp_config/config_functions.py` (same connected-status/
  OS/name filters), returning the candidate list unchanged in shape — this tool adds no new filtering
  capability, only a Studio-server-local entry point so Helm doesn't need to reach across servers mid-build.
- No rate-limit gate (`readOnlyHint=True`); no CLAUDE.md gate-table row, per the `get_plan_statistics`
  precedent's "Not rate-limited" pattern.

**What can go wrong**: nothing new — errors are whatever `get_console_simulators`'s underlying call already
raises.

**Data flow**: caller → `list_simulators` → existing config-server simulator-listing logic → response. No new
external HTTP call.

**Git Commit**: `feat(studio): add list_simulators tool`

### Phase 6: `add_simulators_to_step` / `remove_simulators_from_step`

**Semantic Change**: Let a step accumulate an explicit, role-scoped simulator selection.

**Deliverables**: `sb_add_simulators_to_step`, `sb_remove_simulators_from_step`; tests.

**Implementation Details**:
- `sb_add_simulators_to_step(draft_id, step_name, role: str, simulator_ids: list[str], console)`: look up the
  draft/step; validate `role` is exactly `"attacker"` or `"target"`; merge `simulator_ids` into
  `attackerFilter.simulators` (if `role == "attacker"`) or `targetFilter.simulators` (if `role == "target"`) —
  same `Filter` merge helper as Phase 3, no filter-parameter alternative on this tool (Component C's documented
  scope boundary). Write back; return the step's updated `attackerFilter`/`targetFilter`.
- `sb_remove_simulators_from_step`: symmetric removal from the given role's `simulators.values`.

**What can go wrong**: an invalid `role` value; removing an id never added.

**Data flow**: local cache read-mutate-write; no external HTTP call.

**Git Commit**: `feat(studio): add add_simulators_to_step and remove_simulators_from_step tools`

### Phase 7: `save_scenario`

**Semantic Change**: Persist the draft as a real Validate plan, with the console-parity guards from Component E.

**Deliverables**: `sb_save_scenario`; the final wire-body assembler; tests (unit against a mocked
`config/v3/plans` response, plus e2e against a real console per Risk R6's elevated scrutiny).

**Implementation Details**:
1. Look up the draft; raise a clear "draft not found" error if absent.
2. **Pre-save gate**: call the equivalent of `get_scenario_blocked_entities` against the draft body (via the
   same `sb_get_plan_statistics` plumbing SAF-35508 exposes — exact call shape depends on that dependency
   landing, Risk R1) and require its three-state verdict to be "nothing blocked" or "nothing evaluated"-with-
   caller-override before proceeding; a "blocked" verdict is a typed error surfaced back to the caller (Helm),
   not a silent partial save.
3. Assemble the final wire body from the draft's `name`/`steps`, adding `type: "validate"` and
   `propagateDefinition: null` (never inherited from the draft, since the draft never carries them).
4. If `save_as_new` is true or the draft has no prior `scenario_id`: `POST config/v3/accounts/{accountId}/plans`
   with the assembled body (no `id`). Else: `PUT config/v3/accounts/{accountId}/plans/{id}`.
5. On a DB unique-constraint violation (`(name, accountId)`), surface a clear "name already in use" error
   rather than the raw Sequelize error.
6. On success: evict the `draft_id` entry from `scenario_draft_cache`; return `{scenario_id, name}` from the
   response.
7. On any failure: leave the draft entry in place so the user's work isn't lost to a transient error.

**What can go wrong**: the pre-save gate call itself failing (SAF-35508 dependency not yet available — Risk
R1); a name collision; an upstream 4xx/5xx from `configuration`.

**Data flow**: caller → `save_scenario` → (pre-save checkout call) → `config/v3/plans` POST/PUT → response →
draft cache eviction.

**Git Commit**: `feat(studio): add save_scenario tool`

---

## 9. Risks and Assumptions

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| R1 | **SAF-35508's `get_scenario_simulation_counts`/`get_scenario_blocked_entities`/`get_scenario_attack_blockers` are not yet implemented** (D4 phases 7-9, "not started" at PRD time) — this story's DoD3/DoD5/DoD6/FR12/FR14 depend on their exact contract. | High | Components A-E can be implemented and unit-tested against a mocked contract; final integration/e2e verification is blocked on SAF-35508 landing. Track explicitly at the Phase 7 DoD gate rather than assuming it will have landed by then. |
| R2 | **Draft cache is in-process, single-worker state.** A process restart or a future multi-worker deployment loses in-flight drafts. | Medium | Documented assumption (current deployment is confirmed single-process); `save_scenario` against a missing `draft_id` fails clearly rather than silently, so the failure mode is legible, not corrupting. |
| R3 | **This story's tool contract deliberately diverges from FR13's literal text** (no server `scenario_id`/`step_id` until save; filter-DSL parameters instead of plain arrays for some inputs). A reviewer judging "done" against the ticket's literal wording without reading this PRD's rationale could misjudge the implementation. | Medium | This PRD's Section 2 and `context.md` document every divergence with the platform constraint that forced it (no incremental step API, zero-step rejection, no server draft). Reference this PRD explicitly at the DoD/verification gate. |
| R4 | **FR2's CVE/named-threat-group search remains only partially closed.** `tags_filter`'s generic group-keyed shape (Component D) supports it, but there is no dedicated `cve_filter`/`threat_actor_filter` parameter — Helm must know the exact tag group name (`"CVE"`, `"Threat Actor"`) to use it. | Low-Medium | Document the exact group names in the tool description; the breach-genie skill (companion PRD) is the natural place to encode this vocabulary for Helm. |
| R5 | **Console validation parity is intentionally partial** (Component E) — step-name length/uniqueness and most "is this runnable" branching/attacker-target-presence logic are client-only in the console and are not rebuilt here. | Medium | Explicitly scoped out in Component E and this risk entry, not silently assumed covered; a fast-follow could add these if product asks. |
| R6 | **`config/v3/plans` has zero existing production callers anywhere in the codebase.** `save_scenario` is its first real use — untested edge cases are more likely than on the console-verified `v2` surface. | Medium | Elevated test-plan scrutiny for `save_scenario` specifically (unit + e2e), called out at the Phase 8 test-plan step. |
| R7 | **AC-4/T-35 on SAF-35508's own PRD (whether its numbers match the console) is unverified**, independent of the D4 tool-decomposition. | Low (inherited, not created by this story) | Not this story's risk to close, but worth tracking since DoD2 depends on it transitively. |

---

## 10. Future Enhancements

- **Filter-based / criteria-based simulator selection** (the OS-half of `scenario-step-grouping.md` rule 5's
  "criteria" mode) — Stage 2, SAF-35484.
- **Automatic simulator shortlist suggestion** based on the planned attacks — Stage 2, SAF-35484.
- **Partial-impact / fail-rate conflict handling** with a configurable per-step threshold and swap-or-proceed
  choice — Stage 2, SAF-35484.
- **Edit-mode step placement** (place suggested attacks into an existing matching step rather than always
  creating a new one), **OOB-vs-custom scenario differentiation**, **`rename_scenario`/`delete_scenario`
  tools** — Stage 3, SAF-35485.
- **Data asset / proxy / impersonated-user association** — Stage 4, SAF-35051.
- **Dedicated first-class `cve_filter`/`threat_actor_filter` parameters** instead of routing through the
  generic `tags_filter` — candidate fast-follow if Helm usage shows the generic shape is friction-prone.
- **Offering a matching catalog scenario as a starting point** instead of always building from scratch —
  unassigned in the ticket, candidate for a later story.
- **Full console-validation parity** (step-name length/uniqueness enforcement, branching validity,
  attacker/target-presence at save time) — see Risk R5.

---

## 11. Executive Summary

- **Issue/Feature Description**: Enable Helm to build and save a custom Validate scenario entirely through
  conversation, via a set of low-level, structured MCP tools.
- **What Was Built**: Eight new mutating tools (draft-backed scenario/step/attack/simulator composition plus
  save) and one enhanced read tool (`get_playbook_attacks` gains type/phase/tag filters), all in
  `safebreach_mcp_studio`, writing through `config/v3/plans`.
- **Key Technical Decisions**: an in-process draft cache stands in for the server-side draft the platform
  doesn't have; attack selection supports both explicit ids and a structured type/phase/tags filter (mutually
  exclusive per call, grounded in the ticket's own attached grouping spec); simulator selection stays
  explicit-id-only per FR5's own scope boundary; Propagate exclusion (FR1/DoD3) is structural (no `tags` input
  surface exists to guard) rather than a bolted-on filter.
- **Scope Changes**: FR13's literal tool contract (server-assigned `scenario_id`/`step_id` from the first call)
  was found unimplementable against the real platform (no incremental step API, no server draft, zero-step
  plans rejected) and replaced with the draft-cache design documented in Section 2. FR14 (present simulation
  counts to the user) was added post-brainstorm as skill-layer behavior. `get_playbook_attacks`'s filter
  expansion was added in-scope after the attacks-filter design surfaced the same gap FR2's investigation had
  already found.
- **Business Value Delivered**: replaces a 5-screen manual console flow with a conversational one, backed by
  the same authoritative impact/conflict data the console itself uses, with Propagate scenarios structurally
  excluded regardless of account licensing.

---

## 13. Change Log

| Date | Change Description |
|---|---|
| 2026-09-02 16:49 | PRD created — initial draft |
