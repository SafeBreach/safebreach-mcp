# Test Plan — MCP support for Validate scenario creation and update, Stage 1 (SAF-34615)

> PRD: ./prd.md  |  Branch: feature/SAF-34615-validate-scenario-build-mcp-tools  |  Status: Draft  |  Updated: 2026-09-03 06:20

## Status & Review

| Field | Value |
|-------|-------|
| Status | Reviewed (In Sync with PRD v1) |
| Offering / surface | Validate + console + repo-harness (not Propagate, not UI) |

## Requirements Traceability

Sources: JIRA SAF-34615 Definition of Done ∪ PRD §7 Definition of Done, user-confirmed at the Phase 2 gate
(2026-09-03).

| Req | Requirement | Covered by | Status |
|-----|-------------|------------|--------|
| R1 | User can build+save a complete Validate scenario through Helm alone, using only this story's tools | T-36 | Covered |
| R2 | No scenario is created with a Propagate plan-type or attack, regardless of license | T-22, T-23, T-31 | Covered |
| R3 | No data-asset/proxy/impersonated-user association is performed by this flow | T-23 | Covered (contract check — no tool signature accepts these inputs) |
| R4 | All 8 new tools + `get_playbook_attacks` enhancement are registered, documented, rate-limited where required | T-25–T-29, T-38 | Covered |
| R5 | Draft-cache lifecycle: create, mutate across calls, evict on save, clear "not found" error when absent | T-1, T-2, T-3, T-39 | Covered |
| R6 | `add_step` requires a themed name (rejects empty/default), rejects duplicate names; `remove_step` removes its attacks/simulators too | T-4–T-8 | Covered |
| R7 | Attack selection: `attack_ids`→`playbook` (never `methodIds`), or exactly one filter axis; mutual exclusivity enforced; values accumulate; removal only from the explicit-id axis | T-9–T-16 | Covered |
| R8 | `get_playbook_attacks` gains 3 filter params with no new upstream call; existing filters unaffected | T-17, T-18, T-33 | Covered |
| R9 | `list_simulators` read-only; `add/remove_simulators_to_step` explicit-ID-only; `role` picks `attackerFilter` vs `targetFilter` | T-19–T-21, T-34 | Covered |
| R10 | `save_scenario` force-sets `type:'validate'`/`propagateDefinition:null` on every request; no tool accepts a `tags` input | T-22, T-23 | Covered |
| R11 | `save_scenario` requires a clean pre-save blocked-entities check before persisting | T-31 | Covered — tested against `sb_get_plan_statistics` directly (the surviving shared plumbing), not the not-yet-registered `get_scenario_blocked_entities` tool, to avoid blocking on SAF-35508 phases 7–9 |
| R12 | DB unique-constraint `(name, accountId)` violation surfaces as a clear typed error | T-32 | Covered |
| R13 | `save_scenario` create-vs-update branching, `save_as_new` semantics | T-24, T-30 | Covered |
| R14 | All 8 mutating tools follow the rate-limit gate pattern; `list_simulators`/`get_playbook_attacks` stay unrated | T-25–T-29 | Covered |

**Out of scope for this plan (Phase 2 gate, confirmed 2026-09-03)**: JIRA DoD2 (console-number accuracy) and
DoD5 (fresh-conflict re-check on change) are SAF-35508's own deliverables — this PRD's Component F only
documents that dependency and builds no code against it. No R-item here; verified in SAF-35508's own test plan.

## Change Coverage

| File | Covered by | Justification (if no unit test) |
|------|------------|----------------------------------|
| `safebreach_mcp_studio/studio_functions.py` | T-1–T-24, T-25–T-32, T-38, T-39 | — |
| `safebreach_mcp_studio/studio_types.py` | T-1, T-2 | — |
| `safebreach_mcp_studio/studio_server.py` | T-38 | Registration wiring; behavior covered transitively by every tool-level test above |
| `safebreach_mcp_playbook/playbook_types.py` | T-17, T-18, T-33 | — |
| `safebreach_mcp_playbook/playbook_functions.py` | T-17, T-18, T-33 | — |
| `safebreach_mcp_playbook/playbook_server.py` | T-33 | Registration wiring; parameter passthrough covered by T-33 |
| `CLAUDE.md` | — | Docs-only, no runtime surface; content accuracy checked at PRD DoD review, not by pytest |
| `CHANGELOG.md` | — | Docs-only, no runtime surface |
| `pyproject.toml` | — | Version bump only, no runtime surface |

## Risk Landscape

- **Known risk areas** (from PRD §9, R1 leads): SAF-35508's `get_scenario_simulation_counts`/
  `get_scenario_blocked_entities`/`get_scenario_attack_blockers` are not yet implemented (D4 phases 7–9,
  "not started"); the in-process draft cache is single-worker state (R2); this PRD's tool contract deliberately
  diverges from FR13's literal text (R3); FR2's CVE/threat-actor search stays only partially closed via the
  generic `tags_filter` (R4); console-validation parity is intentionally partial (R5); `config/v3/plans` has
  zero existing production callers — `save_scenario` is its first (R6); SAF-35508's own AC-4/T-35 (console
  number parity) is unverified, inherited not created here (R7).
- **Existing coverage (investigated)**: `get_playbook_attacks`'s current MITRE/platform filters are tested in
  `safebreach_mcp_playbook/tests/test_playbook_functions.py` and `test_playbook_types.py` — zero coverage for
  the new type/phase/tags axes (pure gap). `studio_draft_cache` (`studio_functions.py:51`) is the direct
  precedent for the new `scenario_draft_cache`. `test_rate_limiting.py` (901 lines) is the copyable template
  for every gate test in this plan — asserts `call_order == ["check_limit", "api_call", "record_action"]`.
  `sb_quick_run`/`sb_run_scenario` are the closest existing mutating-tool precedents for structure and error
  handling.
- **What we protect**: the mutual-exclusivity rule on attack/simulator selection (a silent AND/OR mix would
  corrupt a saved plan's `attacksFilter` semantics); the `type`/`propagateDefinition` force-set (a missed
  force-set is a structural Propagate-guard regression); the `playbook` vs `methodIds` mapping (using the dead
  field would silently produce a step that selects zero attacks).
