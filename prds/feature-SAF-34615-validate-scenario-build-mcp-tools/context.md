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

_Pending — Phase 4._

---

## 7. Brainstorm Outcome

_Pending — Phase 5._
