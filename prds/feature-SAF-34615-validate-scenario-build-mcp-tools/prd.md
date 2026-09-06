# Attack search parity for Validate scenario building (SAF-34615) — `safebreach-mcp` share

## 1. Overview

- **Title**: Attack search parity for Validate scenario building — SAF-34615, `safebreach-mcp` share
- **Task Type**: Feature
- **Purpose**: Give Helm a search vocabulary that matches the plan body it assembles. `get_playbook_attacks`
  gains attack-type, attack-phase and tag filters so the `creating-validate-scenario` skill can find the right
  attacks — by type, by phase, by threat actor or CVE — before composing them into a scenario. This is the whole
  of this repo's remaining share of SAF-34615.
- **Target Consumer**: Helm, via the `creating-validate-scenario` skill; and any other MCP client searching the
  playbook.
- **Target Roles (RBAC)**: none new — read-only, existing per-console auth.
- **Business Alignment**: Epic SAF-34231, "Helm Skills & Tools for CTEM answer quality." Stage 1 of 4.
- **Originating Request**: [SAF-34615](https://safebreach.atlassian.net/browse/SAF-34615), reported by Tal Rotem.

> ### Where the rest of SAF-34615 lives
>
> This PRD was originally the whole feature: nine mutating MCP tools for building and saving a Validate
> scenario. Two owner decisions on **2026-09-06** moved that work out of this repo:
>
> 1. Collapse nine tools into one, with a Helm skill as the flow orchestrator.
> 2. Move that one tool out of MCP entirely — it is now `createValidateScenario`, a **native Helm tool** in
>    `breach-genie`, which gains a Zod-enforced body contract, `requireApproval: true` for a platform-enforced
>    save confirmation, and a per-account `featureFlag`.
>
> **The canonical SAF-34615 planning record is now in `breach-genie`**, branch
> `feature/SAF-34615-validate-scenario-building-skill`,
> `prds/feature-SAF-34615-validate-scenario-building-skill/`:
> - `prd.md` — the feature (skill + write tool)
> - `platform-investigation.md` — the platform/API investigation that used to be this folder's `context.md`,
>   moved with the work it grounds
> - `test-plan.md` — the feature's tests
>
> This PRD is deliberately self-contained and small. Read it for the filter work only.

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

`get_playbook_attacks` (`safebreach_mcp_playbook`) gains three optional parameters — `attack_type_filter`,
`attack_phase_filter`, `tags_filter` — in the same style as its existing `mitre_technique_filter` and platform
filters. All three are applied **Python-side against the already-cached full attack fetch**
(`_get_all_attacks_from_cache_or_api` → `filter_attacks_by_criteria`). No new upstream API call: the raw tag data
is already present in every fetched attack, it is simply not carried through `transform_reduced_playbook_attack`
today unless `include_tags=True`.

The axis names and the attack-phase vocabulary match the plan-body contract the `breach-genie` tool accepts
exactly, so an attack found here can be selected there without translation. That alignment is the point — it is
why this work stayed on this side of the split rather than being folded into the skill.

### Alternatives Considered

| Alternative | Pros | Cons | Why not chosen |
|---|---|---|---|
| **Dedicated `cve_filter` / `threat_actor_filter` parameters** | Discoverable; no need to know tag group names | Two more parameters for what is one mechanism; every future tag group needs another | Generic `tags_filter` covers Threat Actor, CVE and custom groups with one shape. Named as a fast-follow if the generic form proves friction-prone (Risk R2) |
| **A new upstream call with server-side filtering** | Less data pulled | The full attack set is already fetched and cached for every other filter; a second path would diverge | Python-side filtering matches every existing filter on this tool |
| **Leave FR2's gap open** and let the skill filter client-side | No repo change at all | Helm would page through the whole catalog to find three attacks; the search vocabulary would drift from the plan body's | The gap was found during investigation and is real |

---

## 3. Core Feature Components

### Component A — Attack Search Parity

**Purpose**: Close FR2's CVE/named-threat-group discovery gap and keep the search vocabulary aligned with the
plan body's filter vocabulary.

**Key Features**:
- `attack_type_filter` — comma-separated, OR logic, matching the existing filter style on this tool.
- `attack_phase_filter` — accepts `infiltration|lateral|exfiltration|host_level`. **These are the same readable
  strings the `breach-genie` tool accepts**, which maps them onto the orchestrator's `Package` enum
  (`INFILTRATION=2|LATERAL=1|EXFILTRATION=0|HOST_LEVEL=5`) at persist time. This tool filters on the readable
  form; it does not need the enum.
- `tags_filter` — a group-keyed dict (e.g. `{"Threat Actor": ["APT29"]}`) covering Threat Actor, CVE and custom
  tag groups without a dedicated parameter per group.
- All three compose with each other and with the existing MITRE/platform filters, and respect existing
  pagination.

**Integration points**: `safebreach_mcp_playbook/playbook_functions.py`, `playbook_types.py`,
`playbook_server.py`.

---

## 4. API Endpoints and Integration

### Existing APIs Consumed

| API | URL | Method | Consumed by |
|---|---|---|---|
| Playbook attacks (moves) | `{base_url}/api/kb/vLatest/moves?details=true` | GET | The existing `get_playbook_attacks` fetch-all-and-cache path — **no new call** |

### New MCP Tools to Create

**None.** This PRD adds no tool. It extends one existing read tool.

### Enhanced Existing Tool

| Tool | New parameters | Server |
|---|---|---|
| `get_playbook_attacks` | `attack_type_filter?: str`, `attack_phase_filter?: str`, `tags_filter?: dict[str, list[str]]` | `safebreach_mcp_playbook` |

---

## 6. Non-Functional Requirements

### Security & Compliance
- Read-only; existing per-console auth (`get_auth_headers_for_console`, `check_rbac_response`). No new roles, no
  rate-limit gate (the gate pattern applies to `readOnlyHint=False` tools only).

### Technical Constraints
- **Backward compatibility**: all three parameters are additive and optional; existing callers are unaffected.
- **No new upstream load**: filtering runs against the cached attack set, so the `playbook_attacks` cache
  (maxsize=5, TTL=1800s) behaviour is unchanged.

---

## 7. Definition of Done

**Core Functionality**
- [ ] `get_playbook_attacks` supports `attack_type_filter`, `attack_phase_filter` and `tags_filter`.
- [ ] The exact tag group names (`"CVE"`, `"Threat Actor"`) are documented in the tool description, not left for
      the caller to guess — a wrong group name returns zero results silently (Risk R1).
- [ ] The attack-phase vocabulary matches the `breach-genie` plan-body contract exactly, so an attack found here
      is selectable there without translation.
- [ ] `CLAUDE.md`'s `get_playbook_attacks` catalog entry and `CHANGELOG.md` are updated.

**Quality Gates**
- [ ] Each filter is covered individually and in combination with the existing MITRE/platform filters.
- [ ] A mistyped tag group name is asserted to return zero results rather than raise — that silent-failure mode
      is the point of Risk R1.
- [ ] Pagination behaviour is unchanged when the new filters are active.

**Cross-repo (tracked, not owned here)**
- [ ] SAF-34615's scenario-creation DoD (DoD1/DoD3/DoD4, Propagate exclusion, themed step names, DAG assembly)
      is satisfied by `breach-genie`'s Phase 7 — this repo's DoD gate references it rather than restating it.

---

## 8. Implementation Phases

| Phase | Status | Completed | Commit SHA | Notes |
|---|---|---|---|---|
| Phase 1: `get_playbook_attacks` filter parity | ⏳ Pending | - | - | The whole of this repo's scope |

### Phase 1: `get_playbook_attacks` filter parity

**Semantic Change**: Extend the existing playbook search tool with three filter axes.

**Deliverables**: The three parameters, their filtering logic, the tag/type/phase data carried through the
reduced transform, docs, and tests.

**Changes**:

| File | Change |
|---|---|
| `safebreach_mcp_playbook/playbook_functions.py` | Modified — extend `filter_attacks_by_criteria` with the three new axes |
| `safebreach_mcp_playbook/playbook_types.py` | Modified — carry tag/type/phase data through `transform_reduced_playbook_attack` |
| `safebreach_mcp_playbook/playbook_server.py` | Modified — expose the new parameters, document the exact tag group names |
| `CLAUDE.md` | Modified — update the `get_playbook_attacks` catalog entry |
| `CHANGELOG.md` | Modified — `### Added` bullet |
| `pyproject.toml` | Modified — version bump |

**Implementation Details**: Filters apply Python-side against the already-cached fetch, following the pattern the
existing MITRE and platform filters use. The tag data needed is already on every fetched attack and only needs
carrying through the reduced transform. Attack-phase values are the readable strings
(`infiltration|lateral|exfiltration|host_level`) — the `Package` enum mapping belongs to the write tool in
`breach-genie`, not here.

**What can go wrong**: a mistyped tag group name returns zero results rather than erroring — name the exact
group strings in the tool description so the skill can encode them literally rather than guessing.

**Data flow**: caller → `get_playbook_attacks` → cached attack list → Python-side filtering → paginated results.

**Git Commit**: `feat(playbook): add attack type, phase and tag filters to get_playbook_attacks`

---

## 9. Risks and Assumptions

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| R1 | **Silent-failure search vocabulary.** `tags_filter` is a generic group-keyed dict with no validation of group names — a wrong or mistyped group returns zero results, not an error. | Low-Medium | Document the exact group strings (`"CVE"`, `"Threat Actor"`) in the tool description; the `breach-genie` skill's procedure states them literally. Asserted in the DoD rather than assumed. |
| R2 | **The generic `tags_filter` shape may prove friction-prone** in practice versus dedicated `cve_filter`/`threat_actor_filter` parameters. | Low | Named as a fast-follow, decided on real usage rather than pre-emptively. |
| R3 | **Vocabulary drift across repos.** The attack-phase strings here and in `breach-genie`'s plan-body contract must stay identical, or an attack found here cannot be selected there. | Medium | The DoD asserts the match explicitly. `breach-genie`'s `references/plan-body-contract.md` cites this contract rather than restating it independently. |

---

## 10. Future Enhancements

- **Dedicated `cve_filter` / `threat_actor_filter` parameters** instead of the generic `tags_filter` — see R2.
- Everything else formerly listed here (filter-based simulator selection, editing, asset association) belongs to
  the `breach-genie` PRD and the Stage 2/3/4 stories (SAF-35484 / SAF-35485 / SAF-35051).

---

## 11. Executive Summary

- **Issue/Feature Description**: Helm needs to find attacks by type, phase, threat actor and CVE before
  assembling a Validate scenario. `get_playbook_attacks` cannot filter on those axes today.
- **What Was Built**: three additive, optional filter parameters on one existing read tool.
- **Key Technical Decisions**: Python-side filtering against the already-cached fetch (no new upstream call);
  one generic group-keyed `tags_filter` rather than a parameter per tag group; readable attack-phase strings
  here, with the `Package` enum mapping owned by the write tool in `breach-genie`.
- **Scope Changes**: **large.** This PRD originally specified nine mutating tools, then one, then none — the
  scenario write path moved to `breach-genie` as a native Helm tool across two owner decisions on 2026-09-06.
  The platform investigation moved with it (`platform-investigation.md` there). What remains here is the search
  parity that was always this repo's natural share.
- **Business Value Delivered**: without these filters, the skill would page the whole attack catalog to find a
  handful of attacks, and its search vocabulary would drift from the plan body it assembles.

---

## 13. Change Log

| Date | Change Description |
|---|---|
| 2026-09-02 16:49 | PRD created — initial draft (nine mutating tools + in-process draft cache) |
| 2026-09-03 15:20 | Corrected against SAF-35508's now-implemented contract (five-state verdict, required `attack_ids`, `fix_lever` removed, AC-4 partially verified) |
| 2026-09-06 | Restructured to a single `create_plan` entry point, with the Helm skill as flow orchestrator; phases 7→2 |
| 2026-09-06b | Rescoped: the write tool left this repo for `breach-genie` as the native `createValidateScenario` |
| 2026-09-06c | **PRD moved.** The canonical SAF-34615 record now lives in `breach-genie`; `context.md` moved there as `platform-investigation.md`. This PRD rewritten small and self-contained for the one phase this repo still owns — `get_playbook_attacks` filter parity. Superseded write-path design is no longer duplicated here; it lives with the work in `breach-genie`. |