- **Intentionally out of scope**:
  - **DoD2/DoD5**: SAF-35508's own scope, not retested here (see Requirements Traceability).
  - **A real end-to-end check that an ALM-tagged attack is actually stripped by the live orchestrator**: the
    structural guard (`type`/`propagateDefinition`, no `tags` input) is unit-tested here (T-22, T-23); the
    live-stripping mechanism itself (`filterMoves`'s ALM exclusion) is orchestrator behavior outside this
    repo's code and outside SAF-35508's own stated scope too — accepted as verified-by-code-reading
    (`context.md` §6.11/§6.15), not re-proven by a real-environment test in this plan.
  - **A dedicated Manual regression test**: genuine automation infra already covers this angle — the
    `automation` repo's `tests/ui/attack_menu/scenarios/test_add_scenario.py`/`test_save_scenario.py`
    (Playwright, run by `Jenkinsfile.PlaywrightUiTests.groovy`/`Jenkinsfile.ManagementPreMergeUiReact.groovy`)
    already exercise the shared console-UI Studio flow (v2) this feature's v3 additions sit alongside on the
    same `plans`/`steps` DB tables. Per the "Manual is not justified when automation infra exists" rule, no
    new Manual regression test is authored here — the Regression section below names that existing suite.

## Coverage Summary (generated)

| Execution | unit | integration | system | e2e | Total |
|-----------|------|-------------|--------|-----|-------|
| Automatic | 25   | 10          | 2      | 1   | 38    |
| Manual    | 0    | 0           | 0      | 1   | 1     |

## Environment Requirements (aggregated)

- Environment classes: **repo-harness** (unit/integration — the large majority of this feature, since Components
  A–D and most of E have zero external HTTP call); **console environment (Validate class), minimal** (system/e2e
  — needed only for `save_scenario`'s real POST/PUT, `list_simulators`, and the full-workflow e2e test).

Capability checklist (answered from this plan's system/e2e tests only — T-34, T-35, T-36, T-37):

- [x] Simulators required? — **Yes, as registered metadata only.** T-34/T-35/T-36 need simulator objects to
  exist (id, connected/disabled state, OS) for filter-matching and plan-write assertions; none needs live
  attacker/target hardware.
- [x] Running simulations / attacks required? — **No.** This story explicitly excludes run/schedule triggering
  (PRD §1); no test executes a simulation.
- [x] Mockulators sufficient? — **Yes.** No test in this plan reads back an actual attack result; mockulator
  metadata (connected/disconnected/OS) is indistinguishable from a real simulator's for every assertion here.
- [x] Console-specific configuration required? — **No new config.** Existing per-console API-token auth only;
  default seeded playbook/attack catalog; a handful of simulators with varied connected/OS attributes to
  exercise `list_simulators` and the filter/statistics-reason paths. No RBAC roles, feature flags, or
  EDR/SIEM connectors needed.
- [x] Lateral-movement topology required? — **No.** Confirmed Validate-only; no Propagate DC/patient-zero/
  victim topology has any bearing on this PRD's tools.
- Required additions (beyond class defaults): none — a handful of pre-registered simulators with varied
  connected/disconnected/OS attributes is within the default console class's normal composition.
- Artifacts under test: none — no feature-branch image/installer track; this PRD ships as an MCP server code
  change against an existing, unmodified console API surface.

## Regression

- **CI that must pass**: this repo's own `uv run pytest` suite (unit + integration, all phases); the
  `automation` repo's existing UI Studio-scenario suite (`tests/ui/attack_menu/scenarios/`, run by
  `Jenkinsfile.PlaywrightUiTests.groovy` / `Jenkinsfile.ManagementPreMergeUiReact.groovy`) — named here as the
  regression evidence for the shared `plans`/`steps` DB surface this feature's `v3` writes sit alongside; no
  `Automation-Pen-Testing-*` job applies (that family is Propagate/pen-test domain, unrelated to this Validate
  -only feature — corrected during investigation, the originally-assumed job family does not map here).
- **Regression tests in this plan**: none authored directly (see Risk Landscape "Intentionally out of scope" —
  existing automation infra already covers this angle).

## Tests

**Unit** — all Automatic; environment: none

| Test | Description | Aspect | Passes after | Repo |
|------|-------------|--------|---------------|------|
| T-1  | `create_scenario` mints a unique `draft_id` and seeds `{name, steps: []}` | — | Phase 1 | safebreach_mcp_studio |
| T-2  | `create_scenario` with no `name` defaults to `""`, not `None`/error | — | Phase 1 | safebreach_mcp_studio |
| T-3  | A tool call against an absent `draft_id` raises a clear "draft not found" error | — | Phase 2 | safebreach_mcp_studio |
| T-4  | `add_step` rejects an empty/whitespace-only `step_name` | — | Phase 2 | safebreach_mcp_studio |
| T-5  | `add_step` rejects a duplicate `step_name` within the same draft | — | Phase 2 | safebreach_mcp_studio |
| T-6  | `add_step` appends a themed step with empty `attacksFilter`/`attackerFilter`/`targetFilter` base objects | — | Phase 2 | safebreach_mcp_studio |
| T-7  | `remove_step` removes the step and its attacks/simulators | — | Phase 2 | safebreach_mcp_studio |
| T-8  | `remove_step` on an unknown `step_name` raises rather than no-opping | — | Phase 2 | safebreach_mcp_studio |
| T-9  | `add_attacks_to_step(attack_ids=...)` merges into `attacksFilter.playbook` (never `methodIds`), operator `is` | — | Phase 3 | safebreach_mcp_studio |
| T-10 | `add_attacks_to_step` rejects when both `attack_ids` and a filter param are supplied | — | Phase 3 | safebreach_mcp_studio |
| T-11 | `add_attacks_to_step` rejects when neither `attack_ids` nor any filter param is supplied | — | Phase 3 | safebreach_mcp_studio |
| T-12 | Two sequential `attack_ids` calls extend, not replace, `attacksFilter.playbook.values` | — | Phase 3 | safebreach_mcp_studio |
| T-13 | `attack_phase_filter` maps each of the 4 phase strings to the correct `Package` integer | API-contract | Phase 3 | safebreach_mcp_studio |
| T-14 | `attack_phase_filter` rejects an unrecognized phase string | — | Phase 3 | safebreach_mcp_studio |
| T-15 | `tags_filter` merges each `{group: values}` entry into `attacksFilter.tags[group]` | — | Phase 3 | safebreach_mcp_studio |
| T-16 | `remove_attacks_from_step` removes only from `attacksFilter.playbook.values`; raises on an unknown id/axis | — | Phase 3 | safebreach_mcp_studio |
| T-17 | `get_playbook_attacks`'s 3 new filters each correctly narrow a hand-built attack list; missing-tag-data attacks are excluded | — | Phase 4 | safebreach_mcp_playbook |
| T-18 | `get_playbook_attacks`'s existing filters (name/date/MITRE/platform) are unaffected by the new params | regression | Phase 4 | safebreach_mcp_playbook |
| T-19 | `add_simulators_to_step`: `role='attacker'` → `attackerFilter.simulators`; `role='target'` → `targetFilter.simulators` | — | Phase 6 | safebreach_mcp_studio |
| T-20 | `add_simulators_to_step` rejects an invalid `role` value | — | Phase 6 | safebreach_mcp_studio |
| T-21 | `remove_simulators_from_step` removes only the given role's `simulators.values`; raises on an unknown id | — | Phase 6 | safebreach_mcp_studio |
| T-22 | `save_scenario`'s wire-body assembler always sets `type:'validate'`/`propagateDefinition:null`, regardless of draft content | — | Phase 7 | safebreach_mcp_studio |
| T-23 | Contract check: no tool in the 8-tool set accepts a `tags`, `data_assets`, `proxies`, or `impersonated_users` input parameter | API-contract | Final | safebreach_mcp_studio |
| T-24 | `save_scenario` branches POST (no id) vs PUT (with id) correctly per `save_as_new`/prior `scenario_id` | — | Phase 7 | safebreach_mcp_studio |
| T-38 | Every registered tool carries the correct `ToolAnnotations` (`readOnlyHint=False` for the 8 mutating tools, `True` for `list_simulators`) | API-contract | Final | safebreach_mcp_studio |

**Integration** — all Automatic

| Test | Description | Aspect | Passes after | Repo | Environment |
|------|-------------|--------|---------------|------|-------------|
| T-25 | `create_scenario`'s rate-limit gate: `check_limit` before the cache write, `record_action` only after success | — | Phase 1 | safebreach_mcp_studio | repo-harness |
| T-26 | `add_step`/`remove_step` rate-limit gate pattern | — | Phase 2 | safebreach_mcp_studio | repo-harness |
| T-27 | `add_attacks_to_step`/`remove_attacks_from_step` rate-limit gate pattern | — | Phase 3 | safebreach_mcp_studio | repo-harness |
| T-28 | `add_simulators_to_step`/`remove_simulators_from_step` rate-limit gate pattern | — | Phase 6 | safebreach_mcp_studio | repo-harness |
| T-29 | `save_scenario`'s rate-limit gate: `check_limit` before the POST/PUT, `record_action` only after a successful response (never on 4xx/5xx) | — | Phase 7 | safebreach_mcp_studio | repo-harness |
| T-30 | `save_scenario`'s full request-body assembly: build a draft in-process, mock `requests.post`, assert the exact posted body shape (`name`/`steps`/`type`/`propagateDefinition`) | API-contract | Phase 7 | safebreach_mcp_studio | repo-harness |
| T-31 | `save_scenario`'s pre-save gate: when `sb_get_plan_statistics` (called directly) reports a blocking conflict, `save_scenario` refuses to persist and surfaces a clear error, with no POST/PUT issued | — | Phase 7 | safebreach_mcp_studio | repo-harness |
| T-32 | `save_scenario` handles a mocked DB unique-constraint violation `(name, accountId)` with a clear typed "name already in use" error, not a raw passthrough | — | Phase 7 | safebreach_mcp_studio | repo-harness |
| T-33 | `get_playbook_attacks` integration: mock the KB fetch with realistic nested tag data, exercise the real fetch→transform→filter pipeline end-to-end for all 3 new filters | — | Phase 4 | safebreach_mcp_playbook | repo-harness |
| T-39 | `save_scenario` evicts the `draft_id` from `scenario_draft_cache` after a successful save; a failed save (mocked 500) leaves the draft entry intact | — | Phase 7 | safebreach_mcp_studio | repo-harness |

**System**

| Test | Description | Exec | Aspect | Passes after | Repo | Environment |
|------|-------------|------|--------|---------------|------|-------------|
| T-34 | `list_simulators` against a real minimal console returns simulator metadata matching `get_console_simulators`' existing contract | Automatic | — | Phase 5 | safebreach_mcp_studio | console environment (Validate, minimal) |
| T-35 | A single `save_scenario` POST against a real minimal console creates a real plan, verified via a raw GET on `config/v3/plans/{id}`, confirming server-side `type='validate'` | Automatic | — | Phase 7 | safebreach_mcp_studio | console environment (Validate, minimal) |

**E2E**

| Test | Description | Exec | Aspect | Passes after | Repo | Environment |
|------|-------------|------|--------|---------------|------|-------------|
| T-36 | Full build-through-save workflow (`create_scenario`→`add_step`→`add_attacks_to_step`→`add_simulators_to_step`→`save_scenario`) against a real minimal console, verified by reading the saved plan back | Automatic | — | Phase 7 | safebreach_mcp_studio | console environment (Validate, minimal) |
| T-37 | AI-executed walkthrough calling the new MCP tools exactly as Helm would, then inspecting the resulting scenario in the console's own Studio UI for coherence | Manual | progression | Final | — | console environment (Validate, minimal) |

### T-1 — `create_scenario` mints a unique draft

- Description: Proves the draft store actually creates an isolated, addressable entry per call — the
  foundation every other tool depends on.
- Status: Active
- Passes after: Phase 1
- Level: unit
- Execution: Automatic
- Risk: A colliding or predictable `draft_id` would let one conversation's draft leak into another's.
- Risk source: PRD Component A
- Verify: Call `sb_create_scenario` twice with the same `name`; inspect both returned `draft_id`s and the
  cache contents.
- Expected: Two distinct `draft_id`s (uuid4 format); each maps to its own `{name, steps: []}` entry in
  `scenario_draft_cache`.
- Evidence required: CI run (butler job + build #).
- Automation lives in: `safebreach_mcp_studio/tests/test_studio_functions.py`

### T-2 — `create_scenario` default name

- Description: Proves `name` is genuinely optional and doesn't crash or store `None` where a string is expected.
- Status: Active
- Passes after: Phase 1
- Level: unit
- Execution: Automatic
- Risk: A `None` name reaching the eventual `config/v3/plans` body would fail schema validation at save time,
  far from the actual cause.
- Risk source: PRD Component A
- Verify: Call `sb_create_scenario(name=None, ...)`.
- Expected: The stored draft's `name` field is `""`, not `None`.
- Evidence required: CI run (butler job + build #).
- Automation lives in: `safebreach_mcp_studio/tests/test_studio_functions.py`

### T-3 — draft-not-found error is clear

- Description: Proves a caller referencing an evicted/unknown `draft_id` gets a legible error instead of a
  crash or a silent no-op.
- Status: Active
- Passes after: Phase 2
- Level: unit
- Execution: Automatic
- Risk: A silent no-op here would make every downstream tool's "success" response meaningless.
- Risk source: PRD Component A, §9 R2
- Verify: Call `sb_add_step` with a `draft_id` never returned by `create_scenario`.
- Expected: A `ValueError` (or equivalent typed error) naming the draft as not found; no cache mutation occurs.
- Evidence required: CI run (butler job + build #).
- Automation lives in: `safebreach_mcp_studio/tests/test_studio_functions.py`

### T-4 — `add_step` rejects empty name

- Description: Proves the one console default this story deliberately does not replicate is actually blocked,
  not merely undocumented.
- Status: Active
- Passes after: Phase 2
- Level: unit
- Execution: Automatic
- Risk: An empty/whitespace step name reaching a saved plan reproduces the console's own anti-pattern this
  story exists partly to avoid.
- Risk source: PRD Component B (F11)
- Verify: Call `sb_add_step` with `step_name=""` and with `step_name="   "`.
- Expected: Both raise a validation error; the draft's step list is unchanged.
- Evidence required: CI run (butler job + build #).
- Automation lives in: `safebreach_mcp_studio/tests/test_studio_functions.py`

### T-5 — `add_step` rejects duplicate name

- Description: Proves two steps can't silently collide under the same name within one draft.
- Status: Active
- Passes after: Phase 2
- Level: unit
- Execution: Automatic
- Risk: Duplicate step names make later `add_attacks_to_step`/`add_simulators_to_step` calls ambiguous about
  which step they target.
- Risk source: PRD Component B
- Verify: Call `sb_add_step` twice with the same `step_name` on the same draft.
- Expected: The second call raises; the draft still has exactly one step with that name.
- Evidence required: CI run (butler job + build #).
- Automation lives in: `safebreach_mcp_studio/tests/test_studio_functions.py`

### T-6 — `add_step` base shape

- Description: Proves a newly added step matches the base-object convention the rest of the pipeline
  (`get_plan_statistics`, `save_scenario`) expects.
- Status: Active
- Passes after: Phase 2
- Level: unit
- Execution: Automatic
- Risk: An omitted (vs. empty-object) filter key could be treated differently by downstream consumers than the
  console's own `getStepsForApi` convention.
- Risk source: PRD Component B
- Verify: Call `sb_add_step` with a valid themed name; inspect the resulting step object.
- Expected: The step has `name`, and empty-object (not omitted) `attacksFilter`, `attackerFilter`,
  `targetFilter`.
- Evidence required: CI run (butler job + build #).
- Automation lives in: `safebreach_mcp_studio/tests/test_studio_functions.py`

### T-7 — `remove_step` removes its content

- Description: Proves removing a step doesn't leave orphaned attack/simulator data behind in the draft.
- Status: Active
- Passes after: Phase 2
- Level: unit
- Execution: Automatic
- Risk: Orphaned filter data surviving step removal could resurface unexpectedly in a later save.
- Risk source: PRD Component B
- Verify: Add a step, add attacks and simulators to it, then remove it.
- Expected: The step and everything under it is gone from the draft; no other step is affected.
- Evidence required: CI run (butler job + build #).
- Automation lives in: `safebreach_mcp_studio/tests/test_studio_functions.py`

### T-8 — `remove_step` on unknown name raises

- Description: Proves removal failures are never silently swallowed.
- Status: Active
- Passes after: Phase 2
- Level: unit
- Execution: Automatic
- Risk: A silent no-op would let Helm believe a step was removed when it wasn't.
- Risk source: PRD Component B, §9 R2
- Verify: Call `sb_remove_step` with a `step_name` not present in the draft.
- Expected: Raises a clear error; the draft's step list is unchanged.
- Evidence required: CI run (butler job + build #).
- Automation lives in: `safebreach_mcp_studio/tests/test_studio_functions.py`

### T-9 — explicit attack ids use `playbook`, never `methodIds`

- Description: Proves the one field-name decision most likely to silently fail (both keys exist in the
  swagger schema, only one is implemented server-side) is actually implemented correctly.
- Status: Active
- Passes after: Phase 3
- Level: unit
- Execution: Automatic
- Risk: Writing to `methodIds` would produce a step that silently selects zero attacks — verified via
  `orchestrator/src/server/other/playbook_filter.js` to have no implementation for that key.
- Risk source: `context.md` §7 Decision 2 refinement (F5 resolution)
- Verify: Call `sb_add_attacks_to_step(attack_ids=[101, 102])` on a fresh step.
- Expected: `attacksFilter.playbook == {"operator": "is", "values": [101, 102], "name": "playbook"}`;
  `attacksFilter.methodIds` is absent.
- Evidence required: CI run (butler job + build #).
- Automation lives in: `safebreach_mcp_studio/tests/test_studio_functions.py`

### T-10 — mutual exclusivity: both supplied rejected

- Description: Proves the rule grounded in `scenario-step-grouping.md` rule 5 (a step's attack selection is
  exactly one mode, never a combination) is actually enforced, not just documented.
- Status: Active
- Passes after: Phase 3
- Level: unit
- Execution: Automatic
- Risk: Silently ANDing `attack_ids` with a filter would corrupt the step's `attacksFilter` semantics in a way
  that's hard to detect later.
- Risk source: PRD Component B, `context.md` §7 Decision 2
- Verify: Call `sb_add_attacks_to_step(attack_ids=[101], attack_type_filter="X")`.
- Expected: Raises a validation error naming both parameters; no draft mutation occurs.
- Evidence required: CI run (butler job + build #).
- Automation lives in: `safebreach_mcp_studio/tests/test_studio_functions.py`

### T-11 — mutual exclusivity: neither supplied rejected

- Description: Proves a no-op call (nothing to select) is rejected rather than silently accepted.
- Status: Active
- Passes after: Phase 3
- Level: unit
- Execution: Automatic
- Risk: A silently-accepted empty call gives Helm false confirmation that attacks were added.
- Risk source: PRD Component B
- Verify: Call `sb_add_attacks_to_step` with `attack_ids=None` and all three filter params `None`.
- Expected: Raises a validation error.
- Evidence required: CI run (butler job + build #).
- Automation lives in: `safebreach_mcp_studio/tests/test_studio_functions.py`

### T-12 — repeated `attack_ids` calls extend

- Description: Proves attack selection accumulates across turns of a conversation, rather than the last call
  silently overwriting earlier ones.
- Status: Active
- Passes after: Phase 3
- Level: unit
- Execution: Automatic
- Risk: A replace-not-extend bug would silently drop attacks a user thought were already added.
- Risk source: PRD Component B
- Verify: Call `sb_add_attacks_to_step(attack_ids=[101])`, then `sb_add_attacks_to_step(attack_ids=[102])` on
  the same step.
- Expected: `attacksFilter.playbook.values == [101, 102]` (order-independent set equality), not `[102]`.
- Evidence required: CI run (butler job + build #).
- Automation lives in: `safebreach_mcp_studio/tests/test_studio_functions.py`

### T-13 — `attack_phase_filter` enum mapping

- Description: Proves every one of the 4 accepted phase strings maps to the orchestrator's actual integer
  enum — a silent off-by-one here selects entirely the wrong attack phase.
- Status: Active
- Passes after: Phase 3
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: A wrong mapping (e.g. `infiltration` sent as `1` instead of `2`) silently selects `lateral` attacks
  instead of `infiltration` ones — a correctness bug invisible without cross-checking the orchestrator source.
- Risk source: `context.md` §7 Decision 2 refinement
- Verify: Call `sb_add_attacks_to_step(attack_phase_filter=<each of "infiltration"|"lateral"|"exfiltration"|
  "host_level">)` in 4 separate assertions.
- Expected: `attacksFilter.attackPhase.values == [2]` for infiltration, `[1]` lateral, `[0]` exfiltration,
  `[5]` host_level.
- Evidence required: CI run (butler job + build #).
- Automation lives in: `safebreach_mcp_studio/tests/test_studio_functions.py`

### T-14 — `attack_phase_filter` rejects unknown string

- Description: Proves an unrecognized phase string fails loudly rather than being silently dropped or passed
  through as garbage.
- Status: Active
- Passes after: Phase 3
- Level: unit
- Execution: Automatic
- Risk: A silently-ignored bad value would produce a step with no phase constraint at all, wider than intended.
- Risk source: PRD Component B
- Verify: Call `sb_add_attacks_to_step(attack_phase_filter="not_a_real_phase")`.
- Expected: Raises a validation error.
- Evidence required: CI run (butler job + build #).
- Automation lives in: `safebreach_mcp_studio/tests/test_studio_functions.py`

### T-15 — `tags_filter` group-keyed merge

- Description: Proves the generic tag-group escape hatch (the mechanism standing in for a dedicated CVE/
  threat-actor filter) actually writes to the right nested location.
- Status: Active
- Passes after: Phase 3
- Level: unit
- Execution: Automatic
- Risk: A flattened or mis-keyed write here silently breaks Threat Actor/CVE-style filtering entirely.
- Risk source: PRD Component B
- Verify: Call `sb_add_attacks_to_step(tags_filter={"Threat Actor": ["APT29"], "CVE": ["CVE-2024-1234"]})`.
- Expected: `attacksFilter.tags["Threat Actor"].values == ["APT29"]` and
  `attacksFilter.tags["CVE"].values == ["CVE-2024-1234"]`, as two independent group entries.
- Evidence required: CI run (butler job + build #).
- Automation lives in: `safebreach_mcp_studio/tests/test_studio_functions.py`

### T-16 — `remove_attacks_from_step` scope

- Description: Proves removal is restricted to the explicit-id axis, since removing from a criteria-based
  filter has no well-defined meaning in Stage 1.
- Status: Active
- Passes after: Phase 3
- Level: unit
- Execution: Automatic
- Risk: An unscoped removal could silently mutate a type/phase/tags filter axis in an undefined way.
- Risk source: PRD Component B
- Verify: (a) Remove an id present in `attacksFilter.playbook.values`; (b) attempt removal when
  `attacksFilter.playbook` doesn't exist; (c) attempt removal of an id never added.
- Expected: (a) succeeds, id gone from `values`; (b) and (c) both raise clear errors.
- Evidence required: CI run (butler job + build #).
- Automation lives in: `safebreach_mcp_studio/tests/test_studio_functions.py`

### T-17 — `get_playbook_attacks` new filters narrow correctly

- Description: Proves each of the 3 new filter axes actually filters, and correctly excludes attacks missing
  the relevant tag data rather than erroring or including them by default.
- Status: Active
- Passes after: Phase 4
- Level: unit
- Execution: Automatic
- Risk: A silently-inclusive filter (treating "no data" as "matches") would make the filter useless for its
  purpose — helping Helm narrow a search.
- Risk source: PRD Component D
- Verify: Build a small in-memory attack list with varied/missing tag data; call
  `filter_attacks_by_criteria` with each of `attack_type_filter`, `attack_phase_filter`, `tags_filter` in turn.
- Expected: Each filter returns only the matching attacks; attacks lacking the relevant tag/data are excluded,
  not errored on.
- Evidence required: CI run (butler job + build #).
- Automation lives in: `safebreach_mcp_playbook/tests/test_playbook_types.py`

### T-18 — existing filters unaffected

- Description: Proves adding the 3 new filters didn't regress the 5 filters that already ship.
- Status: Active
- Passes after: Phase 4
- Level: unit
- Execution: Automatic
- Aspect: regression
- Risk: A threading-through change (raw tags now flow further) could accidentally alter existing filter
  behavior.
- Risk source: PRD Component D
- Verify: Re-run the existing `name_filter`/`mitre_technique_filter`/platform-filter test cases after the
  Phase 4 change.
- Expected: All pre-existing filter behavior is bit-for-bit unchanged.
- Evidence required: CI run (butler job + build #).
- Automation lives in: `safebreach_mcp_playbook/tests/test_playbook_types.py`

### T-19 — `add_simulators_to_step` role routing

- Description: Proves `role` correctly routes to the two different filter objects it's meant to select
  between, since `role` is not itself a filter value.
- Status: Active
- Passes after: Phase 6
- Level: unit
- Execution: Automatic
- Risk: A swapped attacker/target assignment would silently invert which simulators attack and which are
  targeted.
- Risk source: PRD Component C
- Verify: Call `sb_add_simulators_to_step(role="attacker", simulator_ids=["sim-1"])` and, separately,
  `role="target"`.
- Expected: `attackerFilter.simulators.values == ["sim-1"]` for the first call;
  `targetFilter.simulators.values == ["sim-1"]` for the second; the other filter object is untouched by each.
- Evidence required: CI run (butler job + build #).
- Automation lives in: `safebreach_mcp_studio/tests/test_studio_functions.py`

### T-20 — invalid role rejected

- Description: Proves a typo'd or invalid role value fails loudly.
- Status: Active
- Passes after: Phase 6
- Level: unit
- Execution: Automatic
- Risk: A silently-ignored bad role could write to neither filter, leaving Helm believing simulators were added.
- Risk source: PRD Component C
- Verify: Call `sb_add_simulators_to_step(role="both", ...)`.
- Expected: Raises a validation error.
- Evidence required: CI run (butler job + build #).
- Automation lives in: `safebreach_mcp_studio/tests/test_studio_functions.py`

### T-21 — `remove_simulators_from_step` scope

- Description: Proves removal only touches the specified role's simulator list.
- Status: Active
- Passes after: Phase 6
- Level: unit
- Execution: Automatic
- Risk: A removal that touches the wrong role's filter would silently corrupt the other side's simulator
  selection.
- Verify: Add simulators to both roles; remove one id from `role="attacker"`.
- Expected: Only `attackerFilter.simulators.values` loses that id; `targetFilter` is unaffected. Removing an
  id never added raises.
- Risk source: PRD Component C
- Evidence required: CI run (butler job + build #).
- Automation lives in: `safebreach_mcp_studio/tests/test_studio_functions.py`

### T-22 — `save_scenario` force-sets type/propagateDefinition

- Description: Proves the structural half of the Propagate guard actually fires on every save, independent of
  whatever the draft happens to contain.
- Status: Active
- Passes after: Phase 7
- Level: unit
- Execution: Automatic
- Risk: A missed force-set is a direct regression of DoD3/FR1's core guarantee.
- Risk source: PRD Component E, §7 DoD3
- Verify: Assemble the wire body from a draft that has no `type`/`propagateDefinition` fields at all (the
  normal case, since the draft never carries them).
- Expected: The assembled body has `type: "validate"` and `propagateDefinition: null`, unconditionally.
- Evidence required: CI run (butler job + build #).
- Automation lives in: `safebreach_mcp_studio/tests/test_studio_functions.py`

### T-23 — no tool accepts a `tags`/asset-association input

- Description: Proves, as a standing contract across the whole finished tool set, that the input surfaces this
  design deliberately never exposes really don't exist — the simplest and most robust form of the Propagate
  and data-asset guards.
- Status: Active
- Passes after: Final
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: A future edit accidentally adding a `tags` (or `data_assets`/`proxies`/`impersonated_users`) parameter
  to any of the 8 tools would silently reopen the F16 Propagate-tag hole or DoD4's asset-association exclusion.
- Risk source: PRD Component E, §7 DoD3/DoD4
- Verify: Introspect the registered parameter names of all 8 tools (`create_scenario`, `add_step`,
  `remove_step`, `add_attacks_to_step`, `remove_attacks_from_step`, `add_simulators_to_step`,
  `remove_simulators_from_step`, `save_scenario`).
- Expected: None of the 8 signatures include `tags`, `data_assets`, `proxies`, or `impersonated_users`.
- Evidence required: CI run (butler job + build #).
- Automation lives in: `safebreach_mcp_studio/tests/test_studio_functions.py`

### T-24 — create-vs-update branching

- Description: Proves `save_scenario` picks the right HTTP method/target based on `save_as_new` and whether
  the draft already references a saved `scenario_id`.
- Status: Active
- Passes after: Phase 7
- Level: unit
- Execution: Automatic
- Risk: A wrong branch would create a duplicate scenario when an update was intended, or vice versa.
- Risk source: PRD §4, Component E
- Verify: (a) fresh draft, no prior `scenario_id` → call `save_scenario`; (b) a draft with a prior
  `scenario_id`, `save_as_new=False`; (c) same draft, `save_as_new=True`.
- Expected: (a) and (c) both target `POST .../plans` with no `id` in the body; (b) targets
  `PUT .../plans/{id}`.
- Evidence required: CI run (butler job + build #).
- Automation lives in: `safebreach_mcp_studio/tests/test_studio_functions.py`

### T-38 — tool annotations

- Description: Proves every tool is registered with the correct `readOnlyHint`, catching an accidental flip
  that would silently exempt a mutating tool from the rate-limit gate or misclassify a read tool as mutating.
- Status: Active
- Passes after: Final
- Level: unit
- Execution: Automatic
- Aspect: API-contract
- Risk: A wrong `readOnlyHint` on a mutating tool would silently skip its rate-limit gate.
- Risk source: PRD §6, CLAUDE.md convention
- Verify: Introspect the registered `ToolAnnotations` for all 9 tools (8 new + `get_playbook_attacks`).
- Expected: `readOnlyHint=False` for the 8 mutating tools; `readOnlyHint=True` for `list_simulators` and
  `get_playbook_attacks`.
- Evidence required: CI run (butler job + build #).
- Automation lives in: `safebreach_mcp_studio/tests/test_studio_functions.py`

### T-25 — `create_scenario` rate-limit gate

- Description: Proves the mandatory gate pattern (check before, record only after success) is wired correctly
  for the first tool, following the `test_rate_limiting.py` template.
- Status: Active
- Passes after: Phase 1
- Level: integration
- Execution: Automatic
- Risk: A missing/misordered gate call defeats the whole rate-limiting feature for this tool.
- Risk source: CLAUDE.md rate-limiting convention
- Verify: Patch `rate_limiter` and the cache write with `side_effect` call-order tracking, per
  `test_rate_limiting.py`'s pattern; call `create_scenario`.
- Expected: `call_order == ["check_limit", "cache_write", "record_action"]`;
  `check_limit` called once with `(caller_id, "create_scenario")`.
- Evidence required: CI run (butler job + build #).
- Automation lives in: `safebreach_mcp_studio/tests/test_rate_limiting.py`
- Environment needs: repo-harness

### T-26 — `add_step`/`remove_step` rate-limit gate

- Description: Same gate-order proof for both step-management tools.
- Status: Active
- Passes after: Phase 2
- Level: integration
- Execution: Automatic
- Risk: Same as T-25, for these two tools.
- Risk source: CLAUDE.md rate-limiting convention
- Verify: Same pattern as T-25, for `add_step` and `remove_step`.
- Expected: Same call-order guarantee for both.
- Evidence required: CI run (butler job + build #).
- Automation lives in: `safebreach_mcp_studio/tests/test_rate_limiting.py`
- Environment needs: repo-harness

### T-27 — `add_attacks_to_step`/`remove_attacks_from_step` rate-limit gate

- Description: Same gate-order proof for both attack-selection tools.
- Status: Active
- Passes after: Phase 3
- Level: integration
- Execution: Automatic
- Risk: Same as T-25, for these two tools.
- Risk source: CLAUDE.md rate-limiting convention
- Verify: Same pattern as T-25.
- Expected: Same call-order guarantee for both.
- Evidence required: CI run (butler job + build #).
- Automation lives in: `safebreach_mcp_studio/tests/test_rate_limiting.py`
- Environment needs: repo-harness

### T-28 — `add_simulators_to_step`/`remove_simulators_from_step` rate-limit gate

- Description: Same gate-order proof for both simulator-selection tools.
- Status: Active
- Passes after: Phase 6
- Level: integration
- Execution: Automatic
- Risk: Same as T-25, for these two tools.
- Risk source: CLAUDE.md rate-limiting convention
- Verify: Same pattern as T-25.
- Expected: Same call-order guarantee for both.
- Evidence required: CI run (butler job + build #).
- Automation lives in: `safebreach_mcp_studio/tests/test_rate_limiting.py`
- Environment needs: repo-harness

### T-29 — `save_scenario` rate-limit gate, including the failure path

- Description: Proves the gate's most important edge case — `record_action` must never fire on a failed save.
- Status: Active
- Passes after: Phase 7
- Level: integration
- Execution: Automatic
- Risk: Recording success on a failed API call would silently under-count and let a caller exceed real usage
  without the limiter noticing.
- Risk source: CLAUDE.md rate-limiting gate placement rule 4
- Verify: (a) mock a successful POST, assert full call order incl. `record_action`; (b) mock a 500 response,
  assert `record_action` is never called.
- Expected: (a) `check_limit`→`api_call`→`record_action`; (b) `check_limit`→`api_call`, no `record_action`.
- Evidence required: CI run (butler job + build #).
- Automation lives in: `safebreach_mcp_studio/tests/test_rate_limiting.py`
- Environment needs: repo-harness

### T-30 — `save_scenario` full body assembly

- Description: Proves the entire draft→wire-body pipeline (not just the `type`/`propagateDefinition` piece
  covered in T-22) produces exactly the shape the real API expects, for a realistically populated draft.
- Status: Active
- Passes after: Phase 7
- Level: integration
- Execution: Automatic
- Aspect: API-contract
- Risk: A subtly wrong body shape would fail against the real API in a way unit tests of individual pieces
  wouldn't catch.
- Risk source: PRD Component E
- Verify: Build a draft via `create_scenario`→`add_step`→`add_attacks_to_step`→`add_simulators_to_step` calls
  (in-process, no HTTP); mock `requests.post`; call `save_scenario`; inspect the exact posted JSON body.
- Expected: The body matches `{name, steps: [{name, attacksFilter, attackerFilter, targetFilter}], type:
  "validate", propagateDefinition: null}` with the accumulated step/attack/simulator data intact.
- Evidence required: CI run (butler job + build #).
- Automation lives in: `safebreach_mcp_studio/tests/test_studio_functions.py`
- Environment needs: repo-harness

### T-31 — pre-save gate blocks on a blocking verdict

- Description: Proves `save_scenario` actually enforces DoD6's "checked before persisting" requirement rather
  than merely documenting it.
- Status: Active
- Passes after: Phase 7
- Level: integration
- Execution: Automatic
- Risk: A missing/bypassable pre-save check would let a scenario with a fully-blocked attack (including an
  ALM-tagged one) save successfully, directly regressing DoD3/DoD6.
- Risk source: PRD Component E/F, §7 DoD6
- Verify: Mock `sb_get_plan_statistics` (called directly — see Requirements Traceability R11 note) to return a
  response with a fully-blocked attack (`moves[id] === 0`); call `save_scenario`.
- Expected: `save_scenario` raises a clear "blocked" error; no `requests.post`/`requests.put` call is made.
- Evidence required: CI run (butler job + build #).
- Automation lives in: `safebreach_mcp_studio/tests/test_studio_functions.py`
- Environment needs: repo-harness

### T-32 — DB unique-constraint handling

- Description: Proves a name collision produces a legible error instead of a raw Sequelize stack trace
  reaching the caller.
- Status: Active
- Passes after: Phase 7
- Level: integration
- Execution: Automatic
- Risk: A raw passthrough error would be confusing to Helm and, transitively, to the end user.
- Risk source: PRD Component E, `context.md` §6.13 (F15)
- Verify: Mock `requests.post` to return the 4xx shape a `(name, accountId)` unique-constraint violation
  produces; call `save_scenario`.
- Expected: A clear, typed "name already in use" error; the draft is NOT evicted (work isn't lost to a
  transient/fixable error).
- Evidence required: CI run (butler job + build #).
- Automation lives in: `safebreach_mcp_studio/tests/test_studio_functions.py`
- Environment needs: repo-harness

### T-33 — `get_playbook_attacks` end-to-end filter pipeline

- Description: Proves the new filters work through the real fetch→transform→filter pipeline, not just the
  isolated filter function tested in T-17.
- Status: Active
- Passes after: Phase 4
- Level: integration
- Execution: Automatic
- Risk: T-17 alone wouldn't catch a wiring bug between the KB fetch, the reduced-attack transform, and the
  filter call.
- Risk source: PRD Component D
- Verify: Mock the `{base_url}/api/kb/vLatest/moves?details=true` response with realistic nested tag data
  (`[{id, name, values}]` shape); call `sb_get_playbook_attacks` with each new filter.
- Expected: Filtered results match what T-17 predicts for the same data, proving the pipeline threads raw tags
  through correctly end-to-end.
- Evidence required: CI run (butler job + build #).
- Automation lives in: `safebreach_mcp_playbook/tests/test_playbook_functions.py`
- Environment needs: repo-harness

### T-39 — draft eviction on save

- Description: Proves a successful save cleans up its draft, and a failed one preserves it so the user's work
  isn't lost to a transient error.
- Status: Active
- Passes after: Phase 7
- Level: integration
- Execution: Automatic
- Risk: Evicting on failure would silently discard a user's in-progress build over a fixable/transient error;
  never evicting would leak cache entries.
- Risk source: PRD Component A/E
- Verify: (a) mock a successful save, inspect `scenario_draft_cache` afterward; (b) mock a failed save
  (500), inspect the cache afterward.
- Expected: (a) the `draft_id` entry is gone; (b) the `draft_id` entry is still present, unchanged.
- Evidence required: CI run (butler job + build #).
- Automation lives in: `safebreach_mcp_studio/tests/test_studio_functions.py`
- Environment needs: repo-harness

### T-34 — `list_simulators` against a real console

- Description: Proves the tool's proxy to `get_console_simulators`' logic actually returns real, correctly
  shaped simulator metadata from a live console — not just that it calls the right function.
- Status: Active
- Passes after: Phase 5
- Level: system
- Execution: Automatic
- Risk: A shape mismatch between what `list_simulators` returns and what `get_console_simulators` actually
  produces would only surface against a real API response.
- Risk source: PRD Component C
- Verify: Against a real minimal console with a handful of registered (mockulator) simulators of varied
  connected/OS attributes, call `list_simulators` with each supported filter.
- Expected: Results match `get_console_simulators`' own contract for the same console/filters; filters narrow
  correctly.
- Evidence required: CI run (butler job + build #) against the provisioned console environment.
- Automation lives in: `planned: safebreach_mcp_studio/tests/test_e2e_scenario_build.py`
- Environment needs: console environment (Validate, minimal)

### T-35 — a single `save_scenario` POST against a real console

- Description: Proves the actual `config/v3/plans` write succeeds and produces server-side `type='validate'`
  against a real, unmocked API — the first production caller of this surface (Risk R6).
- Status: Active
- Passes after: Phase 7
- Level: system
- Execution: Automatic
- Risk: `config/v3/plans` has no other production caller anywhere in the codebase; an untested edge case here
  is more likely than on the console-verified `v2` surface.
- Risk source: PRD §9 R6
- Verify: Build a minimal one-step draft; call `save_scenario` against a real minimal console; issue a raw
  `GET config/v3/plans/{id}` afterward.
- Expected: `save_scenario` returns a real `scenario_id`; the raw GET confirms `type: "validate"` and
  `propagateDefinition: null` server-side.
- Evidence required: CI run (butler job + build #) against the provisioned console environment.
- Automation lives in: `planned: safebreach_mcp_studio/tests/test_e2e_scenario_build.py`
- Environment needs: console environment (Validate, minimal)

### T-36 — full build-through-save e2e workflow

- Description: The single most important test in this plan — proves the whole conversational build actually
  produces a correct, saved, ready-to-run scenario, end to end, the way Helm would really use these tools.
  Satisfies R1 (DoD1) and the mandatory E2E requirement.
- Status: Active
- Passes after: Phase 7
- Level: e2e
- Execution: Automatic
- Risk: Any of the 24 unit tests could individually pass while the tools still fail to compose correctly in
  sequence against a real environment — this is the only test that proves composition.
- Risk source: PRD §7 DoD1
- Verify: Against a real minimal console with a handful of registered simulators and the default seeded
  playbook: `create_scenario` → `add_step` (themed name) → `add_attacks_to_step` (explicit ids) →
  `add_simulators_to_step` (attacker + target roles) → `save_scenario`. Read the saved plan back via a raw
  GET on `config/v3/plans/{id}`.
- Expected: The saved plan's `steps[0].attacksFilter.playbook.values`, `.attackerFilter.simulators.values`,
  `.targetFilter.simulators.values`, and top-level `type`/`propagateDefinition` all match what was built,
  exactly.
- Evidence required: CI run (butler job + build #) against the provisioned console environment.
- Automation lives in: `planned: safebreach_mcp_studio/tests/test_e2e_scenario_build.py`
- Environment needs: console environment (Validate, minimal)

### T-37 — AI-executed progression walkthrough

- Description: Sign-off evidence that a scenario built entirely through these MCP tools is indistinguishable,
  when inspected in the console's own Studio UI, from one a human would have built there directly. This is the
  plan's mandatory progression test.
- Status: Active
- Passes after: Final
- Level: e2e
- Execution: Manual
- Aspect: progression
- Risk: T-36 proves the API-level result is correct; it does not prove the result is *sensible* to a human
  reviewing it in the console — e.g. a step whose name or attack grouping is technically valid JSON but reads
  oddly in the UI.
- Risk source: PRD §7 DoD1, ticket Goal ("saved, ready to run")
- Manual because: judging whether the built scenario "reads coherently" in the console UI is a qualitative
  review, not a single deterministic assertion — the deterministic half of this workflow is already covered
  by T-36.
- Verify: An AI agent, using only the new MCP tools (no direct API calls), builds a small multi-step scenario
  as Helm would in a real conversation, saves it, then opens the resulting scenario in the console's Studio UI
  and reviews step names, attack groupings, and simulator assignments for coherence.
- Expected: The scenario opens without error in Studio; step names are themed (not "Step 1"/"Step 2"); attacks
  and simulators appear exactly as built; nothing about the scenario reads as obviously MCP-generated versus
  human-built.
- Evidence required: Transcript/command log of the tool calls made, plus a screenshot of the resulting
  scenario in Studio, with an observed-vs-expected note.
- Environment needs: console environment (Validate, minimal)

## Tests by Phase (readiness view)

| After phase | Newly green | Cumulative green |
|-------------|-------------|-------------------|
| Phase 1 | T-1, T-2, T-25 | T-1, T-2, T-25 |
| Phase 2 | T-3–T-8, T-26 | + T-3–T-8, T-26 |
| Phase 3 | T-9–T-16, T-27 | + T-9–T-16, T-27 |
| Phase 4 | T-17, T-18, T-33 | + T-17, T-18, T-33 |
| Phase 5 | T-34 | + T-34 |
| Phase 6 | T-19–T-21, T-28 | + T-19–T-21, T-28 |
| Phase 7 | T-22, T-24, T-29, T-30, T-31, T-32, T-35, T-36, T-39 | + T-22, T-24, T-29, T-30, T-31, T-32, T-35, T-36, T-39 |
| Final | T-23, T-38, T-37 | all |

## Sign-off

- [ ] Requirements traceability complete — every R# covered or explicitly out-of-scope
- [ ] Change Coverage complete — every changed file tested or justified
- [ ] Regression complete — existing `automation` UI suite named as regression evidence (see Risk Landscape);
  post-ship CI builds named
- [ ] Progression evidence — T-37 (Manual, progression)
- [ ] validating-test-plan: RESULT: clean
- [ ] All tests green (cumulative through Final) — evidence: test-results/<phase-or-date>.md
- [ ] Accepted gaps listed and approved: none

## Change Log

| Date | Change |
|------|--------|
| 2026-09-03 06:20 | Test plan created from PRD v1 |
| 2026-09-03 07:05 | Reviewed and approved by Boris Berezovsky (planning-dev-task Phase 8) |
