# Ticket Context: SAF-35508

## Status
Phase 9: Complete — JIRA description overwritten + audit comment 205027 posted

## Mode
Improving

## Original Ticket
- **Key**: SAF-35508 — https://safebreach.atlassian.net/browse/SAF-35508
- **Type**: Subtask of SAF-34615 (Story: "MCP support for Validate scenario creation and update (Stage 1)")
- **Summary**: MCP support for Core plan statistics API: ad-hoc plan impact, per-attack/simulator counts, and constraints
- **Status**: To Do
- **Priority**: Medium
- **Labels**: CTEM-dev
- **Reporter / Assignee**: Boris Berezovsky (both)
- **Created / Updated**: 2026-08-25

### Description (as written)
Implements functional requirements 6 and 7 of SAF-34615.

Central claim: `POST /orch/v1/accounts/{accountId}/plan/statistics` is the orchestrator's
impact-and-validation engine behind every simulation-count and conflict number the
console shows. Requirement 6 makes it the single source of truth for Helm too —
MCP must never estimate these independently.

Console wrapper: `getPlanStatistics(plan, limit, includeDisabled, getConstraints, abortable)`
at `ui-react/src/actions/execution.tsx:615`.

Capability surface named in the ticket:
- **Input** is an ad-hoc `ValidatePlan` body, *not* an id. No saved plan required; no Studio
  call site sends a `planId`. Matters most for Helm, which re-scores a configuration while
  building it, long before `save_scenario` exists.
- Per-step scoping via `attacksFilter`, `attackerFilter`/`targetFilter` (`simulatorsFilter`),
  `systemFilter`, `successCriteria`, and `draft: true` for Studio draft custom attacks.
- **Query params**: `limit` (console uses 500000 / `PLAN_SIMULATIONS_STATISTICS_LIMIT`),
  `includeDisabled`, `getConstraints` + `getAllConstraints` (console sets both together),
  `useCache`.
- **Response per step** (`StepStatistics`): `simulationCount`, `moves` (attack id → sim count,
  `0` = runs nowhere), `simulators`/`attackerSimulators`/`targetSimulators` (simulator id →
  attack count, `0` = does nothing), `simulatorConstraints.{attacker,target}Constraints[simulatorId][moveId]`,
  `isLimitReached`.

Console consumers cited as evidence of the real behavior MCP must match:
Add Simulators Checkout tab (`SimulatorsModal.tsx:68`, `includeDisabled=true`, `getConstraints=true`);
Add Simulators Select tab (`SimulatorsModal.tsx:198`); Studio per-step stats
(`StudioStatsManager.tsx:55`); run gating (`RunTestModal.tsx:268`, `sagas/methods.ts:174` →
`runDisabled()` at `planUtils.ts:520`, blocks when any step has `simulationCount === 0`);
Quick Run single-step estimate (`QuickRunModal/index.tsx:148,174`); attack detail modal
(`BreachDetailModal.tsx:356`); Test Summary PDF (`TestSummaryOverviewPdf.tsx:72`).

Scope for this sub-task:
1. An MCP tool over this endpoint accepting an ad-hoc plan body (and, as a convenience,
   resolving a saved `scenario_id` into one), passing through the parameters above, returning
   per-step counts plus a structured, untranslated conflict list. No narrative fields — Helm
   interprets (req 13). *Note: supersedes SAF-34615 req 13, which specifies `scenario_id` input only.*
2. This call is the **only** impact/conflict path in the MCP layer. Re-checks after a changed
   decision reuse it rather than a separate estimation.
3. Plain-language translation (req 7): every conflict type maps to an explanation of its effect
   on the current selection plus one concrete suggested fix as a yes/no. Raw reasons
   ("Role is incompatible") must never reach the user.
4. Hard-failure handling — the only two cases in this story: an attack that runs on no selected
   simulator (`moves[id] === 0`) and a simulator with zero attacks (`*Simulators[id] === 0`).
   Tell the user they are inapplicable and remove them; no swap offer; save is not blocked.

Out of scope: partial-impact and fail-rate conflicts, and swap-or-proceed choices
(SAF-35484, Story 2).

To resolve during implementation:
- `simulatorConstraints`, `moves`, and the simulator maps are untyped
  (`{[key: string]: unknown}`) in the generated schema. Enumerate the constraint-reason
  vocabulary from live responses to build a stable conflict-type enum and translation table.
- Decide the `includeDisabled` contract. Checkout tab uses `true` (disconnected simulators
  counted); run-gating uses `false`. "Expected vs runnable" likely maps onto this flag — confirm
  whether runnable needs a second call or a client-side derivation.
- Consider exposing `runDisabled`-equivalent feasibility (any step with `simulationCount === 0`)
  so Helm can tell the user a scenario is unrunnable for the same reason the console greys out Run.

### Acceptance Criteria (as written)
1. The tool evaluates an ad-hoc plan body with no saved scenario, and also accepts a `scenario_id`.
2. It surfaces per-step `simulationCount`, per-attack `moves` counts, per-simulator counts, and
   structured constraints, and passes through `limit` / `includeDisabled` / `getConstraints` / `useCache`.
3. Numbers match the console's Checkout and Requirements Status views for the same configuration.
4. No estimation path exists in the MCP layer outside `plan/statistics`.
5. Every conflict type has a plain-language translation with a suggested fix; no raw reason string
   reaches the user.
6. An attack with `moves[id] === 0` is auto-removed with an explanation, without blocking save.
7. A simulator with zero associated attacks is auto-removed the same way.
8. Any change to an earlier decision triggers a fresh call to the same endpoint.

Covers SAF-34615 Definition of Done items 2, 5, and 6.

## Task Scope
Preparation focus agreed with the user (all four):
1. **Resolve the open questions** — answer the three "To resolve during implementation" items
   from code: the constraint-reason vocabulary/enum, the `includeDisabled` contract
   (expected vs runnable), and whether to expose `runDisabled`-equivalent feasibility.
