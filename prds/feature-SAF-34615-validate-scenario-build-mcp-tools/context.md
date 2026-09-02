# SAF-34615 — MCP support for Validate scenario creation and update (Stage 1)

**Status**: `Phase 5: Brainstorm`

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

### 6.8 Canonical step shape and filter primitive (verified directly this session)

Path correction: the serializer/defaults live in **`ui-react/src/containers/matrices/planUtils.ts`**
(agent reports cited `containers/Studio/utils/planUtils.ts`; line numbers hold).

**The filter primitive** — `getFilterObj` (`ui-react/src/containers/Studio/utils/helpers.tsx`):

```js
getFilterObj(name, values) => ({ [name]: { operator: 'is', values, name: name.toLowerCase() } })
Filter.ATTACKS    = 'playbook'     // -> attacksFilter.playbook
Filter.SIMULATORS = 'simulators'   // -> attackerFilter.simulators / targetFilter.simulators
```

So an explicit attack selection is `attacksFilter.playbook = {operator:'is', values:[...], name:'playbook'}`,
and an explicit simulator selection is `attackerFilter.simulators` / `targetFilter.simulators` of the same
shape. This is the object `add_attacks_to_step` / `add_simulators_to_step` must build and merge.

**`getDefaultStep(index, addStats, moveIds, simulatorId, impersonatedUserIds)`** (`planUtils.ts:150-180`)
produces:

```
{ id: index, uuid: uuidv4(), name: `Step ${index || 1}`,
  attacksFilter:  getFilterObj('playbook',   moveIds),
  attackerFilter: getFilterObj('simulators', simulatorId),
  targetFilter:   getFilterObj('simulators', simulatorId),
  systemFilter: { ...bypassProxy=[true], ...runAsRoot=[true], ...simulationUsers=[impersonatedUserIds] },
  meta: {...} }
```

**`getStepsForApi`** (`planUtils.ts:77-107`) always emits `attacksFilter: {}`, `attackerFilter: {}`,
`targetFilter: {}` as a base before merging the cleaned filters — empty filters are `{}`, never omitted.
It also drops `successCriteria` unless both `path` and `operator` are set, and applies the caller's
omit-list (`OMIT_VALUES_SAVE` / `OMIT_VALUES_RUN`).

#### Two consequences for this story

| # | Finding | Consequence |
|---|---|---|
| F11 | **The console's own default step violates grouping rule 1.** `getDefaultStep` names steps `Step ${index \|\| 1}` — exactly the `"Step 1"/"Step 2"` anti-pattern `scenario-step-grouping.md` rule 1 forbids. | `add_step` must **require** a themed `step_name` rather than defaulting like the console. A deliberate, documented divergence from console behaviour — not a console bug to fix here. |
| F12 | **FR9 parity risk hides in step defaults, not in validations.** `getDefaultStep` seeds `systemFilter` with `bypassProxy=[true]`, `runAsRoot=[true]` and `simulationUsers`. | An MCP-created step omitting these would *run differently* from an identically-described console step — a silent behavioural divergence, not a validation error. FR9 must be read as covering **defaults parity**, not only validation parity. |

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

### 6.9 FR2 attack-sourcing surface — coverage and gaps

FR2 names five search axes. The existing MCP read surface covers three; two are only partially reachable.

| Axis | Verdict | How | Gap |
|---|---|---|---|
| Scenarios catalog | **SUPPORTED** | `get_scenarios(name_filter, category_filter, tag_filter, creator_filter, recommended_filter)` + `get_scenario_details` | `category_filter` is a substring match on resolved names, so the caller must already know rough category names |
| Attack IDs | **SUPPORTED** | `get_playbook_attack_details(attack_id)`; `get_playbook_attacks(id_min/id_max)` | — |
| Attack playbook (free text) | **SUPPORTED** | `get_playbook_attacks(name_filter, description_filter)`, case-insensitive partial match | — |
| **Named threat groups** | **PARTIAL** | `Threat Actor` is a real tag group (`content-manager/src/scenarios/entities/scenario.entity.ts:16`, `TAG_THREAT_ACTOR`). Visible per-attack via `get_playbook_attack_details(include_tags=True)`. Scenario category id=3 "Threat Groups" exists (`content-manager/src/database/one-time-seeds/categories.ts:30-37`) | **No bulk attack-level search by threat actor.** `get_playbook_attacks_by_tags` searches only the custom `'Tags'` group and explicitly excludes classification groups (`playbook_types.py:129-131`) |
| **CVEs** | **PARTIAL** | `CVE` / `CVE Link` are real tag groups (`content-manager/src/moves/move-transform-backward.ts:89-90`), visible per-attack via `include_tags` | **No bulk search by CVE at all.** Finding "attacks matching CVE-2024-XXXX" means fetching every attack and scanning — not a search |

