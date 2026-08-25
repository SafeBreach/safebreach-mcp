# Ticket Summary: SAF-35508

## Overview

**Mode**: Improving existing
**Project**: SAF — Subtask of SAF-34615 (Story: MCP support for Validate scenario creation and update, Stage 1)
**Repositories**: `safebreach-mcp` (implementation), `orchestrator` (read-only reference)

---

## Current State

**Summary**: MCP support for Core plan statistics API: ad-hoc plan impact, per-attack/simulator counts, and constraints

The ticket is already unusually well-specified: it names the endpoint, the console wrapper, seven console call
sites, the full capability surface, 8 acceptance criteria, and three explicit "to resolve" items.

**What the investigation changed:**

1. **It reads as greenfield; it is not.** The description does not mention `_get_scenario_statistics`
   (`studio_functions.py:2400`), which already calls this endpoint, nor `CONSTRAINT_REASON_DESCRIPTIONS`
   (`:2225`), which is already a partial translation table. Anyone picking this up would rediscover both, and
   might build a second path alongside them — the exact outcome AC-4 forbids.
2. **All three "to resolve" items are answerable from source now**, and one of the three answers inverts the
   assumption written into the ticket.
3. **Four gaps** exist between these acceptance criteria and the parent story's contract.
4. **One unguarded correctness trap** can silently delete a user's whole configuration.

---

## Investigation Summary

### orchestrator (read-only)

- **`src/server/controllers/plan_statistics.js`** — the controller. Natively resolves a saved plan when the body
  carries `id` **or** `testId` (`:51-53`); `planId` is in the schema but is **not** honoured. A body with no
  `steps` returns HTTP 400 `NOT_ALLOWED`.
- **`includeDisabled` is inverted from the intuitive reading** (`:65-66`). `true` counts disabled simulators
  **and sets `offlineNodes = []`**, so `simulator_is_offline` is never emitted. `false` excludes them from the
  counts **but reports each one** with that reason (`matrix_statistics.js:29-38`). Expected and runnable cannot
  come from one call, and expected cannot be derived from the `false` response.
- **`isLimitReached` truncates and nullifies** (`:74-88`). The controller pushes a sentinel step with
  `simulationCount: null` and every `moves[id] = null`, then **returns early** — so `steps` is shorter than the
  plan's step count. Driven by `renderedMoves.length` vs `STATISTICS_STEP_LIMIT_PERCENT` (0.5) and
  `STATISTICS_STEP_LIMIT_AFTER_CIRCUIT_BREAK_PERCENT` (0.01) of `limit`; `limit=0` disables it.
- **`src/server/other/StatisticsAggregator.js`** — constraint shape is
  `simulatorConstraints[attacker|targetConstraints][simulatorId][moveId] = [{reason, values?}, …]`. The ticket's
  index order is correct. Two undocumented details: the leaf is an **array** (deduped by `reason`), and
  `removeEmptySimulatorConstraints()` prunes empties, so the map is **sparse** — an absent simulator means "no
  constraints", not "not evaluated".
- **`sbGenerator/validators/job_validator.js:178-186`** — `getAllConstraints` is a **completeness** flag, not a
  grouping key (its swagger description is wrong). `false` chains validators so a simulator records only the
  *first* reason; `true` runs every validator against the full node set so it records *all* of them.
- **`job_validator.js:58-77`** — every in-scope move and node is pre-seeded to `0`, so `=== 0` is sound.
  `simulators` is the attacker∪target **union**; a node on only one side is `undefined` in the other role map,
  never `0`.
- **`sbGenerator/validators/constraints.js`** — the reason vocabulary is a **static dictionary of 88 codes**
  across 21 validator groups. No live sampling is needed to enumerate it. Codes are machine-readable
  `snake_case`, not the console prose the parent story used as its example.
- **`ConstraintManager.js`** — a third path exists for single-simulation re-runs, via
  `systemFilter.simulations.values`; it throws `SafeBreachOperationNotSupported` when the simulators filter
  operator is not `is`.