2. **Map the MCP-side landing spot** — which MCP server/package the tool belongs in, its
   naming/parameter conventions, and how `scenario_id` → plan-body resolution would work.
3. **Scope boundary check** — verify the split against SAF-35484 (Story 2) and parent
   SAF-34615 req 13; confirm the supersede note and that nothing falls between the tickets.
4. **Ground the ACs in code** — verify every AC is implementable and unambiguous against the
   actual endpoint and existing MCP tool patterns; tighten wording where vague.

## Repositories Under Investigation
- `/Users/bariber/projects/core/safebreach-mcp` — **primary** (implementation target, PRD home).
  Python MCP server; packages: `safebreach_mcp_core`, `safebreach_mcp_config`,
  `safebreach_mcp_data`, `safebreach_mcp_playbook`, `safebreach_mcp_studio`, `safebreach_mcp_utilities`.
- `/Users/bariber/projects/core/orchestrator` — read-only. Owns
  `POST /orch/v1/accounts/{accountId}/plan/statistics`; source for the real response shape and
  the constraint-reason vocabulary.

Explicitly **not** investigated this round (user's choice): `ui-react` (console call sites are
already enumerated in the ticket), `mcp-proxy`.

## Branch & PRD Location
- Branch: `feature/SAF-35508-plan-statistics-mcp-tool` (base `origin/main` @ 1b6f63f)
- Worktree: `/Users/bariber/projects/core/safebreach-mcp/.claude/worktrees/feature+SAF-35508-plan-statistics-mcp-tool`
- PRD folder: `prds/feature-SAF-35508-plan-statistics-mcp-tool/`

## Investigation Findings

### orchestrator — the endpoint itself

Route contract (`src/server/other/swagger.json`, path
`/orch/v1/accounts/{accountId}/plan/statistics`, `operationId: getPlanStatistics`,
tag `statistics`, `x-postman-folder: Attack/Scenarios`):

| Query param | Type | Swagger default | Console value (per ticket) |
|---|---|---|---|
| `includeDisabled` | boolean | `false` | `true` (Checkout), `false` (run gating) |
| `useCache` | boolean | `true` | — |
| `limit` | integer | `0` | `500000` |
| `getConstraints` | boolean | `false` | `true` |
| `getAllConstraints` | boolean | `false` | `true` (set together with `getConstraints`) |

Request body is `ValidatePlan`; the only **required** field is `name`. It also carries
`id`, `planId`, `testId`, `steps[]`, `draft`, `successCriteria`, `flowControl`, `tags`, etc.
Response is `{ data: PlanStatistics }` where `PlanStatistics = { steps: StepStatistics[] }`.
`StepStatistics` requires `simulationCount`, `moves`, `simulators`, `targetSimulators`,
`attackerSimulators`; optional `isLimitReached`, `simulatorConstraints`. The four maps are
declared bare `"type": "object"` with no `properties` — the ticket's "untyped in the
generated schema" claim is confirmed at the source.

Controller: `src/server/controllers/plan_statistics.js` → `PlanStatistics.getPlanStatistics`.

**F1 — The endpoint already resolves a saved plan by id (controller:51-53).**
```js
if (metaPlan.id || metaPlan.testId) { planToPrepare = await this.planPreparation.getPlanById(metaPlan); }
else { planToPrepare = metaPlan; }
```
Both the ad-hoc body and the by-id form are native to the endpoint. AC-1's "also accepts a
`scenario_id`" therefore needs no MCP-side resolution step — it can be a passthrough of
`{id: <scenario_id>}`. Note the check is `id || testId`; **`planId` is present in the schema
but is NOT used for resolution**. A plan with no `steps` is rejected with HTTP 400
`NOT_ALLOWED` ("Can not get statistics for plans with no steps").

**F2 — `includeDisabled` is the inverse of the intuitive reading (controller:65-66).**
```js
const nodesForCalculations = includeDisabled ? configurationNodes : configurationNodes.filter((n) => n.isEnabled);
const offlineNodes         = includeDisabled ? [] : configurationNodes.filter((n) => !n.isEnabled);
```
- `includeDisabled=true` → disabled simulators **count toward the numbers**, and `offlineNodes`
  is empty, so **no `simulator_is_offline` constraint is ever emitted**. This is the
  "expected" number.
- `includeDisabled=false` → disabled simulators are excluded from the counts **but are still
  reported**: `matrix_statistics.js:29-38` walks `offlineNodes` and adds
  `{reason: 'simulator_is_offline'}` for every (move, node) pair on both attacker and target
  sides. This is the "runnable" number *plus* the explanation for the gap.

Consequence for the open question: **expected and runnable cannot come from one call.**
`includeDisabled=false` is the strictly more informative single call (runnable counts +
the offline reason); a second call with `true` is required if the expected number is also
wanted. Client-side derivation of expected from the `false` response is not possible — the
disabled simulators are filtered out of the counts entirely. Note `node.isEnabled` is derived
(`isConnected && approved`), so "disabled" covers unapproved simulators too, not just
disconnected ones.