**"Relatively new attacks" is already covered.** `get_playbook_attacks` exposes `published_date_start/end` and
`modified_date_start/end` (`playbook_types.py:478-497`); orchestrator field names match
(`orchestrator/src/server/other/playbook_filter.js:13,28,56-57`). The orchestrator's separate
`latestKnownAttacks` concept is a *step-scoped* plan-render filter (call site
`orchestrator/src/server/services/PlanPreparation.js:419`), not a playbook-search filter — different mechanism;
confirm with product which one FR2 means.

### 6.10 Attack classification metadata — what FR3's grouping can actually see

The grouping rules want a tactic / component / vector axis. Most of the facts that would support that are **not
exposed by any MCP tool today**, though they exist server-side.

| Field | Meaning | Exposed by MCP? | Source |
|---|---|---|---|
| MITRE tactic / technique | ATT&CK mapping | **YES** — `mitre_technique_filter`, `mitre_tactic_filter`, `include_mitre_techniques`. ~42.6% coverage | `playbook_types.py:152-219` |
| Platform (attacker/target OS) | from `content.nodes.*.constraints.os` | **YES** — `attacker_platform_filter` / `target_platform_filter`, always-on fields. ~32.3% coverage | `playbook_types.py:222+` |
| Published / modified date | recency | **YES** | see §6.9 |
| Custom tags | the `'Tags'` group | **YES** — the only group with bulk search | `playbook_types.py:120-149` |
| **Attack phase** | `Package` enum: `EXFILTRATION=0, LATERAL=1, INFILTRATION=2, HOST_LEVEL=5` | **NO** | `orchestrator/src/server/other/constants.js:1-9`; filter key `attackPhase` at `playbook_filter.js:11,55` |
| **Attack type** | tag group `'Attack Type'` | **NO** — raw `include_tags` only | `scenario.entity.ts:18`; `playbook_filter.js:56` |
| **NIST control** | tag group `nist_Control` | **NO** — raw `include_tags` only | `playbook_filter.js:45,58` |
| **Protocol** | tag group `protocol` | **NO** — raw `include_tags` only | `playbook_filter.js:40,58-59` |
| **Threat Actor / CVE** | classification tag groups | **PARTIAL** — per-attack only | see §6.9 |
| `origin` | orchestrator `attacksFilter` vocabulary key; `valuesExtractorByFilter.origin = move => move.origin` | **NO**, and **what populates it is unconfirmed** — no matching field found in content-manager's move entity | `playbook_filter.js:10,54` — needs owner input |

**Consequence:** attack phase, attack type, NIST control and protocol are precisely the axes
`scenario-step-grouping.md` rules 1-2 lean on, and none is available. `add_attacks_to_step` cannot today be
handed the facts the grouping rules assume.

### 6.11 The Propagate guard already exists — but at run time, not save time (verified directly)

`orchestrator/src/server/services/PlanPreparation.js:405-409`:

```js
if (!step.isPropagate) {
  const filter = { tags: { ALM: { operator: 'noneOf', values: ['1'], name: 'ALM' } } };
  moves = this.playbookFilter.filterPlaybook(filter, moves);   // strips every ALM=1 move
}
```

Propagate attacks are marked by the **`ALM`** tag group (Advanced Lateral Movement), and the orchestrator strips
every `ALM=1` move when preparing any non-propagate step. `step.isPropagate` is the step-level gate.

**F13 — DoD3 is not satisfied by this on a literal reading.** The strip happens at *plan preparation* (run time).
A Propagate attack id can still be **persisted** into a Validate plan's `attacksFilter`; it simply never executes.
DoD3 says "No scenario is **created** with a Propagate attack in it". Combined with F10 (v2 forces
`type:'validate'` at the *plan* level, but says nothing about the attacks inside), there is currently **no
save-time attack-level guard**. Decision for brainstorm: rely on the runtime strip, or add a save-time filter.

**F14 — the MCP layer has no ALM filter to lean on.** No `get_playbook_attacks` parameter exposes ALM/Propagate;
it is visible only as `"ALM:1"` in a raw `include_tags` response for a single attack. A save-time guard would
need a new filter param, or a fetch-all-and-scan, or reliance on Validate-scoped catalog content.

### 6.12 FR10 — the requirement's premise is unconfirmed

