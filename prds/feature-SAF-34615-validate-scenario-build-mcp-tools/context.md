# SAF-34615 — MCP support for Validate scenario creation and update (Stage 1)

**Status**: `Phase 3: Create Working Branch and PRD Context`

**Branch**: `feature/SAF-34615-validate-scenario-build-mcp-tools`
**Base**: `origin/feature/SAF-35508-plan-statistics-mcp-tool` (not `main` — see Dependencies)
**Repo**: `safebreach-mcp`
**Worktree**: `.claude/worktrees/feature+SAF-34615-validate-scenario-build-mcp-tools`

---

## 1. JIRA Ticket Summary

| Field | Value |
|---|---|
| Key | [SAF-34615](https://safebreach.atlassian.net/browse/SAF-34615) |
| Summary | MCP support for Validate scenario creation and update (Stage 1) |
| Type | Story |
| Status | In Progress |
| Priority | Medium |
| Assignee | Boris Berezovsky |
| Reporter | Tal Rotem |
| Epic | SAF-34231 — Helm Skills & Tools for CTEM answer quality |
| Team | Core |
| Sprint | Saf sprint 97 (created in Saf Sprint 95) |
| Original estimate | 3d |
| QA testing required | Yes |
| Design review | Not Required |
| Release notes type | External |
| Labels | `CTEM-dev`, `description-changed-in-sprint` |

### Background (from ticket)

Users can build custom Validate scenarios from scratch or by modifying a scenario from the
Scenarios Catalog, then configure steps, attacks, simulators, data assets, proxies, and
impersonated users before running them. Today this is a manual, multi-screen console flow
(Studio, Add Simulators Select/Checkout, Requirements Status). The goal is to expose this as an
interactive MCP-driven flow through Helm, so a user can describe a goal in conversation and reach
a fully configured, ready-to-run scenario — with Helm surfacing the meaningful decision points and
their impact along the way instead of a silent one-shot action.

### Goal (from ticket)

Enable Helm to guide a user through building a new custom Validate scenario from scratch, entirely
through conversation. Helm proposes a phased attack plan, lets the user pull up and select
simulators, and surfaces only the conflicts and gaps that meaningfully affect the scenario, always
asking for confirmation before adding anything the user did not explicitly request. The end result
is a **saved, ready-to-run scenario**. Running or scheduling it is a separate, later action that
Helm may suggest but this capability does not perform.

### Functional Requirements (verbatim intent)

| # | Requirement | Owner |
|---|---|---|
| FR1 | **Restrict this flow to Validate scenarios.** Propagate scenarios must never be produced or modified through this flow, regardless of whether the account holds a Propagate license. | SAF-34615 |
| FR2 | **Build the attack plan from existing content.** Translate the user's goal into attack phases and specific attacks by searching existing SafeBreach content (scenarios catalog, attack IDs, named threat groups, CVEs, attack playbook) rather than inventing an attack list. Also check the playbook for relatively new attacks matching the goal and suggest adding them. | SAF-34615 |
| FR3 | **On creation, group the attacks into steps.** Check which existing step fits the attack type/category and use it for grouping; only propose a new step when no existing step is a reasonable fit. Grouping logic defined in `scenario-step-grouping.md` (see §2). | SAF-34615 |
| FR4 | **Present the planned structure before configuring simulators.** Present planned step+attack structure in plain language and get confirmation before touching simulator selection. | SAF-34615 |
| FR5 | **Let the user pull up a simulator list and select manually.** Basic filters (connected only, OS, name) or all simulators; the user says which to select. Automatic suggestion is out of scope (→ SAF-35484). | SAF-34615 |
| FR6 | **Source impact and conflict data from the Core checkout API.** All simulation-count estimates and all configuration conflicts must come from the same Core checkout/validation API the console uses. MCP must not estimate independently. | **SAF-35508 (done)** |
| FR7 | **Translate conflicts into plain language with a suggested fix.** Never surface a raw console-style conflict reason as-is. Scope for this story: proactively act only on two hard-failure cases — an attack that cannot run on any selected simulator, and a simulator that ends up with zero associated attacks. Inform the user those are inapplicable and will be removed; no swap offer. | **SAF-35508 (done)** |
| FR8 | **Confirm decisions one or two at a time**, in the order they naturally arise, not batched upfront. A final summary of all choices before saving. | SAF-34615 |
| FR9 | **Console-level validations.** All validations the console performs today must also apply when creating/updating via Helm. The Helm path must not be a backdoor around existing console logic. | SAF-34615 |
| FR10 | **Treat AI-generated attacks like any other attack.** Attacks from SafeBreach's AI-generated Attack Scenarios category are searchable and proposable through the same logic, with no special-casing. | SAF-34615 |
| FR11 | **Exclude run and schedule triggering.** Capability ends once a scenario is fully configured and saved in a ready-to-run state. Helm may *suggest* running/scheduling; the MCP tool must not perform it. | SAF-34615 |
| FR12 | **Re-check the scenario after any change.** If the user changes an earlier decision, automatically re-run the impact/conflict check across the full current configuration and proactively surface new conflicts. | SAF-34615 (orchestration) |
| FR13 | **Define the low-level MCP tool set and contract.** Discrete tools, each one clear scenario-configuration operation, structured input/output. No tool accepts a free-text goal or returns an interpreted/narrative field; Helm owns all sequencing and interpretation. | SAF-34615 |

### FR13 — tool contract as specified in the ticket

| Tool | Input | Output |
|---|---|---|
| `search_scenarios` / `get_scenario` | — | existing tools |
| `create_scenario` | `name` (optional) | `scenario_id` |
| `add_step` / `remove_step` | `scenario_id`, `step_name` | `step_id` |
| `add_attacks_to_step` / `remove_attacks_from_step` | `step_id`, `attack_ids[]` | updated attack list for the step |
| `list_simulators` | `scenario_id`, optional basic `filters` (connected status, OS) | candidate simulator list (browse-and-pick, not auto-suggest) |
| `add_simulators_to_step` / `remove_simulators_from_step` | `step_id`, `simulator_ids[]`, `role` (attacker/target), `selection_mode` (manual only) | updated simulator list for the step |
| `checkout_scenario` | `scenario_id` | per step: expected simulation count, runnable count, structured (untranslated) conflict list, from the Core checkout/validation API |
| `save_scenario` | `scenario_id`, `save_as_new` (bool), `name` (required if `save_as_new`) | saved `scenario_id`, `name` |

> **Note (ticket):** associating data assets, proxies, and impersonated users to a scenario or its
> steps is **out of scope** here — covered by the Stage-4 story (SAF-35051).

> **Superseded:** SAF-35508 renamed `checkout_scenario` → **`get_plan_statistics`** and widened its
> input from `scenario_id`-only to an **ad-hoc plan body** (with `scenario_id` passthrough). Its
> ticket states this explicitly supersedes SAF-34615 req 13 for that one tool.

### Non-functional requirement

The checkout/validation calls used for impact numbers and conflicts are the **single source of
truth** throughout the flow; any re-check after a change reuses the same call rather than a
separate estimation path.

### Definition of Done

| # | Item | Owner |
|---|---|---|
| DoD1 | A user can, through conversation with Helm alone, build from scratch and save a fully configured, ready-to-run Validate scenario. | SAF-34615 |
| DoD2 | Simulation count and conflict information matches what the console's own Checkout and Requirements Status views would show for the same configuration. | **SAF-35508** |
| DoD3 | No scenario is created with a Propagate attack in it through this flow. | SAF-34615 |
| DoD4 | No association of data assets to a scenario is handled at this stage. | SAF-34615 (exclusion) |
| DoD5 | Changing an earlier decision automatically triggers a fresh checkout and surfaces any new conflicts. | **SAF-35508** + SAF-34615 orchestration |
| DoD6 | An attack unable to run on any selected simulator, or a simulator with zero associated attacks, is automatically removed with a plain-language explanation, without blocking the save. | **SAF-35508** reports; SAF-34615 **acts** (removal from plan body) |

### Future scope (explicitly deferred by the ticket)

- Offer a matching catalog scenario as a starting point instead of only building from scratch. *(Unassigned — candidate for a later story.)*
- Automatically propose a simulator shortlist matching the planned attacks → **SAF-35484** (Stage 2).
- Filter-based simulator selection in addition to manual → **SAF-35484** (Stage 2).
- Conflict handling beyond hard failures: partial-impact conflicts with a configurable per-step threshold (~30%+ of a step's expected simulations), swap-or-proceed choice → **SAF-35484** (Stage 2).
- On edit, place suggested attacks into an existing matching step rather than always creating a new one → **SAF-35485** (Stage 3).
- Differentiate out-of-box vs custom scenarios: never overwrite out-of-box; ask before updating vs saving as new → **SAF-35485** (Stage 3).
- `rename_scenario` / `delete_scenario` tools, blocked for out-of-box, delete requires explicit confirmation → **SAF-35485** (Stage 3).

### Ticket comments

- Boris Ifraimov (2026-08-17): FYI to Almog Ben lulu, Stas Zvolinski, Hadas Cohen.

---

## 2. Attachment — `scenario-step-grouping.md` (authoritative source for FR3)

> Attached by Tal Rotem, 2026-08-17. Jira attachment content is not retrievable via the Atlassian
> MCP or WebFetch (403); reproduced here verbatim from the ticket page so it survives as a durable
> planning input.

```markdown
# Skill: scenario-step-grouping

**Purpose:** Guide how attacks are grouped into steps when building or reviewing a SafeBreach
Validate scenario, so steps read as a coherent attack narrative instead of an arbitrary attack list.

## Rules

### 1. Name each step after its theme, not its position
Use a kill-chain/MITRE tactic ("Credential Access", "Discovery"), a target component or asset role
("Domain Controller", "Network"), or an attack vector ("Malware Transfer", "Email Attachments").
Never leave steps named "Step 1", "Step 2".

### 2. Pick one grouping axis per scenario and hold it for every step
Don't mix a tactic-based step with a component-based step in the same scenario. Choose one axis
(tactic, component, or vector) and apply it consistently.

### 3. Keep each step's attack list pure
Every attack in a step should fit that step's theme. No leftover or arbitrary IDs, and no ID
appearing in more than one step.

### 4. Order steps to match the attack narrative
Infiltration before propagation before host infection, exploitation before execution, and so on.
If the scenario has a written description, the step order should follow it.

### 5. Selection mode is a free choice, criteria are not the point
A step can select attacks by `criteria` (attack type + OS), explicit `playbook_ids`, or
`attack_tags` (threat actor, MITRE tactic). `null` target/attacker criteria is expected and fine
when the tag or ID list already does the selecting, this is not itself a flaw. It becomes a problem
only when nothing is deliberately selecting attacks, for example a step with no criteria and no
thematic ID list.

### 6. Group asset-specific or simulator-specific attacks into their own step
If a small set of attacks is only relevant to a particular data asset or simulator (not the general
scenario flow), put them in a dedicated step named after that asset or simulator, rather than
folding them into a phase or vector step where they don't really belong.

### 7. Catch-all steps: use deliberately, not as a fallback
At most one catch-all step per scenario, clearly labeled as one.

**Use one when:**
- The scenario's purpose is broad coverage (a baseline sweep, a "full coverage" style scenario)
  rather than a specific attack narrative.
- The themed phases are already covered, and you need one final step to sweep up related attack
  types that don't cleanly fit any single phase.
- The alternative is fragmenting into several near-empty steps just to preserve purity, one honest
  catch-all step is clearer than that.

**Avoid one when:**
- The scenario models a specific attack chain or threat actor, where every step should map to a
  real phase or tactic.
- It would become the only step, or hold most of the attacks, since that means the scenario has no
  real structure.
- It's being used to dodge deciding on a grouping axis. Attacks that don't fit existing steps are
  usually a sign you need a new themed step (see rule 6 for the asset-specific case), not a bucket
  for the unclear ones.

**Rule of thumb:** a catch-all is a deliberate design choice for "broad sweep after the specific
phases", not a fallback for attacks you haven't categorized.
```

### Planning note on FR3 ownership

Rules 1–4, 6 and 7 are **narrative/judgement** rules — they describe how a *model* (Helm) should
compose steps, not a deterministic algorithm an MCP tool can enforce. Rule 5 is the only rule that
touches the tool contract directly (a step's selection mode: `criteria` / `playbook_ids` /
`attack_tags`). This split needs to be resolved during brainstorming: **which of these rules become
tool-enforced invariants, which become tool-supplied facts, and which stay in Helm's prompt/skill
layer.** The parent story's FR13 explicitly says no tool returns an interpreted/narrative field,
which pushes most of this document toward the Helm layer — but `add_step`'s contract (`step_name`)
and `add_attacks_to_step`'s contract (`attack_ids[]` only) may be too thin to express rule 5's
selection modes.

---

## 3. Dependencies and Related Tickets

### SAF-35508 — MCP support for Core plan statistics API *(Subtask of SAF-34615, In Progress)*

**Implements FR6 and FR7. Covers DoD 2, 5 and 6.**
**Status on disk: fully implemented on `feature/SAF-35508-plan-statistics-mcp-tool`, not merged to `main`.**
All six PRD phases complete; e2e suite ran 8/8. ~8,055 insertions across 20 files, including
`safebreach_mcp_core/plan_statistics.py`, `safebreach_mcp_studio/studio_types.py`, and a full
`prds/…/test-plan.md` + `test-results/phase-1..6.md`.

Key decisions taken there that constrain SAF-34615:

- **Tool wire name is `get_plan_statistics`**, not `checkout_scenario`. Explicitly supersedes
  SAF-34615 req 13 for that tool.
- **Input is an ad-hoc plan body**, not a scenario id. `scenario_id` is a passthrough to Core as
  `{id}`. This is the capability that matters for Helm, which scores a configuration repeatedly
  *while building it, long before `save_scenario` exists*. → **Strong signal that SAF-34615's
  `create_scenario` may not need to persist server-side.**
  (Amended on-branch: OOB scenario UUIDs are *not* a pure passthrough — they are resolved
  client-side because Core cannot accept them.)
- **The endpoint** is `POST /orch/v1/accounts/{accountId}/plan/statistics`; console wrapper is
  `getPlanStatistics(...)` at `ui-react/src/actions/execution.tsx:615`; Core controller is
  `orchestrator/src/server/controllers/plan_statistics.js`.
- **`includeDisabled` is inverted** vs. the intuitive reading: `true` = *expected* counts
  (disabled simulators count, `simulator_is_offline` never emitted); `false` = *runnable* counts
  plus the explanation for the gap. Expected and runnable **cannot come from one call**, and
  expected cannot be derived client-side from a runnable response. Default is `false`.
- **`getAllConstraints` is a completeness flag**, not a grouping key. `true` = every validator runs
  against the full node set so a simulator accumulates *every* reason. The console uses `true`.
- **Hard-failure predicates**: attack runs nowhere ⇔ `moves[id] === 0`; simulator does nothing ⇔
  `simulators[id] === 0` (the attacker-union-target map, not a single role map). Every in-scope
  move/node is pre-seeded to `0`, so `=== 0` is sound.
- **`null` ≠ `0`.** When the circuit breaker fires (`isLimitReached`), the controller pushes a
  sentinel step and returns early: `steps` is *shorter than the plan's step count*,
  `simulationCount` is `null`, and every `moves[id]` is `null`. `null` means "not computed", not
  "runs nowhere". Never report zero-impact on `null`.
- **Severity is computed from counts alone** — `blocking` when the attack's count is integer `0`,
  `reducing` when positive. No vocabulary metadata involved. Blocker-ness is *contextual*, not a
  property of the constraint code.
- **The tool reports; it does not act.** SAF-35508 explicitly places the *removal* of zero-impact
  attacks/simulators from the plan body on "the caller that holds the configuration (Helm, or a
  future scenario-editing tool)" — **that caller is SAF-34615**. This is a direct hand-off:
  **DoD6's "is automatically removed" is SAF-34615 work.**
- **`CONSTRAINT_REASON_DESCRIPTIONS` is deleted**; MCP owns no constraint *meanings*, only a closed
  -enum `fix_lever` per emitted code (`target_filter.os`, `attacker_filter.role`,
  `*_filter.simulators`, `*_filter.connection`, `console.simulator_approval`, `console.license`,
  `console.advanced_actions`, `step.parameters`, or `null`). Meanings arrive from **SAF-35568**.
- **`registered with `readOnlyHint=True`**; the rate-limiting gate table is deliberately *not*
  extended, since that contract applies only to `readOnlyHint=False` tools. → **SAF-34615's tools
  are all mutating, so the rate-limiting gate table almost certainly does apply to them.**

### SAF-35568 — constraint meanings *(dependency of SAF-35508, transitively of this story)*

Supplies authoritative descriptions for the 88 emitted constraint codes. SAF-35508 emits
`description: null` so SAF-35568 can populate it without a shape change. Flagged in SAF-35508 as
placing SAF-35568's localization question on Stage 1's critical path.

### Related stories

| Ticket | Summary | Status | Relationship |
|---|---|---|---|
| SAF-35484 | Stage 2: filter-based simulator selection and expanded conflict detection | To Do | Consumes this story's tool surface; owns deferred FR5/FR7 scope |
| SAF-35485 | Stage 3: editing existing scenarios | To Do | Owns edit-mode step placement, OOB-vs-custom rules, rename/delete |
| SAF-35051 | Stage 4: scenario asset association | To Do | Owns data assets, proxies, impersonated users (DoD4 exclusion) |
| SAF-31511 | MCP: Propagate Run and rerun actions for the AI Agent | To Do | Sibling capability; FR11 keeps run/schedule out of this story |

---

## 4. Current State of the MCP Repo (pre-investigation reconnaissance)

Repo: `safebreach-mcp`, Python, `uv`-based. Servers: `safebreach_mcp_config`,
`safebreach_mcp_core`, `safebreach_mcp_data`, `safebreach_mcp_playbook`, `safebreach_mcp_studio`,
`safebreach_mcp_utilities`.

### Registered tools relevant to this story

| Existing tool | Server | Maps to FR13 slot |
|---|---|---|
| `get_scenarios` | config | ticket's `search_scenarios` |
| `get_scenario_details` | config | ticket's `get_scenario` |
| `get_console_simulators`, `get_simulator_details` | config | candidate backing for `list_simulators` (FR5) |
| `get_playbook_attacks`, `get_playbook_attack_details`, `get_playbook_attacks_by_tags`, `get_playbook_attack_tags` | playbook | candidate backing for FR2 attack-plan sourcing |
| `run_scenario`, `quick_run`, `manage_test` | studio | FR11 boundary — must **not** be invoked by this capability |
| `get_plan_statistics` | studio *(SAF-35508 branch only)* | FR6/FR7 |

Studio server also carries the Studio *attack* authoring tools (`validate_studio_code`,
`save_studio_attack_draft`, `get_all_studio_attacks`, `update_studio_attack_draft`,
`get_studio_attack_source`, `run_studio_attack`, `get_studio_attack_latest_result`,
`create_new_studio_attack`, `set_studio_attack_status`) — these author *attacks*, not *scenarios*.

### Key finding

**No scenario-mutation tool exists anywhere in the repo.** Every write tool in FR13
(`create_scenario`, `add_step`/`remove_step`, `add_attacks_to_step`/`remove_attacks_from_step`,
`add_simulators_to_step`/`remove_simulators_from_step`, `save_scenario`) is net-new, and
`list_simulators` is at minimum a new scenario-scoped wrapper. There is no in-repo precedent for a
multi-call mutable draft that survives across tool invocations.

---

## 5. Decisions Taken During Planning

| Decision | Choice | Rationale |
|---|---|---|
| Branch base | `origin/feature/SAF-35508-plan-statistics-mcp-tool` | `get_plan_statistics` is a hard dependency (FR6/FR7/FR12/NFR) and is unmerged. Building against `main` would mean planning against absent code. Accepted risk: rebase churn if SAF-35508 changes in review. |
| PRD scope | Remaining scope only — FR1–5, FR8–13 | FR6/FR7 and DoD 2/5/6 are delivered by SAF-35508. Restating them would duplicate ~8k lines of finished work. Traceability note kept so the DoD gate stays honest. |
| Repo | `safebreach-mcp` | Owns the Studio/config/playbook MCP surface and the `prds/` convention. |
| Worktree | `.claude/worktrees/feature+SAF-34615-…` | Matches the repo's existing convention (SAF-35508 uses the same). |
| Branch upstream | Explicitly unset | `git worktree add -b` off a remote base set upstream to the **base** branch; a bare `git push` would have written into SAF-35508. |

### Open questions carried into Investigation (Phase 4)

1. **Core write APIs for scenarios** — which orchestrator/Core endpoints the console's Studio uses
   to create/update a Validate scenario, its steps, attacks and simulator filters; whether a draft
   can exist server-side before save.
2. **Client-side draft vs server-side draft** — should `create_scenario` persist immediately and
   return a real `scenario_id`, or should the MCP hold an in-memory/opaque plan body until
   `save_scenario`? SAF-35508's ad-hoc-plan input strongly implies the latter is what the flow
   actually needs, but FR13's contract (`scenario_id` from `create_scenario`, `step_id` from
   `add_step`) reads as the former. **This is the central design fork of the story.**
3. **Console validations to mirror (FR9)** — enumerate what `ui-react` Studio enforces today (name
   uniqueness, step/attack limits, role rules, required fields) so the MCP path is not a backdoor.
4. **Validate vs Propagate separation (FR1/DoD3)** — how the two scenario kinds are distinguished
   in the data model, and which guard prevents a Propagate attack from entering this flow.

---

## 6. Investigation Findings

Five parallel Explore investigations across `orchestrator`, `configuration`, `ui-react` and the MCP
worktree. Every claim below carries `file:line` evidence; claims marked **(verified directly)** were
additionally re-checked by hand in this session rather than taken from an agent report.

### 6.1 Entry points — the Core write surface for Validate scenarios

Internally a "Validate scenario" is a **Plan** (`type: 'validate'`) owning a **Step** collection.
CRUD lives in the **`configuration`** service, *not* `orch`.

| Method | URL | Service | Purpose | Evidence |
|---|---|---|---|---|
| POST | `config/v2/accounts/{accountId}/plans` | config | Create scenario | `ui-react/src/actions/execution.tsx:550-569` → `configuration/src/server/controllers/planController.js:262` `createPlanV2` |
| PUT | `config/v2/accounts/{accountId}/plans/{id}` | config | Update scenario | `execution.tsx:571-588` → `planController.js:278` `updatePlanV2` |
| DELETE | `config/v2/accounts/{accountId}/plans/{id}` | config | Delete scenario | `execution.tsx:605-613` → `planController.js:269` |
| GET | `config/v2/accounts/{accountId}/plans` | config | List scenarios (catalog) | `execution.tsx:499-510` |
| POST/PUT/GET/DELETE | `config/v3/accounts/{accountId}/plans[/{id}]` | config | Type-aware v3-native surface (adds `type`, `propagateDefinition`). **No ui-react caller found.** | `planController.js:297-316` |
| POST | `orch/v1/accounts/{accountId}/plan/statistics` | orch | Impact/validation — **owned by SAF-35508** | `execution.tsx:615-645` |

**Two services participate in one flow**: impact from `orch`, persistence from `config`.

**(verified directly)** The save body is whitelisted through `_.pick(removeEmptySimulationUsers(data), planFields)`
(`execution.tsx:563,583`). `planFields` (`execution.tsx:528-548`) is exactly:
`id, description, integration, planId, accountId, name, capture, debug, steps, draft, createdAt,
updatedAt, deletedAt, originalScenarioId, edges, actions, tags, deploymentId, emailRecipients`.
This is the authoritative `save_scenario` request contract.

### 6.2 Data flow — the plan/step body

Schema `Plan` (v2) / `PlanV3` in `configuration/src/server/REST/swagger.json`; TS type generated from
the same swagger at `ui-react/src/types/execution.ts:34`. Persisted to Postgres tables `plans` /
`steps` via Sequelize models `configuration/src/server/models/plans.js` and `models/steps.js`
(filters stored as JSON-serialized `TEXT`). The `data` submodule owns execution *results*, not
scenario definitions.

```
Plan   { id, name (≤128), accountId, description, systemFilter, successCriteria, tags[],
         capture, steps: Step[], deploymentId, actions[], edges: PlanEdge[], draft,
         originalScenarioId, emailRecipients[], userId, createdAt/updatedAt }
PlanV3 adds: type: 'propagate'|'validate', propagateDefinition (null for validate)

Step   { id, uuid, planId, index, attacksFilter, targetFilter, attackerFilter, systemFilter,
         initialEvents, name, description, successCriteria, wait, simulationCleanupDelayMinutes }

AttacksFilter    { playbook, nistControl, systemRequirements, attackPhase, publishedDate,
                   modifiedDate, attackType, attackTypesCounter, protocol, zipPassword,
                   tags{}, parameters{}, ports, methodIds, origin }
SimulatorsFilter { os, osVersion, deployments, simulators, externalIP, internalIp, sbRelease,
                   connection, role, dataAssets, advancedActions, impersonatedUser }

Every leaf is a Filter = { operator: anyOf|noneOf|is|isNot|includes|…, values[], name }
```

### 6.3 The decisive findings

| # | Finding | Evidence |
|---|---|---|
| F1 | **No incremental step API exists.** No `/plans/{id}/steps` or `/steps/{stepId}` route anywhere in the configuration swagger `paths`. The only writes are whole-plan POST and PUT. | full-swagger grep |
| F2 | **PUT is a wholesale replace, not a merge.** `#updatePlanCore` deletes *all* existing steps for the plan (`crudControllerAsync.deleteAll('step', {filters:{planId}})`) and recreates the array from the body. No server-side diffing. Server step `id`s are therefore **not stable across saves** — they are new rows each PUT. | `planController.js:181-192`; `models/steps.js:5-16` |
| F3 | **No server-side scenario draft.** `POST /plans` is a direct DB insert returning 201, immediately visible in `GET /plans` (the catalog). There is no commit/publish step. | `planController.js:105`, `200-231`, `287-290` |
| F4 | **A Validate plan cannot be created with zero steps** → 400. So "create an empty scenario, then add steps" is impossible server-side; the first write must already carry steps. | `planController.js:72-74` |
| F5 | **`attacksFilter` is a filter DSL, not an attack-id array.** Explicit attack selection is `attacksFilter.methodIds` / `.playbook` with an `operator`+`values`. Same for simulators via `attackerFilter.simulators` / `targetFilter.simulators`. | swagger `definitions.AttacksFilter`, `definitions.Filter` |
| F6 | **Attacker vs target is not a `role` value** — it is *which filter object* the selection is assigned to (`attackerFilter` vs `targetFilter`). (`role` exists inside SimulatorsFilter but means the simulator's Critical/Infiltration/Exfiltration role, a different concept.) | swagger `definitions.SimulatorsFilter` |
| F7 | **Steps are positional, not keyed, server-side** — `index` is unique per `planId`; order in the PUT body defines identity after the delete+recreate. Any reorder/removal must resend the full ordered array. | `models/steps.js` |
| F8 | **Scenario name uniqueness is a DB constraint**, composite unique `(name, accountId)`. Not pre-validated client-side. `save_scenario` must handle a Sequelize `UniqueConstraintError` path. | `models/plans.js:101-108` |
| F9 | **`deploymentId` is server-set** from request context and update explicitly rejects changing it (`SBError('Cannot update deployment')`). | `planController.js:153-155` |
| F10 | **v2 self-guards against Propagate.** `config/v2` forces `type:'validate'` on create, strips v3 fields from responses (`#stripV3Fields`), and 404s any propagate-type plan (`#throwV2PropagateNotFound`). v3 is the forward-looking surface but has **no ui-react caller**; v2 is annotated for eventual removal. | `planController.js:243-246`, `:264`, `:297-316` |

### 6.4 How the console itself builds a scenario (the design precedent)

**Verdict: save-at-end. The console persists nothing until Save.**

- The in-progress scenario lives in **Formik form state**, not Redux (`Studio.tsx:437-491`). Redux
  holds only read-only reference data (moves, plans list, catalog, impersonatedUsers).
- "New Scenario" returns a **local plain object** `{name:'New Scenario', steps:[getDefaultStep(...)]}`
  — no HTTP (`Studio.tsx:365-381`). Clone locally renames a Redux-cached plan — no HTTP
  (`Studio.tsx:356-361`).
- The only writes are `createPlan`/`updatePlan`, fired exclusively from `onSubmit` (`Studio.tsx:499-606`).
- **Steps carry a client-generated `uuidv4()`** (`Studio.tsx:452`, `planUtils.ts:160`), and save mints
  *fresh* uuids again (`Studio.tsx:532-536`) — the pre-save uuid is throwaway canvas-wiring.
- **One serializer feeds everything**: `getStepsForApi(steps, omitValues)` (`planUtils.ts:77-107`),
  used by the auto-refreshing stats panel (`StudioStatsManager.tsx:40`), the Simulators-modal live
  requirement checks (`SimulatorsModal.tsx:70,198`), and the final save (`Studio.tsx:508,552`) —
  differing only by omit-list (`OMIT_VALUES_SAVE` / `OMIT_VALUES_RUN`, `utils/constants.ts:9-20`).
- Save vs Save-as-new is a **purely client-side branch**: `planId && !saveAs` → PUT, else POST with no
  `id` in the body (`Studio.tsx:518-565`). No distinct endpoint or wire flag.

**(verified directly) Plan-level `draft` is a red herring.** It is set from a URL query param
(`isDraft === 'true'`, `Studio.tsx:483,525,553`) and means *Studio draft custom attacks*, confirmed by
its only backend usage alongside `moveStatus.draft`/`published` (`configuration/src/server/moves/moveUpdater.js:111-116`,
`newControllers/movesController.js:323-328`). It is **not** an unsaved-scenario state. Step-level
`draft` is stripped at save (`constants.ts:19`).

**Add Simulators flow** (`Studio/modals/SimulatorsModal.tsx`, `SimulatorsModalBody.tsx`,
`StudioSimulatorsConstraints.tsx`; `TABS = {select:0, checkout:1}`):
- **Select tab** — grid of all simulators with attacker/target toggles. Filters available
  (`GridSimulatorsAdvancedFilter.tsx:42-53`): Name, OS, Deployments, External IP, Internal IP,
  Connection (`isEnabled`: Connected/Disconnected), SB Release version, Role
  (Critical/Infiltration/Exfiltration), Data Asset, Impersonated user.
- **Checkout tab** — selected simulators only, with live requirement stats.
- **Requirements Status** — `StudioSimulatorsConstraints.tsx`, per-simulator constraint failures,
  driven by `getConstraints:true` on the same `getPlanStatistics` call.
- All filters resolve into `attackerFilter`/`targetFilter` in the same shape the plan body uses
  (`getFormattedFilters`/`normalizeSimulatorFilters`, `SimulatorsModal.tsx:141-148`). Name / IPs /
  Data Asset / Impersonated user / Deployments are UI-side selection aids resolved to simulator ids
  client-side before folding into the filter.

### 6.5 MCP repo conventions for a new mutating tool

- **Registration** (`*_server.py`, inside `_register_tools`): `@self.mcp.tool(name=..., annotations=ToolAnnotations(readOnlyHint=..., destructiveHint=...), description="""…""")` wrapping a thin function that delegates to `*_functions.py` and formats markdown, with `except ValueError` / `except Exception` arms. `get_plan_statistics` is at `studio_server.py:1640-1725`. `destructiveHint` has **no code-level enforcement** — documentation only.
- **The rate-limiting "gate table" is documentation, not code.** `rate_limiter.py` holds a generic `RateLimiter` with no tool registry; the table at `CLAUDE.md:295-303` is prose. The real gate is an inline pattern in each business function: `rate_limiter.check_limit(caller_id, "<tool>")` after param validation and before the write; `rate_limiter.record_action(caller_id, "<tool>")` **only after the write succeeds** (never in a dry-run branch, never on exception — `CLAUDE.md:282-288`). Precedent at `studio_functions.py:767/834, 1026/1094, 1299/1407, 1766/1878, 3461/3467, 3716/3740, 4062/4075`.
- **HTTP**: plain `requests.post/put/delete` with `{"Content-Type":"application/json", **get_auth_headers_for_console(console)}` then `check_rbac_response(response)` (`secret_utils.py:91`, `:76`). Prefer `json=body`; the multipart calls are Studio file-upload specific. `token_context.py`'s `_user_auth_artifacts` ContextVar backs both auth and `get_caller_identity()`.
- **No pydantic / TypedDict / dataclasses for tool I/O.** `*_types.py` are flat dict-in/dict-out mapping functions; parameter validation is manual `if`/`raise ValueError`. SAF-35508 added `_plan_statistics_hint` (`studio_types.py:393`) and `get_plan_statistics_response_mapping` (`:420`).
- **Caching**: `is_caching_enabled()` is env-gated and default-off, **but is referenced only in `data_functions.py`**. Studio's `studio_draft_cache = SafeBreachCache(name="studio_drafts", maxsize=5, ttl=1800)` (`studio_functions.py:51`) is **unconditional in-process state** used at `:830, :1090, :1697, :1874`. `get_plan_statistics` caches nothing by design (`plan_statistics.py:16-17`); its `use_cache` param is a pass-through to the *orchestrator's* server-side cache (`plan_statistics.py:244`) — a different thing.
- **(verified directly) Process model**: `start_all_servers.py` runs all five servers concurrently via asyncio in a **single process**, one port each — no `workers`/gunicorn multiprocessing. In-process draft state is therefore viable *as deployed today*; horizontal scaling or multi-worker deployment would break it. **Recorded as a design assumption + risk.**
- **Tests**: root `conftest.py` seeds the auth ContextVar from env. Unit tests mock `requests.*`; `tests/test_rate_limiting.py` (`TestManageTestRateLimitingGate`, `:26-58`) is the template for asserting gate call order; e2e tests are `@pytest.mark.e2e`, zero-mock, `SKIP_E2E_TESTS`-gated, against `E2E_CONSOLE` (default `pentest01`) — see `tests/test_e2e_plan_statistics.py`.
- **Docs obligation per tool**: a `CLAUDE.md` gate-table row (`:295-303`) *and* a numbered tool-catalog entry (`:311+`, SAF-35508's at `:485-514` is the quality bar); a `CHANGELOG.md` `### Added` bullet; a `pyproject.toml:3` version bump (currently `1.11.0`; new tools = minor).

### 6.6 Integration points and open architectural questions

1. **Server ownership is unsettled and is a one-way door.** `get_scenarios`/`get_scenario_details`/`get_console_simulators` live in **config**; `get_plan_statistics`/`run_scenario`/`quick_run`/`manage_test` live in **studio**. `DESIGN.md` and `CLAUDE.md` state **no ownership rule** (grepped). Tool names are permanent once published. Options: co-locate in **studio** (follows the `checkout_scenario`→`get_plan_statistics` precedent and shares plan-shaping helpers), put writes in **config** (splits read/write for one resource), or a new builder server (no precedent, 6th port).
2. **v2 vs v3 plans surface.** v2 is simpler and self-guards Propagate (F10) but is flagged for removal; v3 is type-aware and forward-looking but has no existing caller.
3. **Where the draft lives.** `studio_draft_cache`'s shape (`maxsize=5`, `ttl=1800`) is the nearest precedent, but a 30-minute TTL and 5-entry bound would silently drop a user's in-progress build mid-conversation.

### 6.7 Contradictions between FR13 as written and the system as built

These are the substance of the Phase 5 brainstorm. **None is a reason to change the ticket's intent —
each is a place where the literal contract cannot be implemented as specified.**

| FR13 as written | Reality | Consequence |
|---|---|---|
| `create_scenario` → returns `scenario_id` | No server draft (F3); a plan with no steps is rejected (F4); POST publishes immediately to the catalog (F3) | A real `scenario_id` cannot exist before steps are added, and creating one early would leak a half-built scenario into the user's catalog |
| `add_step` → returns `step_id` | No step endpoint (F1); PUT deletes+recreates all steps (F2); server ids unstable (F2, F7) | `step_id` must be a client-side handle (mirroring Studio's throwaway `uuid`), not a server id |
| `add_attacks_to_step(step_id, attack_ids[])` | `attacksFilter` is an operator/values filter DSL (F5) | The tool must *merge Filter objects*, not append to a list. Grouping rule 5 names exactly the three selection modes the DSL supports (`criteria`, `playbook_ids`, `attack_tags`) |
| `add_simulators_to_step(..., role)` | Attacker/target = which filter object (F6); `role` inside the filter means something else | `role` maps to filter selection; the parameter name collides with an existing domain term |
| `checkout_scenario(scenario_id)` | Superseded by SAF-35508's `get_plan_statistics` with an ad-hoc plan body | Already resolved by the subtask |

---

## 7. Brainstorm Outcome

_Pending — Phase 5._