**F3 — The constraint structure, exactly (`src/server/other/StatisticsAggregator.js`).**
```
simulatorConstraints = {
  attackerConstraints: { [simulatorNodeId]: { [moveId]: [ {reason, values?}, ... ] } },
  targetConstraints:   { [simulatorNodeId]: { [moveId]: [ {reason, values?}, ... ] } },
}
```
The ticket's `[simulatorId][moveId]` ordering is **correct** (`addConstraintBySimulator(moveId,
nodeId, type, c)` writes `simulatorsConstraint[type][nodeId][moveId]`). Two details the ticket
does not state:
- The leaf is an **array**, not a scalar — a (simulator, move) pair can carry several reasons.
  Entries are deduped by `reason`; when a duplicate arrives and both sides have `values`, the
  `values` arrays are concatenated.
- `removeEmptySimulatorConstraints()` prunes empty leaves and then any simulator whose every
  move came back empty. So **absence is meaningful**: a missing simulator key means "no
  constraints at all", not "not evaluated". Consumers must not assume the map is dense.
- `simulatorConstraints` is only populated when `getConstraints` is truthy; otherwise
  `addConstraintByGroup` is a no-op and the key is absent.

**F4 — `getAllConstraints` changes completeness, not grouping (`sbGenerator/validators/job_validator.js:178-186`).**
```js
const filteredNodes = JobValidator.ValidationClasses[i][filterMethod](move, nodesToFilter, settings, statisticsAggregator);
resultNodes.nodes = resultNodes.nodes.filter((node) => filteredNodes.includes(node));
if (!settings.getAllConstraints) { nodesToFilter = filteredNodes; }
```
- `false` → validators run as a **chain**; each sees only survivors of the previous one, so a
  simulator records **only the first reason** that eliminated it.
- `true` → every validator runs against the **full** node set, so a simulator accumulates
  **every** reason it fails.

The swagger description ("Param to group constraints by") is wrong/stale — it is a
completeness flag with a cost, not a grouping key. `getAllConstraints=true` also enables two
extra constraint emitters (`countBothSideUnderlyingSimulations`, `sameNodeOnBothSideConstraint`
at `job_validator.js:91-92`). For AC-5 (every conflict explained) `getAllConstraints=true` is
the right setting; it is what the console already uses.

**F5 — The counting maps, and what `0` means (`job_validator.js:58-77`).**
```js
attackerNodes.forEach((n) => { result.attackerSimulators[n.id] = 0; result.simulators[n.id] = 0; });
targetNodes.forEach((n)   => { result.targetSimulators[n.id]   = 0; result.simulators[n.id] = 0; });
moves.forEach((m)         => { result.moves[m.id] = 0; });
```
Every in-scope move and node is pre-seeded to `0`, so `=== 0` is a sound predicate for
AC-6/AC-7 — a `0` genuinely means "in scope, runs nowhere". Two caveats:
- `simulators` is the **union** of attacker and target nodes and is incremented from both
  sides. AC-7 ("a simulator with zero associated attacks") must read `simulators[id] === 0`.
  Reading `targetSimulators[id]`/`attackerSimulators[id]` is wrong: a node that appears on only
  one side is **`undefined`** in the other map, not `0`.
- `moves` is keyed by `move.id` at seed time but incremented via
  `result.moves[move.originalMoveId] += …` — the rendered-move to original-move mapping matters
  if MCP ever needs to correlate back to rendered variants.

**F6 — `isLimitReached` truncates the response and poisons the maps with `null` (controller:74-88).**
When the circuit breaker fires, the controller pushes a sentinel step and **returns immediately**:
```js
stepStatistics.push({ isLimitReached: true, simulationCount: null,
  moves: moves.reduce((acc, m) => { acc[m.id] = null; return acc; }, {}),
  targetSimulators: {}, attackerSimulators: {}, simulators: {}, simulatorConstraints: {} });
return { steps: stepStatistics };
```
So on limit-reached: `steps.length` is **shorter than the plan's step count**, `simulationCount`
is `null`, and **every** `moves[id]` is `null`. `null` means "not computed", which is
categorically different from `0` ("runs nowhere"). Any AC-6/AC-7 auto-removal that treats
falsy as zero would silently delete the user's entire attack list on a large scenario.
The breaker is driven by `renderedMoves.length` against
`STATISTICS_STEP_LIMIT_PERCENT` (default 0.5) and `STATISTICS_STEP_LIMIT_AFTER_CIRCUIT_BREAK_PERCENT`
(default 0.01) of `limit`; `limit=0` (the swagger default) disables it entirely, while the
console's `500000` enables it.

**F7 — A third code path exists for single-simulation re-runs (controller:107-120).**
When a step carries `systemFilter.simulations.values`, `ConstraintManager.setStepConstraint`
turns those simulation ids into `step.constraints`, and statistics are computed **per
constraint** and merged by `ConstraintManager.mergeStatistics`. This is the "can this single
simulation be re-run" capability the ticket mentions. `getConstraintNodeFilter` throws
`SafeBreachOperationNotSupported` when the simulators filter operator is not `is` — a real
error surface for a passthrough tool.

**F8 — The reason vocabulary is finite, enumerable from source, and has 88 members.**
`src/server/sbGenerator/validators/constraints.js` is a static dictionary of reason codes
grouped by validator (21 groups: proxy, framework, mail-server type, general, OS, package,
move-state, domain, simulation-user, mail, advanced-actions, license, AWS, Bedrock, Azure, GCP,
web-application, pre-execution, port-in-use, customize-parameter, asset). Codes are
machine-readable `snake_case` (`incompatible_os`, `simulator_is_offline`,
`move_requires_credentials_but_the_simulator_is_missing_credentials`), **not** the
console-style prose the parent story used as its example ("Role is incompatible"). The
ticket's "enumerate the vocabulary from live responses" step can be replaced by reading this
file — a complete, static enum, no live sampling required. `validation_type.js` adds the
orthogonal outcome enum `valid | invalid_constraint | unable_to_validate`.

### safebreach-mcp — the landing spot

**F9 — This is not greenfield: a private helper already calls the endpoint.**
`safebreach_mcp_studio/studio_functions.py:2400` — `_get_scenario_statistics(steps, console,
include_constraints=False, verbose_failures=False)`:
```python
constraint_params = "&getConstraints=true&getAllConstraints=true" if include_constraints else ""
api_url = (f"{base_url}/api/orch/v1/accounts/{account_id}"
           f"/plan/statistics?limit=500000&includeDisabled=true{constraint_params}")