### safebreach-mcp (implementation target)

- **`studio_functions.py:2400` — `_get_scenario_statistics`** already posts an ad-hoc body
  (`{"name": "", "steps": steps}`) to the endpoint. It is **not registered as a tool**; its only callers are
  `sb_quick_run` (`:2737`) and `sb_run_scenario` (`:2958`), both only in their `evaluate=True` preview branch.
  It hardcodes `limit=500000` and `includeDisabled=true`, ties `getConstraints`/`getAllConstraints` to one
  boolean, never sends `useCache`, discards `isLimitReached` and the raw maps, and raises `TypeError` on a
  limit-reached response (`v > 0` and `-x[1]` over `None`).
- **`studio_functions.py:2225` — `CONSTRAINT_REASON_DESCRIPTIONS`** covers **14 of the 88 codes (16%)**.
  All 14 are real; **74 are untranslated**, including `simulator_is_offline` and the whole Azure, GCP, Bedrock
  and web-application families. The lookup falls back to the **raw code** (`:2333`), so an untranslated
  `snake_case` string reaches the user today for 84% of the vocabulary. The entries carry `description` and
  `fixable` (a boolean) but **no suggested fix**.
- **`studio_server.py`** registers 12 tools via `@self.mcp.tool(name=…, annotations=ToolAnnotations(…),
  description=…)`. Wire names are snake_case without the `sb_` prefix. A statistics tool would be the server's
  first `readOnlyHint=True` entry.
- **AC-4 already holds.** The only other `statistics` in the repo is `safebreach_mcp_data`'s
  `simulations_statistics`, a *post-execution* status count from test summaries. AC-4 is a regression guard.

---

## Problem Analysis

### Problem Description

Helm must repeatedly answer, mid-conversation, *"given the configuration as it stands, what will run, what will
not, and why?"* Core already answers this, and MCP already reaches the endpoint — but only through a private
pre-flight helper inside two run-oriented tools. The capability is therefore **private, hardcoded, lossy, and
in three specific ways incorrect**. Those four properties, not a missing integration, are what block the parent
story.

- **Private** — the only route to impact data is a tool declared as *running a test*, which queues a real one
  at `evaluate=False`. Every re-check after a changed decision (AC-8, parent req 12) goes through a
  destructive-hinted tool. There is no read-only impact primitive, which is what parent req 13 specifies.
- **Hardcoded** — `includeDisabled` is not a tuning knob; per the inversion above it *selects which question is
  being asked*. Fixed at `true`, the tool permanently asks for expected and never for runnable.
- **Lossy** — the raw `moves` / `simulators` maps and `isLimitReached` are discarded before returning, yet
  AC-6/AC-7 are defined in terms of individual zero-valued entries in exactly those maps.
- **Incorrect** — disconnected simulators are counted as runnable with no way to explain it; 74 of 88 reasons
  leak raw; limit-reached responses crash.

### Impact Assessment

| Area | Effect |
|---|---|
| Helm / parent story | Cannot obtain a read-only impact check; blocks parent DoD 2, 5, 6 |
| `sb_quick_run`, `sb_run_scenario` | Their `evaluate=True` previews overstate runnable counts today |
| End users | For 84% of constraint reasons, see a raw `snake_case` code instead of an explanation |
| Large scenarios | Limit-reached responses raise `TypeError` in the current helper |

### Risks & Edge Cases

- **R1 (highest) — silent destruction of user configuration.** AC-6/AC-7 auto-remove on `=== 0`. A
  limit-reached response makes every `moves[id]` `null` *and* truncates the step list. Treating falsy as zero,
  or assuming `len(steps)` matches the plan, removes everything the user selected and reports it as normal.
  **No acceptance criterion currently guards this.**
- **R2** — the two existing callers depend on the helper's present shape and on `includeDisabled=true`;
  correcting it changes numbers shipped tools already report.