"AI-generated Attack Scenarios" has **zero trace** in `content-manager`, `orchestrator`, `configuration`,
`ui-react`, or the MCP repo. The static category seed (`categories.ts:13-94`) lists ten categories —
Security Controls, Known Attacks Series, Threat Groups, Baseline Scenarios, MITRE ATT&CK, Industry, Environment,
Regulatory Compliance, Geography, Dynamic/Results Driven — and none matches. Categories are served dynamically
via `scenarioCategoriesService`, so a new one could exist as live DB data with no code change.

**Model mismatch:** categories belong to **scenarios**, not to individual attacks/moves (moves carry tags, not
categories). So "attacks from the AI-generated Attack Scenarios *category*" does not type-check against the data
model. It may mean (a) attacks appearing as steps within scenarios in that category, or (b) a new *tag* on moves.
**Open question for Tal Rotem — do not guess.**

**Good news:** nothing in `get_scenarios`, `get_scenario_details`, `get_playbook_attacks` or any filter function
special-cases a category or tag name; filtering is generic substring/exact match. FR10's "no special-casing"
requirement is therefore **already satisfied structurally**.

**Correction to the §4 reconnaissance:** `scenario_categories` is **not** a registered tool — that string came
from a `SafeBreachCache(name=...)` instantiation. There is no way to enumerate categories today, which matters if
Helm must discover the exact category name before calling `category_filter`.

### 6.13 FR9 — the console-validation inventory, and what is browser-only

**Headline: the Save button is barely gated at all.** `StudioHeader.tsx:381` —
`disabled={isAlmScenario || isDraft === 'true'}`. No name, step, attack or simulator validity check gates Save.
And **no `validate`/`validationSchema` prop is ever passed to Formik** (`Studio.tsx:732-741`) — there is no
form-level schema for the scenario. Every "validation" is ad-hoc UI logic, and most of it gates **Run/Schedule**,
not Save.

| Validation | Enforcement | file:line |
|---|---|---|
| Scenario name required (non-empty) | **Both** | client `StudioRightPanel.tsx:264` (`disallowEmpty`); server `models/plans.js:17-23` |
| Scenario name ≤128 chars | **Both** | client `StudioRightPanel.tsx:266`; server `plans.js:18` + swagger `Plan.name` |
| Scenario name uniqueness per account | **Server only — no client check** | `plans.js:101-108`; `SaveAsPopUp.tsx` is a plain `FormikInput` with no check |
| **Step name required** | **CLIENT ONLY — backdoor** | client `StudioRightPanel.tsx:264`; server `models/steps.js:32` is unbounded TEXT, no `allowNull:false`, no validator |
| **Step name ≤128 chars** | **CLIENT ONLY — backdoor** | client `StudioRightPanel.tsx:266`; server none |
| **Step name unique within scenario** | **CLIENT ONLY — backdoor** | client `StudioRightPanel.tsx:220-230,265` (`forbiddenValues`); server's only step index is `(index, planId)` — ordering, not name (`steps.js:52-58`) |
| Plan must have ≥1 step | **Server, on CREATE only — asymmetric** | `planController.js:72-74`; `#updatePlanCore` (124+) has **no** equivalent, so an update could blank out steps |
| "Scenario must have ≥1 step" | **Client only**, and it is a *delete-time* guard, not save-time | `Studio.tsx:651-653` |
| Plan `type` required, enum-checked | **Both** | `utils/model-validators.js:46-51`; swagger `PlanV3.required` |
| `propagateDefinition` shape | **Server only** | `utils/propagatePlanValidators.js`, `model-validators.js:26-43` |
| Deployment-filter guard on create | **Server only** | `planController.js:83-90` |
| Cannot change `deploymentId` / `accountId` | **Server only** | `planController.js:153-155`; `plans.js:87` |
| Cross-account read/update/delete blocked | **Server only** | `planController.js:51-62,157-168` |
| Run gating: all steps green, attacker+target present, valid branching, impersonated-users-vs-runAsRoot conflict | **CLIENT ONLY, and gates Run/Schedule — NOT Save** | `StudioHeader.tsx:190-276` |

**Searched for and confirmed absent** (neither client nor server): max steps per scenario; max attacks per step or
scenario; max simulators per step; a rule preventing the same simulator being both attacker and target; a rule
requiring an attacker *and* target to **save** (only to *run*); duplicate-attack-across-steps blocking;
deprecated/disabled-attack blocking at save time (the picker filters `move.status==='published'` at *fetch* time
only); any step-name sanitization — a Jest test (`StudioCloneAndCreate.test.tsx:202-228`) confirms
`<img src=x onerror=...>` is stored verbatim as a step name.