payload = {"name": "", "steps": steps}
```
It is **not registered as an MCP tool** — it is an internal pre-flight used by exactly two
callers, both in the same module:
- `sb_quick_run` (line 2737), `include_constraints=evaluate`
- `sb_run_scenario` (line 2958), `include_constraints=evaluate`, `verbose_failures=…`

Both surface the result only through their `evaluate=True` preview branch
(`status: 'evaluating'`, `predicted_simulations`, `predicted_per_step`, `step_stats`,
`empty_steps`). So the work of SAF-35508 is largely **promoting and generalizing an existing
private helper into a first-class tool**, not writing a new integration.

Observations on the existing helper, each of which maps to an AC:
- It already posts an **ad-hoc body** (`{"name": "", "steps": steps}`) with no saved plan —
  AC-1's harder half already works, and `name: ""` is what satisfies `ValidatePlan.required: [name]`.
- It **hardcodes** `limit=500000` and `includeDisabled=true`, and ties `getConstraints`/
  `getAllConstraints` to a single `include_constraints` boolean. `useCache` is never sent
  (so the server default `true` applies). AC-2's passthrough requirement is unmet today.
- Per F2, the hardcoded `includeDisabled=true` means these previews report **expected**, not
  **runnable**, counts and can never emit `simulator_is_offline` — a disconnected simulator is
  silently counted as if it would run. This is the most user-visible defect the new tool fixes.
- It reduces the response to counts (`matchedAttacks`, `totalAttacks`, …) and **discards**
  `isLimitReached` and the raw per-simulator maps. AC-2 wants these surfaced.
- Per F6, it is **not null-safe**: `sum(1 for v in moves.values() if v > 0)` and
  `sorted(moves.items(), key=lambda x: -x[1])` both raise `TypeError` on the `null` values a
  limit-reached response returns.
- `sb_run_scenario` already resolves `scenario_id` → `scenario['steps']` before calling, so a
  scenario-id path exists in the codebase (though F1 shows the endpoint can do it natively).

**F10 — A translation table already exists but covers 14 of 88 codes (16%).**
`studio_functions.py:2225` — `CONSTRAINT_REASON_DESCRIPTIONS`, a dict of
`code → {description, fixable}`, consumed by `_summarize_constraints` (2299, per-attack
breakdown) and `_summarize_constraints_aggregated` (2350, grouped by reason code).

Measured against `constraints.js`: **88 distinct codes exist, 14 are translated, 74 are not.**
Every translated code is a real one (no dead entries). Untranslated codes include the entire
Azure, GCP, Bedrock and web-application families, all the `move_requires_X_but_the_simulator_is_missing_X`
pairs, the licence and asset validators, and — notably — **`simulator_is_offline` itself**,
which is the single most likely reason a user will hit.

Two concrete AC-5 gaps in the existing implementation:
- The lookup falls back to the **raw code**:
  `CONSTRAINT_REASON_DESCRIPTIONS.get(code, {}).get('description', code)` (line 2333). For 74
  of 88 codes an untranslated `snake_case` string reaches the user today, which is exactly what
  AC-5 forbids. A safe default (and a test that asserts total coverage) is needed, not just
  more entries.
- The table has `description` + `fixable`, but **no suggested fix**. AC-5 requires "one concrete
  suggested fix as a yes/no"; `fixable: True/False` is a boolean, not a suggestion. The schema
  needs a third field.

**F11 — Tool registration convention.** `safebreach_mcp_studio/studio_server.py` registers 12
tools via `@self.mcp.tool(name=…, annotations=ToolAnnotations(readOnlyHint=…, destructiveHint=…),
description=…)`, delegating to `sb_*` functions in `studio_functions.py`. Wire names are
snake_case without the `sb_` prefix (`quick_run`, `run_scenario`, `manage_test`). A statistics
tool is read-only (`readOnlyHint=True, destructiveHint=False`), unlike every existing
run-oriented tool in this server. `prds/mcp-semantics-quick-run-evaluate.md` records the
naming precedent: wire names track platform vocabulary, and the preview concept is called
**"evaluate"** — relevant when naming this tool against the parent's `checkout_scenario`.

**F12 — AC-4 ("no estimation path outside `plan/statistics`") already holds.** A repo-wide
search for independent counting/estimation (`statistics`, `simulationCount`, `estimat`) finds
only: this helper, and `safebreach_mcp_data`'s `simulations_statistics`, which is a
*post-execution* result-status count from test summaries (`data_types.py:200`), not a
pre-execution prediction. AC-4 is therefore a **regression guard**, not new work.

### Scope boundary (parent SAF-34615 and sibling SAF-35484)

- Parent **req 6** (the orchestrator API is the single source of truth, no independent estimation) →
  SAF-35508 scope items 1-2, AC-2/AC-4. ✔
- Parent **req 7** (translate conflicts, plain language + suggested fix, hard-failure-only for
  this story) → SAF-35508 scope items 3-4, AC-5/AC-6/AC-7. ✔ The parent's own example reason
  ("Role is incompatible") does not exist in that form; the closest real code is
  `incompatible_package`, whose existing MCP description is *"Simulator role mismatch"* (F10).
- Parent **req 12** (re-check after any change) → AC-8. ✔
- Parent **DoD 2, 5, 6** → the subtask's closing claim is accurate. ✔
- Parent **Future scope** explicitly defers partial-impact / fail-rate conflicts with a
  swap-or-proceed choice, plus automatic simulator shortlisting and filter-based selection, to
  **SAF-35484 (Story 2)**. The subtask's out-of-scope line matches the parent verbatim. ✔
  (`SAF-35485` is Story 3: step placement on edit, OOB-vs-custom, rename/delete.)

**Gap G1 — the tool has no name.** Parent req 13 names it `checkout_scenario`; SAF-35508
supersedes that entry's *input* contract but never states the wire name. Helm's tool contract
and every other subtask in the story depend on it, so it should be pinned here.

**Gap G2 — "runnable count" is in the parent contract but absent from these ACs.** Parent
req 13 specifies `checkout_scenario` output as "per step, the expected simulation count,
**runnable count**, and a structured conflict list". SAF-35508's AC-2 lists `simulationCount`,
`moves`, per-simulator counts and constraints — but no distinct runnable figure, and the
"To resolve" section leaves it open. Per F2 this is a real design decision with a cost (two
HTTP calls), so it belongs in an AC rather than in "to resolve".

**Gap G3 — AC-3 is ambiguous about which console view.** It requires numbers to match "the
console's Checkout and Requirements Status views", but per F2 those two views use *different*
`includeDisabled` values (Checkout `true`, run gating `false`) and therefore legitimately show
different numbers. The AC needs to say which call parameters correspond to which view.

**Gap G4 — `isLimitReached` has no AC.** It is named in the description's response section but
no AC covers it, and per F6 mishandling it causes AC-6/AC-7 to destroy a user's configuration.

## Problem Analysis

### Problem statement

Helm needs to answer one question repeatedly while a user builds a Validate scenario in conversation:
*"given the configuration as it stands right now, what will actually run, and what will not — and why?"*

The orchestrator already answers it. `POST /orch/v1/accounts/{accountId}/plan/statistics` scores any plan body and returns
per-step simulation counts, per-attack and per-simulator counts, and per-(simulator, attack) constraint reasons.
The console has used it for years for its Checkout tab, Studio step stats, run gating, Quick Run and the Test
Summary PDF.

The MCP layer reaches that endpoint today, but only through a keyhole. `_get_scenario_statistics`
(`studio_functions.py:2400`) is a private pre-flight helper that two run-oriented tools call in their
`evaluate=True` preview branch. It hardcodes its query parameters, reduces the response to summary counts,
and is unreachable as a capability in its own right. Helm cannot ask "score this configuration" — it can only
ask "pretend to run this scenario and tell me what you would have run".

So the problem is not *integration*. It is that the existing integration is **private, hardcoded, lossy, and
in three specific ways incorrect**. Those four properties, not the absence of an API call, are what block the
parent story.

### The four defects, and why each matters

**1. Private — the capability does not exist as a contract.**
The parent story (req 13) specifies a discrete tool whose output Helm sequences and interprets. Today the only
way to obtain impact data is to invoke a tool whose declared purpose is to *run a test*, and which will queue a
real test if the caller passes `evaluate=False`. Every re-check after a changed decision (AC-8, parent req 12)
routes through a destructive-hinted tool. There is no read-only impact primitive.

**2. Hardcoded — the parameters that carry the meaning are fixed.**
`limit=500000` and `includeDisabled=true` are baked into the URL; `getConstraints`/`getAllConstraints` are tied
to one boolean; `useCache` is never sent. AC-2 requires these to be pass-through, but the deeper issue is that
`includeDisabled` is not a tuning knob — per F2 it *selects which question is being asked*. Fixing it at `true`
permanently asks for the expected number and never the runnable one.

**3. Lossy — the response is reduced before anyone can use it.**
The helper returns `matchedAttacks` / `totalAttacks`-style aggregates and discards the raw `moves`,
`simulators`, `attackerSimulators`, `targetSimulators` maps and the `isLimitReached` flag. AC-6 and AC-7 are
defined in terms of *individual* zero-valued entries in those maps, so the data those criteria operate on is
thrown away before it reaches a caller.

**4. Incorrect — three defects that are live today.**
- *Disconnected simulators are counted as if they would run.* Because `includeDisabled=true` also suppresses
  `offlineNodes` (F2), the current previews report a number that includes simulators that cannot execute, and
  they can never emit `simulator_is_offline` to explain it. A user is told a test will produce N simulations
  when the runnable figure is lower.
- *74 of 88 constraint reasons reach the user as raw `snake_case`.* The fallback at `:2333` returns the code
  itself when the table misses. This is the precise failure mode parent req 7 and AC-5 exist to prevent, and it
  already happens for 84% of the vocabulary — including `simulator_is_offline`.
- *Limit-reached responses crash the helper.* `v > 0` and `-x[1]` over `None` raise `TypeError` (F6).

### Affected areas

| Area | What is touched | Nature |
|---|---|---|
| `safebreach_mcp_studio/studio_functions.py` | `_get_scenario_statistics` (:2400), `CONSTRAINT_REASON_DESCRIPTIONS` (:2225), `_summarize_constraints` (:2299), `_summarize_constraints_aggregated` (:2350) | Generalize + extend |
| `safebreach_mcp_studio/studio_server.py` | New read-only tool registration alongside the existing 12 | Add |
| `safebreach_mcp_studio/studio_functions.py` | `sb_quick_run` (:2737), `sb_run_scenario` (:2958) — the two existing callers | Regression surface |
| `safebreach_mcp_studio/studio_types.py`, `studio_templates.py` | Response typing / rendering for the new tool | Likely add |
| `safebreach_mcp_studio/tests` | Coverage for the new tool + the translation-completeness guard | Add |
| `CLAUDE.md` | Tool catalog and rate-limiting gate table (precedent: `prds/mcp-semantics-quick-run-evaluate.md`) | Update |
| `orchestrator` | **None** — read-only reference. No server change is required or intended. | — |

### Risks

- **R1 — Silent destruction of user configuration.** AC-6/AC-7 auto-remove attacks and simulators. The
  discriminator is `=== 0`. A limit-reached response makes every `moves[id]` `null` and truncates the step list
  (F6). Any implementation that treats falsy as zero, or that assumes `len(steps)` matches the plan, will
  remove everything the user selected and report it as a normal outcome. This is the highest-severity risk in
  the ticket and currently has no acceptance criterion.
- **R2 — Regressing the two existing callers.** `sb_quick_run` and `sb_run_scenario` depend on the helper's
  present shape and on `includeDisabled=true`. Changing the default to `false` changes the numbers those tools
  report, which is arguably a *fix* (R4) but is a visible behavioral change to shipped tools.
- **R3 — Translation table drift.** The vocabulary lives in an orchestrator source file on a different release
  cadence and in a different repository. A code added there appears in MCP responses with no translation, and
  the current fallback leaks it verbatim. Coverage is a point-in-time property unless something enforces it.
- **R4 — "Matches the console" is not one number.** Checkout uses `includeDisabled=true`, run gating uses
  `false`. AC-3 as written can be satisfied against one view and violated against the other.
- **R5 — Cost of correctness.** `getAllConstraints=true` disables the validator short-circuit so every
  validator runs against the full node set (F4), and obtaining both expected and runnable needs two round trips
  (F2). Full fidelity is measurably more expensive than the current single cached call, against an endpoint the
  helper already gives a 120-second timeout.
- **R6 — Auto-removal without a written-back scenario.** AC-6/AC-7 say the affected entities are removed. For
  an ad-hoc body there is nothing to remove them *from* — the caller holds the configuration. Whether this tool
  mutates anything, or only reports what should be removed, is unresolved and determines whether it is
  read-only.

### Edge cases

- `limit=0` (the swagger default) disables the circuit breaker entirely; the console's `500000` enables it.
  Which default the tool adopts decides whether R1 is reachable at all.
- A plan with no `steps` returns HTTP 400 `NOT_ALLOWED`, not an empty result — a normal state while Helm is
  still building.
- `ValidatePlan` requires `name`; the existing helper satisfies this with `""` for ad-hoc bodies.
- `simulatorConstraints` is pruned (F3): a simulator with no constraints is **absent**, not present-and-empty.
  The map is sparse and must not be iterated as if dense.
- A simulator present on only one side is `undefined` in the other role map, never `0` (F5).
- The constraint leaf is an **array** — one (simulator, attack) pair can carry several reasons, and with
  `getAllConstraints=true` it usually will.
- `moves` is seeded by `move.id` but incremented by `move.originalMoveId` (F5).
- Steps carrying `systemFilter.simulations.values` take the per-constraint merge path (F7), which throws
  `SafeBreachOperationNotSupported` when the simulators filter operator is not `is`.
- Both `id` and `testId` trigger by-id resolution; `planId` is in the schema but is **not** honoured (F1).
- `node.isEnabled` is `isConnected && approved`, so `includeDisabled` also governs *unapproved* simulators, not
  only disconnected ones — `simulator_is_offline` is a slightly misleading name for what it covers.

### Dependencies and open decisions

- **D1 — The tool's wire name (G1).** Parent req 13 called it `checkout_scenario`; this subtask supersedes that
  entry's input contract but names nothing. Sibling subtasks and Helm's prompt both depend on it.
- **D2 — Expected vs runnable (G2).** Parent req 13 requires both figures. F2 proves that costs two calls.
  Whether the tool makes both, or exposes the choice and returns one, is a contract decision, not an
  implementation detail.
- **D3 — Read-only or mutating (R6).** Determines the `ToolAnnotations` and whether AC-6/AC-7 belong to this
  subtask at all or to whichever tool owns scenario state.
- **D4 — Translation completeness (G-AC5).** 74 codes need entries, each needing a suggested fix, and the
  raw-code fallback needs replacing with a safe generic default plus a test that fails when coverage regresses.
- **D5 — Upstream vocabulary.** `constraints.js` lives in `orchestrator`, which is not a dependency of
  `safebreach-mcp`. The 88 codes must be vendored, and R3 makes the refresh path a real question.
- **D6 — Backward compatibility for the two existing callers (R2).**

## Proposed Improvements
(Phase 6)

---

# Planning Round (planning-dev-task)

## Status
Phase 7: Review — DoD gate re-run after the AC-9/AC-10 reword

## Phase 1 — JIRA re-fetch (2026-08-26)

Confirmed the improved description authored by the earlier `preparing-ticket` round is **live** on
SAF-35508: the "Current state in the MCP layer" section, the resolved `includeDisabled` /
`getAllConstraints` / vocabulary sections, the `isLimitReached` trap, and the **12 acceptance
criteria** are all present. Labels are now `CTEM-dev`, `sigi_ee_reminder`.

Board state applied this round:
- **Status**: `To Do` → **In Progress** (transition id 21).
- **Sprint**: **not applicable.** JIRA rejected the edit —
  `"Issue 'SAF-35508' is a subtask and subtasks cannot be associated to a sprint. It's associated to
  the same sprint as its parent."` The active sprint is **Saf sprint 96** (id 1184, board 159,
  2026-08-18 → 2026-09-01, field `customfield_10122`). Sprint membership is therefore governed by
  parent **SAF-34615**, which was left untouched — changing a Story's sprint affects every sibling
  subtask and was not in scope for this run.