- **R3** — the vocabulary lives in a different repo on a different release cadence; coverage is a point-in-time
  property unless a test enforces it.
- **R4** — "matches the console" is not one number: Checkout uses `includeDisabled=true`, run gating `false`.
- **R5** — correctness costs more: `getAllConstraints=true` disables the validator short-circuit, and expected
  + runnable needs two round trips, against an endpoint already given a 120-second timeout.
- **R6** — AC-6/AC-7 say entities are "removed", but for an ad-hoc body there is nothing to remove them *from*;
  the caller holds the configuration. This decides whether the tool is read-only.
- Edge cases: `limit=0` disables the breaker; no-steps returns 400; `ValidatePlan` requires `name`; the
  constraint map is sparse; role maps return `undefined` not `0`; the constraint leaf is an array; `moves` is
  seeded by `move.id` but incremented by `originalMoveId`; `node.isEnabled` is `isConnected && approved`, so
  `simulator_is_offline` also covers *unapproved* simulators.

---

## Proposed Ticket Content

### Summary (Title)

Unchanged — it is accurate and specific:

> MCP support for Core plan statistics API: ad-hoc plan impact, per-attack/simulator counts, and constraints

### Recommended changes

1. **Replace the "To resolve during implementation" section** with the resolved answers. All three are settled.
2. **Add a "Current state in the MCP layer" section** so the existing helper and translation table are not
   rediscovered or duplicated.
3. **Expand 8 acceptance criteria to 12**, covering the four gaps: tool name, expected-vs-runnable,
   `isLimitReached`, and per-view parameter mapping for AC-3.
4. **Record the open decisions** that are genuinely contract-level (tool name, read-only vs mutating).

### Open decisions requiring a call before implementation

| # | Decision | Recommendation |
|---|---|---|
| D1 | Wire name. Parent req 13 said `checkout_scenario`, but the input is no longer scenario-only. | `evaluate_plan` — matches the repo's established "evaluate" preview vocabulary (`prds/mcp-semantics-quick-run-evaluate.md`) and does not imply a saved scenario. |
| D2 | Expected *and* runnable (parent req 13 wants both) costs two calls. | Default to **runnable** (`includeDisabled=false`) — strictly more informative, since it also yields `simulator_is_offline`. Expose the flag; make the second call only when both are asked for. |
| D3 | Read-only or mutating (R6). | **Read-only.** Report what should be removed; let whichever tool owns scenario state perform it. Keeps `readOnlyHint=True` and keeps AC-8 re-checks off a destructive tool. |
| D4 | Vendoring the 88 codes from a non-dependency repo (R3, D5). | Vendor as a static table, guarded by a test that fails on missing coverage. |

---

## Proposed Ticket Content (Markdown for JIRA)

**Description:**