**F15 — FR9's real surface is larger than "mirror the validations".** An MCP tool writing directly to the plan API
can today create a scenario with empty, duplicate or 512-character step names, broken branching, and steps with no
attacker or target — none rejected server-side. Mirroring the console therefore means **implementing** these
checks in the MCP layer, not calling something that already enforces them.

### 6.14 FR1/DoD3 — there are TWO independent Propagate signals (verified directly)

**This supersedes the earlier reading of F10 that v2 gives FR1/DoD3 "almost for free". It does not.**

```js
// orchestrator/src/server/other/TestSchemaValidator.js:37-39
static isPropagateTest(test) {
  return test?.type === 'propagate' || test?.systemTags?.includes('ALM') === true;
}
```

Two signals, OR'd, neither cross-validated against the other:

1. **`plans.type`** — enum `'propagate'|'validate'`, default `'validate'` (`models/plans.js:71-78`), with companion
   `propagateDefinition` JSONB (`plans.js:79-82`). Shape consistency **is** enforced server-side on every
   create/update by `validatePlanShape` (`model-validators.js:45-59`).
2. **A legacy plan-level `tags` entry `'ALM'`** — and *this* is what the console's actual Propagate UI produces.
   Studio derives `isAlmScenario` from `_.get(scenario,'tags').includes(ALM_TAG)` (`Studio.tsx:434`), **not** from
   `plan.type`, and **Studio never writes `propagateDefinition` at all**. This path has **no server-side guard
   whatsoever**: `planController.js` never inspects `tags` for `'ALM'`.

**The `tags` → `systemTags` link is verified**, so the legacy path really does reach `isPropagateTest`:
`PlanPreparation.js:69` — `result.data.systemTags = result.data.tags; // This is needed until SAF-11730 is done`,
and `RunTestModal.tsx:284` sends `systemTags: plans[planId].tags`.

**F16 — v2 does NOT close the Propagate hole.** v2 forces `type:'validate'` and 404s propagate-*typed* plans, but
it does not strip `tags`. A `POST config/v2/plans` carrying `type:'validate'` + `tags:['ALM']` is accepted and is
then treated as a Propagate test at fire time. **The MCP layer needs its own explicit guard rejecting
`type==='propagate'` AND any `tags`/`systemTags` containing `'ALM'`, on both create and update.**

**F17 — "regardless of license" is currently untrue at save time.** The Propagate license check
(`'The Propagate package is missing'`, `NOT_ALLOWED` 400) lives in `TestSchemaValidator.validateAPITestSchema`
(`TestSchemaValidator.js:68-97`) and runs only when a test is **submitted to run** — never at plan create/save, and
in `orchestrator`, not `configuration`. The console's client-side strip
(`Studio.tsx:512`: `_.omit({...savedPlan}, hasAlmFlag ? [] : ['tags'])`, keyed on
`FEATURE_ALM = 'feature.penetrationCommandAndControl'`) is UI convenience, **not** a security boundary — nothing
server-side re-checks entitlement before persisting `tags`. FR1's "regardless of whether the account holds a
Propagate license" therefore requires a guard the platform does not have today.

**F18 — attack-level vs plan-level ALM are different things; do not conflate them.**
- **Attack/move level**: moves carry an `ALM` *tag group*; `PlanPreparation.js:405-409` strips every `ALM=1` move
  for any step where `!step.isPropagate`. There is **no** propagate/validate *column* on the moves model
  (`configuration/src/server/models/moves.js`) — the marker is a tag. Content-package licensing is a separate
  axis: `ContentPackage.PropagatePackages:[8]` vs `ValidatePackages:[1..7]`
  (`orchestrator/src/server/other/constants.js:118-128`).
- **Plan level**: `plan.tags` containing `'ALM'` marks the whole *test* as Propagate at fire time (F16).

DoD3 ("no scenario is **created** with a Propagate attack in it") concerns the attack level, and the only guard
there is the **run-time** strip — nothing prevents persisting an ALM-tagged attack id into a saved Validate plan.
Studio's own attack picker does not filter by Propagate/Validate content package at all
(`AttacksModal.tsx`/`AttacksModalBody.tsx` do not receive `isAlmScenario`).

### 6.15 DoD3 resolved — get_plan_statistics already strips ALM attacks for a Validate plan (verified directly)

User direction: DoD3 is satisfied by (a) schema-conformance validation before `create_scenario`/`save_scenario`,
and (b) running the statistics checkout to verify the user's requested attacks can actually run — not by a
bespoke ALM/Propagate guard. Investigated whether the mechanism actually backs that, since `get_plan_statistics`
was believed to score the plan independently of the ALM strip found in §6.11.

