# Context — SAF-34615, `safebreach-mcp` share (attack search parity)

## Status

This folder's original `context.md` was a ~1,250-line platform investigation covering the whole of SAF-34615:
the `configuration` Plan write API, the orchestrator's filter implementation, the console's Studio behaviour,
Propagate exclusion, and the full design trail from nine MCP tools to one.

**It moved to `breach-genie` on 2026-09-06**, as
`prds/feature-SAF-34615-validate-scenario-building-skill/platform-investigation.md`, because the work it grounds
moved there: the scenario write path is now `createValidateScenario`, a native Helm tool, not an MCP tool.

Read that file when you need the *why* behind the plan-body contract. This file covers only what this repo
still builds.

---

## Scope that remains here

One phase: `get_playbook_attacks` gains `attack_type_filter`, `attack_phase_filter` and `tags_filter`.

## Findings that still apply to this repo's work

| # | Finding | Consequence |
|---|---|---|
| F-A | The playbook fetch already retrieves **every** attack with full tag data (`{base_url}/api/kb/vLatest/moves?details=true`), cached as `playbook_attacks` (maxsize=5, TTL=1800s). | The three new filters need **no new upstream call** — they run Python-side against the cached set, like the existing MITRE and platform filters. |
| F-B | `transform_reduced_playbook_attack` drops tag data unless `include_tags=True`, even though it was already fetched. | The only data-plumbing change is carrying type/phase/tag through the reduced transform. |
| F-C | FR2's investigation found no way to bulk-search by CVE or named threat group today. | This is the gap the work closes. A generic group-keyed `tags_filter` covers Threat Actor, CVE and custom groups without a parameter per group. |
| F-D | Tag group names are free-form strings; a wrong one matches nothing rather than erroring. | The exact strings (`"CVE"`, `"Threat Actor"`) must be named in the tool description — Risk R1. |
| F-E | The orchestrator's attack-phase values are the `Package` enum (`INFILTRATION=2`, `LATERAL=1`, `EXFILTRATION=0`, `HOST_LEVEL=5`), but the readable strings are what a caller supplies. | **This tool filters on the readable strings only.** The enum mapping belongs to the write tool in `breach-genie`, which needs it at persist time. Keeping the mapping in one place is what stops the two repos drifting (Risk R3). |

## Cross-repo contract

The one thing this repo must keep in lockstep with `breach-genie`: the **attack-phase vocabulary** and the
**axis names**. An attack found by `attack_phase_filter='exfiltration'` here has to be selectable by the same
string in the plan body there. `breach-genie`'s `references/plan-body-contract.md` cites this contract rather
than restating it, so there is one source of truth rather than two that can diverge.

## Decisions taken during planning

| Decision | Choice | Rationale |
|---|---|---|
| Branch base | `origin/feature/SAF-35508-plan-statistics-mcp-tool` | Set when this branch still carried the write path and depended on SAF-35508's statistics tools. Now that the write moved out, **this base is no longer needed** — the filter work depends on nothing in SAF-35508. Rebasing onto `main` before opening the PR would simplify the merge; flagged rather than done, since it rewrites a pushed branch. |
| Branch/folder naming | `feature/SAF-34615-validate-scenario-build-mcp-tools` | Named when the scope was the MCP tool set. Now a misnomer — the tools moved. Kept anyway: renaming a pushed branch mid-flight breaks the PRD-folder convention's branch↔folder mapping for no functional gain. Noted so a reader is not confused by it. |
| PRD location | Canonical record in `breach-genie`; a small self-contained PRD here | The feature lives where the code lives. Duplicating the design across two repos guarantees drift; a pointer does not. |