```markdown
Implements functional requirements 6 and 7 of SAF-34615.

### The API

`POST /orch/v1/accounts/{accountId}/plan/statistics` is the Core impact-and-validation engine behind every
simulation-count and conflict number the console shows. Requirement 6 makes it the single source of truth for
Helm too: MCP must never estimate these independently.

Console wrapper: `getPlanStatistics(plan, limit, includeDisabled, getConstraints, abortable)` -
`ui-react/src/actions/execution.tsx:615`.
Core controller: `orchestrator/src/server/controllers/plan_statistics.js`.

### Current state in the MCP layer

**This is not a new integration.** `_get_scenario_statistics` (`safebreach_mcp_studio/studio_functions.py:2400`)
already posts an ad-hoc plan body to this endpoint. It is a private pre-flight helper, not a registered tool,
and its only callers are `sb_quick_run` (:2737) and `sb_run_scenario` (:2958), both only in their
`evaluate=True` preview branch.

A partial translation table also exists: `CONSTRAINT_REASON_DESCRIPTIONS` (`studio_functions.py:2225`),
consumed by `_summarize_constraints` (:2299) and `_summarize_constraints_aggregated` (:2350).

The work is therefore to **promote and generalize the existing helper into a first-class tool**, fixing four
properties that block the parent story:

* **Private** - the only route to impact data is a tool declared as running a test, which queues a real one at
  `evaluate=False`. Every re-check after a changed decision routes through a destructive-hinted tool.
* **Hardcoded** - `limit=500000` and `includeDisabled=true` are baked into the URL; `getConstraints` and
  `getAllConstraints` are tied to one boolean; `useCache` is never sent.
* **Lossy** - the raw `moves` and simulator maps and `isLimitReached` are discarded, yet the hard-failure rules
  below are defined in terms of individual zero-valued entries in exactly those maps.
* **Incorrect** - three live defects: disconnected simulators are counted as runnable with no way to explain
  it; 74 of 88 constraint reasons reach the user as raw `snake_case`; limit-reached responses raise
  `TypeError`.

### Capability surface to expose

**Input - an ad-hoc plan, not an id.** The endpoint scores any `ValidatePlan` body posted to it. This is the
capability that matters most for Helm, which evaluates a configuration repeatedly while building it, long
before `save_scenario` exists. The only required body field is `name`.

The endpoint **natively** resolves a saved plan when the body carries `id` or `testId`
(`plan_statistics.js:51-53`), so `scenario_id` support is a passthrough, not a client-side resolution step.
Note `planId` appears in the `ValidatePlan` schema but is **not** honoured. A body with no `steps` returns
HTTP 400 `NOT_ALLOWED`.

Each step can be scoped by:

* `attacksFilter` - methodIds, playbook, attackType, attackPhase, nistControl, protocol, ports, tags,
  parameters, publishedDate/modifiedDate, latestKnownAttacks, origin
* `attackerFilter` / `targetFilter` (`simulatorsFilter`) - simulators, os, osVersion, deployments, connection,
  role, sbRelease, internalIp/externalIP, dataAssets, advancedActions, impersonatedUser
* `systemFilter`, `successCriteria`, and `draft: true` for Studio draft custom attacks

### Query parameters

Swagger defaults, and what each one actually controls:

* `limit` - default `0`, which disables the circuit breaker entirely. The console uses 500000. Compared against
  the rendered-move count, not the simulation count.
* `includeDisabled` - default `false`. Selects expected vs runnable; see below.
* `getConstraints` - default `false`. Populates `simulatorConstraints`; without it the key is absent entirely.
* `getAllConstraints` - default `false`. A completeness flag, not a grouping key; see below.
* `useCache` - default `true`.

<!-- Rendered as a bullet list, not a table: the JIRA markdown-to-ADF converter drops tables. Verified against
     the live description's ADF (no `table` node is produced). -->


### Response - per step (`StepStatistics`)

* `simulationCount` - expected simulations
* `moves` - attack id to simulation count; `0` means that attack runs nowhere in the current selection
* `simulators` / `attackerSimulators` / `targetSimulators` - simulator id to attack count; `0` means that
  simulator does nothing. `simulators` is the attacker-union-target set; a node present on only one side is
  **`undefined`** in the other role map, never `0`.
* `simulatorConstraints.{attacker,target}Constraints[simulatorId][moveId]` - an **array** of `{reason, values?}`
  objects, deduped by reason. The map is **sparse**: `removeEmptySimulatorConstraints()` prunes empty leaves and
  then any simulator with no constraints at all, so an absent simulator means "no constraints", not "not
  evaluated".
* `isLimitReached` - see the hard-failure section; this flag is load-bearing.

### Resolved: the constraint-reason vocabulary

No live sampling is required. `orchestrator/src/server/sbGenerator/validators/constraints.js` is a **static
dictionary of 88 distinct reason codes** across 21 validator groups (proxy, framework, mail-server type,
general, OS, package, move-state, domain, simulation-user, mail, advanced-actions, licence, AWS, Bedrock,
Azure, GCP, web-application, pre-execution, port-in-use, customize-parameter, asset). Codes are machine-readable
`snake_case` (`incompatible_os`, `simulator_is_offline`), not the console prose SAF-34615 used as its example -
the closest real code to "Role is incompatible" is `incompatible_package`.

`CONSTRAINT_REASON_DESCRIPTIONS` currently covers **14 of 88 (16%)**. The remaining **74 are untranslated**,
including `simulator_is_offline` itself and the entire Azure, GCP, Bedrock and web-application families. The
lookup falls back to the raw code (`studio_functions.py:2333`), so untranslated reasons reach the user today.

`validation_type.js` adds an orthogonal outcome enum: `valid | invalid_constraint | unable_to_validate`.

### Resolved: `getAllConstraints` is a completeness flag

Despite its swagger description ("Param to group constraints by"), `getAllConstraints` does not group anything
(`job_validator.js:178-186`):

* `false` - validators run as a chain, each seeing only the previous one's survivors, so a simulator records
  **only the first reason** that eliminated it.
* `true` - every validator runs against the full node set, so a simulator accumulates **every** reason it
  fails, and two extra emitters are enabled (`job_validator.js:91-92`).

Full explanation coverage therefore requires `getAllConstraints=true`, which is what the console already uses -
at the cost of losing the short-circuit.

### Resolved: `includeDisabled` is the inverse of the intuitive reading

`plan_statistics.js:65-66`:

* `includeDisabled=true` - disabled simulators **count toward the numbers**, and `offlineNodes` is set to
  empty, so **`simulator_is_offline` is never emitted**. This is the **expected** number.
* `includeDisabled=false` - disabled simulators are excluded from the counts **but are still reported**:
  `matrix_statistics.js:29-38` adds `{reason: 'simulator_is_offline'}` for every (move, node) pair on both
  sides. This is the **runnable** number plus the explanation for the gap.

Consequence: **expected and runnable cannot come from one call**, and expected cannot be derived client-side
from the `false` response - the disabled simulators are filtered out of the counts entirely.
`includeDisabled=false` is the strictly more informative single call.

Note `node.isEnabled` is `isConnected && approved`, so this flag also governs **unapproved** simulators, not
only disconnected ones.

### Hard failures, and the `isLimitReached` trap

The two hard-failure cases in this story are an attack that runs on no selected simulator (`moves[id] === 0`)
and a simulator with zero attacks (`simulators[id] === 0`, the union map). Every in-scope move and node is
pre-seeded to `0` (`job_validator.js:58-77`), so `=== 0` is a sound predicate.

**But `0` and `null` are not the same.** When the circuit breaker fires, the controller pushes a sentinel step
and **returns early** (`plan_statistics.js:74-88`):

* `steps` is **shorter than the plan's step count**
* `simulationCount` is `null`
* **every** `moves[id]` is `null`

`null` means "not computed", not "runs nowhere". Auto-removal that treats falsy as zero, or that assumes the
returned step count matches the plan, will silently delete the user's entire attack and simulator selection and
report it as a normal result. The existing helper already crashes on this path.

### Scope for this sub-task

1. A read-only MCP tool over this endpoint that accepts an ad-hoc plan body (and passes a saved `scenario_id`
   through as `{id}`), passes through the query parameters above, and returns per-step counts plus a
   structured, untranslated conflict list. No narrative fields - Helm interprets (req 13). _Note: this
   supersedes SAF-34615 req 13, which specifies input `scenario_id` only._
2. This call is the only impact/conflict path in the MCP layer. Re-checks after a changed decision reuse it
   rather than a separate estimation. The existing `_get_scenario_statistics` callers are migrated onto it, not
   left as a parallel path.
3. Plain-language translation (req 7): every one of the 88 conflict types maps to an explanation of its effect
   on the current selection plus one concrete suggested fix as a yes/no. Raw reason codes must never reach the
   user, including for codes added upstream after this ticket.
4. Hard-failure handling, the only two cases in this story - an attack that runs on no selected simulator
   (`moves[id] === 0`) and a simulator with zero attacks (`simulators[id] === 0`). Tell the user they are
   inapplicable and remove them; no swap offer; save is not blocked. Never act on `null`.

Out of scope: partial-impact and fail-rate conflicts and swap-or-proceed choices (SAF-35484, Story 2).

### Decisions to confirm before implementation

* **Tool wire name.** SAF-34615 req 13 called it `checkout_scenario`, but the input is no longer scenario-only.
  Proposed: `evaluate_plan`, matching the repo's established "evaluate" preview vocabulary.
* **Expected vs runnable.** Req 13 asks for both figures; per the above that costs two calls. Proposed: default
  to runnable (`includeDisabled=false`), expose the flag, and make the second call only when both are requested.
* **Read-only vs mutating.** Criteria 8 and 9 say the affected entities are "removed", but for an ad-hoc plan
  body there is nothing to remove them from - the caller holds the configuration. Proposed: this tool reports
  what should be removed and stays read-only; whichever tool owns scenario state performs the removal.
* **Vendoring the vocabulary.** `constraints.js` lives in `orchestrator`, which is not a dependency of
  `safebreach-mcp`. The 88 codes must be copied in, with a test that fails when coverage regresses.

### Also worth knowing

A third code path exists for single-simulation re-runs: when a step carries `systemFilter.simulations.values`,
statistics are computed per constraint and merged (`ConstraintManager.mergeStatistics`).
`getConstraintNodeFilter` throws `SafeBreachOperationNotSupported` when the simulators filter operator is not
`is`.

Covers SAF-34615 Definition of Done items 2, 5, and 6.
```