**It does not score independently — it reuses the exact same pipeline.**
`orchestrator/src/server/controllers/plan_statistics.js` takes `planPreparation` as an injected dependency and
calls, per step: `getPlanMoves` → **`this.planPreparation.filterMoves(planMoves, step, useCache)`**
(`plan_statistics.js:85-86`). `filterMoves` is the exact method (`PlanPreparation.js:390`) containing the ALM strip
verified in §6.11 (`PlanPreparation.js:405-409`): `if (!step.isPropagate) { moves = filterPlaybook({tags:{ALM:
{operator:'noneOf', values:['1']}}}, moves) }`.

**`step.isPropagate` is never assigned anywhere in the orchestrator's Plan/Step code path** (grepped
`services/PlanPreparation.js` and `other/*.js` for an assignment — none found; it is only *read* at line 405).
It is a `Phase`-schema concept (Propagate's separate `propagateDefinition.phases[]` shape,
`TestSchemaValidator.js`'s `validatePropagatePhase`), not a `Plan.Step` field. Since our new tools only ever
construct ordinary `Plan.steps[]` (never `propagateDefinition`), `step.isPropagate` is always falsy for every plan
this story can produce — so the ALM strip in `filterMoves` **always** runs.

**F19 — consequence for DoD3.** Any ALM-tagged attack a user asks Helm to add to a Validate plan is invisible to
`filterMoves`, so it scores `moves[attack_id] === 0` in `get_plan_statistics` — indistinguishable from any other
attack that cannot run on the current selection. SAF-35508's existing zero-impact reporting already flags it as a
hard failure; **this story's own DoD6 obligation (remove + explain) is the same code path that closes DoD3** — no
separate Propagate-detection guard is needed. The design requirement this creates: `create_scenario`/
`save_scenario` must **require** a fresh, zero-blocking-conflict checkout immediately before persisting (not just
offer one), so an ALM attack is always caught and stripped, not merely detectable if Helm happens to ask.

**Still true and unresolved by this** (from §6.14, not superseded): a **whole-plan** `type==='propagate'` or a
plan-level `tags:['ALM']` marker is a different, plan-level concern (F16/F17) — orthogonal to attack-level
filtering. v2's forced `type:'validate'` (F10 original) already prevents the `type` half. The plan-level `tags`
field is one of the 19 `planFields` (§6.1) our `save_scenario` body legitimately carries (e.g. for scenario
tagging) — **the tool must never let a caller set `'ALM'` into that field**, since nothing server-side blocks it
(F16). This is a narrow, cheap guard (reject/strip `'ALM'` from any caller-supplied `tags` on save) — not the
broad "detect Propagate attacks" problem, which §F19 already resolves structurally.

### 6.16 Attack search filtering — investigated whether ALM/tag-group filtering is feasible (verified directly)

Checked whether the attack-listing surface (existing MCP tool, underlying content-manager API, or the console's
own picker) can filter by ALM/Propagate, as a possible defense-in-depth alongside §6.15.

- **The underlying API is fetch-all, not filterable.** `content-manager`'s `GET /moves` (`moves.controller.ts:28-49`,
  `findAll`) takes **no query filter parameters at all** — it returns every move (ETag/304-cached). All of
  `get_playbook_attacks`'s existing filters (name, description, dates, MITRE, platform) are applied **client-side
  in Python** after one full fetch. Actually the playbook server's own live fetch is a *different* endpoint —
  `GET {base_url}/api/kb/vLatest/moves?details=true` (`playbook_functions.py:72`) — same shape: fetch-everything,
  filter-in-Python (`sb_get_playbook_attacks` → `_get_all_attacks_from_cache_or_api` → `filter_attacks_by_criteria`,
  `playbook_functions.py:157-183`).
- **Raw tag data (including ALM) is already present in every fetched attack** — `attack_data.get('tags')` in the
  nested `[{id,name,values:[...]}]` shape `_transform_tags` already knows how to parse (`playbook_types.py:66-99`).
  It is simply not carried through: `transform_reduced_playbook_attack` (`playbook_types.py:319-359`, used by
  `sb_get_playbook_attacks`) only extracts tags when `include_tags=True` is passed, and `sb_get_playbook_attacks`
  never passes it (`playbook_functions.py:165`, `include_mitre_techniques=needs_mitre` only).
- **F20 — adding an ALM-exclusion (or general tag-group) filter to `get_playbook_attacks` is a pure Python
  change, no new upstream API call needed** — same shape as the existing MITRE/platform filters, applied against
  data already in memory from the one cached fetch.