## Phase 2 — Decisions taken by the user (this round)

These close D1, D2 and D3 from the previous round's open-decision list.

| # | Decision | Chosen | Consequence |
|---|---|---|---|
| **D1** | Tool wire name | **`get_plan_statistics`** | Mirrors the orchestrator's endpoint (`getPlanStatistics`) and the console wrapper exactly. Most discoverable against the API. Supersedes both the parent's `checkout_scenario` (req 13) and the previous round's `evaluate_plan` recommendation. AC-12's "confirmed wire name" is now satisfied. |
| **D2** | Expected vs runnable | **Runnable default, flag exposed** | `includeDisabled=false` is the default (strictly more informative — it is the only setting that emits `simulator_is_offline`). The flag is a pass-through parameter. A second call is issued **only** when both figures are explicitly requested, and each result is labelled. Matches AC-3 as written. |
| **D3** | Read-only or mutating | **Read-only: the tool reports, it does not act** → ACs 9/10 **reworded**, not deferred | The tool reports raw + translated statistics plus a zero-impact summary. It shapes no plan body, so it is unambiguously `readOnlyHint=True`. On review the user's framing — *"statistics should return a summary of what's going to run and what not"* — showed the ticket's "auto-removed" wording was the error, not the design: removal is an action on the plan body, which the caller holds. **SAF-35508 ACs 9/10 were reworded to "reported" on 2026-08-26 rather than accepted as gaps — see "Resolution" below.** |
| **D4** | Vendoring the vocabulary | **Vendor as a static table + coverage test** (carried over; recommendation accepted implicitly, no competing option) | The 88 codes are copied into `safebreach-mcp` with a test that fails when coverage regresses. |