**Acceptance Criteria:**

```markdown
1. The tool evaluates an ad-hoc plan body with no saved scenario, and also accepts a `scenario_id`, passed
   through to Core as `{id}` rather than resolved client-side. A plan with no steps surfaces a typed error
   rather than an unhandled 400.
2. It surfaces per-step `simulationCount`, per-attack `moves` counts, per-simulator `simulators`,
   `attackerSimulators` and `targetSimulators` counts, `isLimitReached`, and structured constraints; and passes
   through `limit`, `includeDisabled`, `getConstraints`, `getAllConstraints` and `useCache` with documented
   defaults.
3. The tool returns runnable counts by default (`includeDisabled=false`) and can return expected counts
   (`includeDisabled=true`); when both are requested it issues both calls and labels each result. The
   documentation states that expected cannot be derived from a runnable response.
4. Numbers match the console for the same configuration, per view and per parameter set: the Add Simulators
   Checkout tab with `includeDisabled=true, getConstraints=true`, and run gating with `includeDisabled=false`.
5. When `isLimitReached` is true, the tool reports it explicitly, preserves the distinction between `null` (not
   computed) and `0` (runs nowhere), surfaces that the returned step list is shorter than the plan's, and
   performs no auto-removal.
6. No estimation path exists in the MCP layer outside `plan/statistics`. `_get_scenario_statistics` and its two
   callers are migrated onto the new tool rather than left as a parallel implementation.
7. All 88 constraint reason codes in `constraints.js` have a plain-language description and a concrete
   suggested fix expressed as a yes/no choice. A test fails if any code lacks an entry.
8. No raw reason code reaches the user. An unrecognised code (one added upstream after this ticket) renders a
   safe generic explanation, never the code itself.
9. An attack with `moves[id] === 0` is auto-removed with an explanation, without blocking save. A `null` value
   never triggers removal.
10. A simulator with `simulators[id] === 0` is auto-removed the same way, read from the attacker-union-target
    map rather than a single role map.
11. Any change to an earlier decision triggers a fresh call to the same endpoint.
12. The tool is registered with a confirmed wire name and `readOnlyHint=True`, and is documented in the CLAUDE.md
    tool catalog and rate-limiting gate table.
```

### Suggested Labels/Components

- Labels: `CTEM-dev` (unchanged)
- Components: none set on this project