- **The console does not do this today.** Confirmed earlier (§6.14): `AttacksModal.tsx`/`AttacksModalBody.tsx`
  never receive `isAlmScenario` and apply no Propagate/Validate content-package filtering in the picker — the
  console relies exclusively on the run-time strip, the same mechanism §6.15 shows `get_plan_statistics` already
  reuses.

**Decision (per user direction + this finding):** rely on §6.15's checkout-based removal as the DoD3 mechanism —
it is load-bearing, verified, and requires no new filter. An ALM-exclusion filter on the attack-search tool is a
**cheap, optional UX improvement** (skip proposing an attack Helm already knows will be stripped, rather than
surfacing it and then explaining its removal one step later) — not required for DoD3 correctness. Defer the
decision on whether to build it to the brainstorm/PRD-scoping step.

### 6.17 FR10 — resolved by user direction: out of scope

**User direction: ignore FR10. Any published attack is valid to use, with no special-casing by category.**
This matches §6.12's finding that the "AI-generated Attack Scenarios" category has zero trace in any repo, and
that no current MCP/console code special-cases any category or tag. No new work is needed for FR10 — the
existing generic, non-special-casing search behavior already satisfies the user's stated intent. Remove FR10 from
the PRD's scope of work; keep §6.12 as a record of why (in case product raises it again later).

## 7. Brainstorm Outcome

Four forks were presented with alternatives and tradeoffs (per the brainstorming skill); user decided each.

### Decision 1 — Draft state: in-process draft cache

`create_scenario` mints a `draft_id` (uuid) and stores the accumulating plan body in a new bounded
in-process `SafeBreachCache` in `safebreach_mcp_studio` (mirroring `studio_draft_cache`'s pattern —
`studio_functions.py:51` — but as its own instance, e.g. `scenario_draft_cache`, sized and TTL'd for a
multi-turn conversational build rather than a single attack-draft edit). Every subsequent tool
(`add_step`, `add_attacks_to_step`, `add_simulators_to_step`, and their `remove_*` counterparts) takes
`draft_id` and mutates the cached body; `save_scenario` reads it, assembles the final wire body (see
Decision 4), POSTs/PUTs it, and evicts the cache entry on success.

**Accepted, documented risk**: this state does not survive an MCP process restart, and would break under
a future multi-worker/horizontally-scaled deployment (§6.5 confirmed `start_all_servers.py` runs
single-process today — this is a live assumption, not a permanent guarantee). `save_scenario` failing with
"draft not found" after a restart is an acceptable, clearly-erroring failure mode for Stage 1, to be
called out explicitly in the PRD's risks section rather than engineered around.

**Rejected alternatives**: (a) stateless design where Helm carries the full plan body across every tool
call, matching `get_plan_statistics`'s own ad-hoc-body pattern — rejected in favor of the closer FR13/console
match, accepting the tokens-per-call and JSON-fidelity cost that comes with a stateful draft_id instead;
(b) persisting immediately on `create_scenario` (a real `scenario_id` from turn one) — rejected because it
contradicts the console's own verified behavior (§6.4) and would publish an unfinished scenario into the
user's real catalog before they agree to save it.

### Decision 2 — Attack/simulator input: ID lists + raw Filter-DSL escape hatch

`add_attacks_to_step` accepts `attack_ids[]` (builds `attacksFilter` internally, `operator:'is'`) **and**
an optional raw `attacks_filter` parameter accepting the `AttacksFilter` DSL directly (§6.2 schema:
`playbook`, `methodIds`, `tags`, `attackPhase`, `nistControl`, `protocol`, …). Symmetric design for
`add_simulators_to_step`: `simulator_ids[]` plus an optional raw `attacker_filter`/`target_filter`.

This diverges from the ticket-literal, ID-only recommendation: it deliberately keeps the door open for
`scenario-step-grouping.md` rule 5's criteria/playbook_ids/attack_tags selection modes (nominally Stage
2/3 scope per SAF-35484/SAF-35485) without a breaking parameter change if Stage 1 or a fast-follow needs
them sooner.

**Design detail (proposed default, not yet re-confirmed with user — flag in PRD review):** `attack_ids`
and `attacks_filter` are **mutually exclusive per call** — passing both is a validation error, not a merge.
Simplest semantics; avoids ambiguous "does the filter narrow the id list or extend it" questions. Same rule
for `simulator_ids` vs `attacker_filter`/`target_filter`.