### Resolution of D3 — the ticket was reworded, not narrowed (2026-08-26)

The Phase 7 DoD gate flagged TI-9 and TI-10 as gaps. Presented with them, the user asked *"what does
it mean remove? statistics should return a summary of what's going to run and what not"* — which
identified the real problem: the ACs described an **action on the plan body**, while the tool being
specified is a **statistics call**. The wording was wrong, not the design.

Applied to SAF-35508 (single `editJiraIssue`, description replaced):
- **AC-9 / AC-10** → the zero-impact attack / simulator is **reported** as inapplicable with a
  plain-language explanation; reporting never blocks save, and `null` is never reported as
  zero-impact.
- **AC-5** aligned — "performs no zero-impact reporting" replaces "performs no auto-removal".
- **AC-12** now states the rate-limiting gate table is **not** extended (read-only tools are outside
  that contract).
- **Scope item 4** → "Hard-failure **reporting**", stating that *acting* on the report belongs to the
  caller holding the configuration (Helm, or a future scenario-editing tool).
- **Out-of-scope line** now names plan-body mutation explicitly.
- **"Decisions to confirm"** → **"Decisions taken (2026-08-26)"**, recording D1–D4.
- The constraint-vocabulary section gained the by-value vendoring trap (F14).

Net effect: **all 12 ACs are covered by the PRD**; no DoD gap is accepted. No `## Accepted DoD Gaps`
section is therefore needed.