**Open question carried to §6.1's F5 ambiguity**: the console's own `getFilterObj` builds explicit attack
selection under `attacksFilter.playbook` (`ATTACKS: 'playbook'`, `planUtils.ts` / `Studio/utils/constants.ts`),
while the broader `AttacksFilter` schema (§6.2) also lists a distinct `methodIds` field. Which key
`attack_ids[]` should populate — `playbook` (console parity) or `methodIds` (schema-literal) — needs one
more grounding check (cross-reference SAF-35508's own `methodIds` handling in `get_plan_statistics`, since
it already had to resolve this) before the PRD locks the internal mapping.

### Decision 3 — Server home: Studio

New tools live in `safebreach_mcp_studio` (`studio_server.py`/`studio_functions.py`/`studio_types.py`),
alongside `get_plan_statistics`, `run_scenario`, `quick_run`, `manage_test`. Rationale: SAF-35508 already
resolved `checkout_scenario`'s FR13 slot into Studio, and the build→check→run arc — plus the plan-shaping
helpers a `save_scenario` body-assembler will want — stays in one server and one auth/rate-limit context.

**Rejected**: Config (architecturally closer to the backend service that owns Plan/Step CRUD, and where
`get_scenarios`/`get_scenario_details`/`get_console_simulators` already live, but would split the
build-check-run loop across two servers and be Config's first-ever mutating tool); a new dedicated server
(cleanest separation, but real infra overhead — port, launcher entry, Desktop config, test scaffolding —
for a handful of tools, with no precedent for a split this granular in this repo's history).

### Decision 4 — Plans API: v3

New tools write through **`config/v3/plans`** (`configuration/src/server/controllers/planController.js`'s
type-aware native methods — `createPlan`/`updatePlan`/`getPlanById`/`getAllPlans`/`deletePlan`, §6.1), not
the v2 wire-compat surface the console itself calls.

**Consequence — v3 does NOT self-guard `type='validate'` the way v2 does (v2's `createPlanV2` force-sets it;
`planController.js:264`).** `save_scenario` must set `type:'validate'` and `propagateDefinition:null`
explicitly on **every** create and update request — `validatePlanShape` (`model-validators.js:45-59`)
requires the pairing (a `'validate'`-typed plan requires a **null** `propagateDefinition`; a non-null value
is a shape violation, 400). This is now a required, explicit part of `save_scenario`'s implementation, not
optional — carried forward from §6.14/F16.

**F16's plan-level `tags:['ALM']` risk is closed by simple omission, not a guard.** Checked the `ValidatePlan`
schema (`orchestrator/src/server/other/swagger.json`, `components.schemas.ValidatePlan.properties` —
verified directly: `id, accountId, planId, testId, tags, systemTags, name, planRunId, capture, debug, draft,
force, priority, successCriteria, steps, flowControl, retrySimulations, retryPolicy, originalScenarioId,
actions, edges, systemFilter, emailRecipients`, `required:['name']`) — it carries `tags`/`systemTags` but
**no `type` field at all**, confirming the ad-hoc-checkout body (what `get_plan_statistics` scores mid-build)
and the final v3 save body are genuinely different shapes; `type`/`propagateDefinition` belong only on the
latter. **None of FR13's tools (`create_scenario`, `add_step`, `add_attacks_to_step`,
`add_simulators_to_step`, `save_scenario`) expose a `tags` input parameter at all** — so the simplest and
most robust closure is to never accept caller-supplied `tags` in Stage 1, rather than build a reject-`'ALM'`
filter for an input surface that doesn't need to exist. The internal draft body (Decision 1) therefore never
carries `tags` for the lifetime of any scenario this story can produce.

**Consequence for the draft↔checkout↔save pipeline**: the draft cache's internal representation should track
close to the `ValidatePlan`/`Step` shape (`name`, `steps[]` with `attacksFilter`/`attackerFilter`/
`targetFilter`/`systemFilter`) for the whole build phase — this is exactly what gets posted to
`get_plan_statistics` for every interim checkout, unmodified. Only `save_scenario` wraps/augments that body
with `type:'validate'` + `propagateDefinition:null` immediately before the `config/v3/plans` POST/PUT — the
v3-specific fields are added at the last possible step, not carried through the whole build.

**Consequence for testing**: v3 has **zero existing production callers anywhere in the codebase** (§6.1) —
this story's tools would be its first real use. This raises the bar on `save_scenario`'s test coverage
(unit + e2e) beyond the repo's usual bar for a new tool; flag for extra scrutiny at the Phase 8 test-plan
step and the Phase 7 DoD gate.

**Rejected**: v2 — safer (self-guarding, console-parity, easiest FR9-diff target) but flagged
`// DELETE WHEN v2 IS REMOVED` in its own code; user chose to build against the forward surface rather than
the surface scheduled for eventual removal.

### Decision 2, refined — attacks_filter gains first-class type/phase/tags support

**User direction: the `attacks_filter` escape hatch must explicitly support filtering by attack type,
attack phase, and tags** — not stay a raw opaque JSON passthrough. Grounded against §6.2/§6.10's schema
findings:

| Parameter | Maps to | Values |
|---|---|---|
| `attack_type_filter` | `attacksFilter.attackType` (dedicated schema field) | tag-group `'Attack Type'` values (§6.10) |
| `attack_phase_filter` | `attacksFilter.attackPhase` (dedicated schema field) | orchestrator `Package` enum — `infiltration\|lateral\|exfiltration\|host_level` (string in, mapped to `INFILTRATION=2\|LATERAL=1\|EXFILTRATION=0\|HOST_LEVEL=5` — `orchestrator/src/server/other/constants.js:1-9`) |
| `tags_filter` | `attacksFilter.tags[group]` (generic, group-keyed dict) | any tag group by name → values, e.g. `{"Threat Actor": ["APT29"], "CVE": ["CVE-2024-1234"]}` — covers Threat Actor/CVE/custom `Tags` and any future group without a new parameter |

**Recommendation (not yet re-confirmed): use the dedicated `attackType`/`attackPhase` fields for the two
named, common axes, and keep `tags_filter` as the generic escape hatch for everything else** — clearer,
self-documenting parameters beat routing every axis through one opaque dict.

**Open question surfaced, not decided — carry to PRD**: should `get_playbook_attacks` (the read/search
tool, FR2) gain matching `attack_type_filter`/`attack_phase_filter`/`tags_filter` parameters too? Right now
Helm would have no way to discover which attacks match a given type/phase/tag *before* committing that
filter live into a saved step's `attacksFilter` — it would be selecting blind. This also happens to be the
natural fix for §6.9's CVE/threat-actor bulk-search gap (F-none-assigned — no bulk search exists today),
since `tags_filter`'s group-keyed shape is exactly what that gap needs. Flagging for explicit user decision
rather than assuming scope creep into FR2.

### Decision 5 — Skills: open scope question, not decided

**User asked whether Helm-side skills should be authored in addition to the MCP tools.** Investigated
whether this repo or workspace has any trace of where Helm's own orchestration/skill layer lives — the
layer that would encode `scenario-step-grouping.md`'s grouping rules, FR2's search strategy, FR7's
conflict-translation cadence, and FR8's one-or-two-at-a-time confirmation flow. **Found nothing**: no
Helm/agent-orchestration repo among the user's local checkouts, and zero "skill" references anywhere in
`ui-react/src/containers/AIChat/` (Helm's own console-side chat UI).

FR13 is explicit that the MCP tools must stay "dumb" — "No tool accepts a free-text goal or returns an
interpreted/narrative field; Helm is responsible for all sequencing and interpretation on top of these
tools." That interpretation layer has to live *somewhere*, and the attached `scenario-step-grouping.md` is
itself literally formatted as a Claude Skill document (`# Skill: scenario-step-grouping`) — strong evidence
that a companion skill is expected to exist, but authored and shipped from a system this repo/PRD has no
visibility into.

**Not decided — needs a direct answer, not an inference**: is authoring that skill in scope for SAF-34615 at
all? If yes, where does it live (a different repo, a different deployment mechanism for Helm) and in what
format? This determines whether Phase 6's PRD covers tools only, or tools + a skill deliverable with its own
implementation phase.

### Summary of tool set entering Phase 6

| Tool | Server | Input (Decision 2 shape) | Draft-cache role (Decision 1) |
|---|---|---|---|
| `create_scenario` | studio | `name` (optional) | mints `draft_id`, seeds `{name, steps: []}` |
| `add_step` / `remove_step` | studio | `draft_id`, `step_name` (**required**, themed — F11) | mutates draft |
| `add_attacks_to_step` / `remove_attacks_from_step` | studio | `draft_id`, `step_name`, `attack_ids[]` **xor** `attacks_filter` | mutates draft |
| `list_simulators` | studio | `draft_id` optional (browse-only, read-only tool), basic filters | reads draft for context only |
| `add_simulators_to_step` / `remove_simulators_from_step` | studio | `draft_id`, `step_name`, `simulator_ids[]` **xor** `attacker_filter`/`target_filter` | mutates draft |
| `save_scenario` | studio | `draft_id`, `save_as_new`, `name` (if `save_as_new`) | reads + wraps with `type`/`propagateDefinition`, POST/PUT `config/v3/plans`, evicts draft |

**Status**: `Phase 5: Brainstorm`