Parent-story consequence, still open: SAF-34615 **req 7**'s *acting* half (removing an entity from a
configuration) is owned by no Stage 1 subtask. Parent **DoD items 2 and 5** are covered; **item 6** is
covered only to the extent that surfacing rather than removing satisfies it. Per the user's decision
this is **recorded in the PRD and deferred** — not tracked as a follow-up ticket yet. Options remain
(a) a new SAF-34615 subtask, or (b) fold into SAF-35484 (Story 2).

## Phase 4 — Additional investigation (this round)

Verification of every line reference the previous round recorded, plus four new findings.

### Verified unchanged
All previous line references are still exact:
`CONSTRAINT_REASON_DESCRIPTIONS` :2225 · `_summarize_constraints` :2299 ·
`_summarize_constraints_aggregated` :2350 · `_get_scenario_statistics` :2400 ·
`sb_quick_run` :2690 (calls at :2737) · `sb_run_scenario` :2864 (calls at :2958).
`studio_server.py` registers 12 tools; wire names confirmed as
`validate_studio_code`, `save_studio_attack_draft`, `get_all_studio_attacks`,
`update_studio_attack_draft`, `get_studio_attack_source`, `run_studio_attack`,
`get_studio_attack_latest_result`, `create_new_studio_attack`, `set_studio_attack_status`,
`run_scenario`, `quick_run`, `manage_test`.

### F13 — CORRECTION to F11: this would **not** be the server's first read-only tool
The previous round claimed a statistics tool "would be the server's first `readOnlyHint=True` entry".
That is **wrong**. `studio_server.py` already registers four read-only tools:
`validate_studio_code` (:53), `get_all_studio_attacks` (:281), `get_studio_attack_source` (:461),
`get_studio_attack_latest_result` (:630). `get_plan_statistics` follows an established in-server
pattern rather than introducing one. No PRD risk attaches to the annotation choice.

### F14 — The 88-code count is confirmed, but it is 88 **values**, not 88 keys
Measured directly against `orchestrator/src/server/sbGenerator/validators/constraints.js`
(21 exported groups, 89 total key entries):

* **87 distinct keys**
* **88 distinct values** ← this is what actually appears in a response's `reason` field
* Two entries whose **value differs from their key**, which is the trap:
  * `advancedActionValidator.some_cloned_advanced_actions_are_disabled` → emits
    **`some_duplicate_advanced_actions_are_disabled`**
  * `webApplicationValidator.move_does_not_require_location_simulator_location_is_ignored` → emits
    **`move_does_not_require_url_simulator_url_is_ignored`**

**Implication for D4:** the vendored table must be keyed on the **values**, not the keys. A
key-derived vendoring would ship two codes that can never occur while missing the two that do, and
the coverage test would still pass — a silently wrong 88/88.

Two values are also shared across groups (`incompatible_framework_version` appears in both
`moveFrameworkConstraintValidator` and `mailSimulationValidator`), so a code cannot be assumed to
belong to exactly one validator group.

### F15 — Coverage measured exactly: 14 / 88, 74 missing, 0 dead
Programmatic diff of `CONSTRAINT_REASON_DESCRIPTIONS` against the 88 values:
`MCP entries: 14 · covered: 14 · MISSING: 74 · DEAD (in MCP but not in orchestrator): none`.
The previous round's 14/88/74 figures are confirmed precisely, and no entry needs deleting.

### F16 — The regression surface is far larger than R2 assumed: 58 test references
`_get_scenario_statistics` is referenced **58 times** in
`safebreach_mcp_studio/tests/test_studio_functions.py`, plus once in `test_e2e_run_scenario.py:350`.
The majority are `@patch('...studio_functions._get_scenario_statistics', return_value=[...])`
decorators carrying **hardcoded return dicts** in the helper's current summary shape
(`simulationCount`, `matchedTargetSimulators`, `matchedAttackerSimulators`, `matchedAttacks`,
`totalTargetSimulators`, `totalAttackerSimulators`, `totalAttacks`).

Direct-behaviour tests live at :6212-:6293 (`TestGetScenarioStatistics`).

**Implication for the architecture.** Changing the *return shape* of `_get_scenario_statistics`
would force edits to ~20+ patch decorators across a 10 228-line test file — a large, purely
mechanical diff with real risk of masking a genuine regression. The safe design is therefore:

> introduce a **new low-level function** that performs the HTTP call and returns the *raw*
> per-step response (null-safe, parameters fully exposed), and **refactor
> `_get_scenario_statistics` into a thin summariser on top of it**, preserving its existing return
> contract byte-for-byte.

This satisfies AC-6 (one and only one path to `plan/statistics`) without touching the two existing
callers' observable behaviour or the 58 test references. It also isolates the `includeDisabled`
correction: the new tool defaults to `false` (runnable) per D2, while `_get_scenario_statistics`
keeps passing `true` explicitly, so `quick_run` / `run_scenario` previews are unchanged by default
and their correction becomes a separate, deliberate decision rather than a side effect.

### F17 — Confirmed null-unsafety and the discarded union map, in situ
Reading `_get_scenario_statistics` (:2446-:2492) confirms both defects at the exact expressions:
* `sum(1 for v in target_sims.values() if v > 0)`, the same for `attacker_sims` and `moves`, and
  `sorted(moves.items(), key=lambda x: -x[1])` — every one raises `TypeError` on the `None` values a
  limit-reached response returns.
* It reads `targetSimulators` and `attackerSimulators` only. The **union `simulators` map is never
  read at all**, so the map AC-10 was defined against is not merely discarded downstream — it is
  never extracted from the response.
* `isLimitReached` is never read.
* `s.get('simulationCount', 0)` defaults a missing count to `0`, collapsing "absent" into
  "runs nowhere" — the same `null`/`0` conflation R1 warns about, already present.

### F18 — Conventions for the new code
* **Cache**: `SafeBreachCache` from `safebreach_mcp_core.safebreach_cache`; the studio server's only
  instance today is `studio_draft_cache = SafeBreachCache(name="studio_drafts", maxsize=5, ttl=1800)`
  (`studio_functions.py:41`). Per-user cache keys use `get_cache_user_suffix()` from
  `safebreach_mcp_core.token_context`.
* **Auth / URL**: `get_api_base_url(console, 'orchestrator')`, `get_api_account_id(console)`,
  `get_auth_headers_for_console(console)`, `check_rbac_response(response)`, `timeout=120`.
* **Tests**: `safebreach_mcp_studio/tests/` — `test_studio_functions.py` (unit, 10 228 lines),
  `test_e2e*.py` (e2e, `@pytest.mark.e2e`), `test_rate_limiting.py`. A read-only tool needs **no**
  rate-limiting gates (`readOnlyHint=True` ⇒ outside the `check_limit`/`record_action` contract).


---

## Accepted Ticket-Compliance Gaps

Recorded by `verifying-ticket-compliance` on 2026-09-03, at HEAD `1e93f1c`. Each entry names the item, why it
is not met as the ticket literally words it, and where the superseding decision is documented. An entry here
is a decision, not an oversight — and none of them is a claim that the work happened.

### TI-4 — "Numbers match the console for the same configuration, per view and per parameter set"

**Date**: 2026-09-03 · **Status**: unverified, accepted

**Justification**: T-35 is the only test in the plan that compares the tools' numbers against what the console
itself renders, and it has never run: no Validate console has been provisioned for this feature
(`env-design.md` is still `Draft (awaiting review)` with the console choice recorded as the one genuinely
blocking decision, and no `environment.md` exists). The six e2e tests are authored and collect cleanly but are
in the same position.

This gap is **load-bearing and must not be read as minor**. Every other criterion on this ticket is verified
by tests that compare the implementation against itself or against a mocked transport — they establish
**self-consistency, not correctness**. TI-4 is the only item that would establish that the numbers are right.
Accepting it means the feature ships verified internally and unverified against the product.

**To close it**: provision a Validate console, then run T-35 and the e2e suite (T-28…T-31, T-40, T-48).

### TI-1 (mechanism only) — "`scenario_id` passed through to Core as `{id}` rather than resolved client-side"

**Date**: 2026-09-03 · **Status**: superseded by observed API behaviour

**Justification**: The substance is met — both an ad-hoc body and a saved `scenario_id` are accepted, and a
step-less plan raises a typed error. The **mechanism** in the AC is not achievable: probing the orchestrator
directly showed `{"id": 1}` and `{"id": "1"}` accepted, `{"id": "<uuid>"}` rejected with `/id must be
integer`, and `{"testId": "<uuid>"}` rejected as not a test. An OOB scenario's UUID has **no field on the
endpoint that accepts it**, so the tool resolves it to its steps and scores them as an ad-hoc body; an integer
plan id is still passed through natively. Documented in `prd.md` §13 (2026-08-27) and verified live on
`zircon-piculet`. The AC was written from the swagger, before the endpoint was probed.

### TI-7 (lever half) and TI-8 (null-lever clause) — "All 88 emitted reason codes carry a `fix_lever`"

**Date**: 2026-09-03 · **Status**: superseded by decision, recorded in PRD v5

**Justification**: The deletion half is met — `CONSTRAINT_REASON_DESCRIPTIONS` is gone and no constraint
meaning is vendored. The **lever map was deliberately not built**. The AC assumed SAF-35568 would serve
`description` *and* `fixLever`; it implemented `fixLever`, reviewed it, and **removed it as redundant relative
to `description`**. A lever map here would then be a permanently MCP-owned artifact with no upstream
counterpart, drifting against 97 codes forever, asserting a remedy from an enum never validated against the
orchestrator's own `ValidatePlan` fields — and re-adopting a design its own author rejected. The repo now
asserts the **absence** of any lever symbol (`test_no_constraint_fix_levers_symbol`). Recorded in `prd.md` §2
(alternatives table), §3 Component A, §9 R7, and the v5 change-log entry.

### TI-12 (wire name) — "The tool is registered as `get_plan_statistics`"

**Date**: 2026-09-03 · **Status**: superseded by decision D4

**Justification**: Every substantive clause is met — read-only registration, CLAUDE.md catalogue entry, and
the rate-limiting gate table deliberately unextended. Only the **count and the names** differ: the single tool
was decomposed into `get_scenario_simulation_counts`, `get_scenario_blocked_entities` and
`get_scenario_attack_blockers`, and `get_plan_statistics` was retired. This was a user decision taken on
2026-09-02 (D4) on the grounds that one tool answering three questions forced the caller to read past two of
them. `sb_get_plan_statistics` survives as the shared plumbing, so AC-6's single-call-site guarantee is
untouched. Recorded in `prd.md` §2 (Revision), §3 Component E, §8 Phases 7–9, and the v7 change-log entry.
