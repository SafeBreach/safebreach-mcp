# Context: SAF-31468

**Status:** Phase 6: Summary Created
**Mode:** Improve existing ticket
**Branch:** `bugfix/SAF-31468-studio-runs-missing-from-test-results`
**Repo:** `/Users/yossiattas/Public/safebreach-mcp`

## Ticket Snapshot

- **Key:** SAF-31468
- **Type:** Bug
- **Priority:** High
- **Status:** To Do
- **Components/Tags:** Breach-genie, MCP; Validate; Cloud; internal
- **Reporter/Creator:** Jondi Tsveniashvili
- **Assignee:** Yossi Attas
- **Sprint:** Saf sprint 91
- **Related:** SAF-31110 ([HELM Automation] Cover scenario execution from HELM — Done)

### Current Summary
> HELM | safebreachStudio_run_studio_attack via HELM complete successfully but do not appear in Test Results UI

### Current Description (verbatim essence)
Custom Studio attacks executed via HELM complete successfully on the target simulator, but the
resulting test run does not appear in the Test Results UI. Users have no path to find their
HELM-launched custom attack runs in the standard test history view.

- When run manually as a **quick run** from the UI, the test **does** appear in Test Results.
- In Breach Studio's published list the attack **does** appear.

**Reproduction:**
1. In HELM, ask: "write a Windows host-level attack, run it and report me result and run id"
2. HELM creates a draft Studio attack, validates, and saves it.
3. HELM publishes the attack (DRAFT → PUBLISHED).
4. HELM calls `run_studio_attack` and reports COMPLETED with a Run ID.
5. Open the Test Results page in the same account.

**Observed:**
- HELM reports the test as COMPLETED with a Run ID and per-simulation outcome.
- The simulation actually ran successfully on the simulator.
- The run does NOT appear in the Test Results page.
- The data is still retrievable via `get_studio_attack_latest_result(attack_id)`.

**Expected:** A successful test run reported by HELM should be discoverable from the Test Results page.

### Evidence
- env: pentest-findings-9c4d7f.dev.sbops.com, management 2026.2.4 latest develop
- planRunId: `1779631053907.18`
- attack_id: `10000026` (PUBLISHED before run)
- Simulator: `1747feb4-dbc9-46cc-823a-4d0522a7c485` (6evkncvw, Windows 10)
- sbexecution log: `resultStatus: SUCCESS`, `resultCode: SimulationSuccess`

### Reproduced again (comments)
- Hadas Cohen on Pentest01: custom attack "Hadas's attack" (ID `10004721`), test ID `1780579449522.31` —
  ran but disappeared from Test Results.
- Jondi: telling HELM to publish the custom attack before running still leaves the test result missing.

## Scope (confirmed with user)
- **Repos to investigate:** safebreach-mcp only.
- **Outcome:** Root-cause + fix plan — pinpoint the exact payload/field difference between the MCP
  `run_studio_attack` path and the UI quick-run path, and specify the fix so runs appear in Test Results.

## Working Hypothesis (pre-investigation)
The `run_studio_attack` queue payload is missing a field/flag that the UI quick-run sets, which
governs whether a run is surfaced in the Test Results (test history) listing. The run executes and is
retrievable by attack ID, so the test record exists — but it is likely filtered out of the
Test Results query (e.g. test type / origin / "systemTest" / name / visibility flag).

## Investigation Findings (safebreach-mcp)

### Root cause — confirmed
`run_studio_attack` hardcodes `"draft": True` in the queue/orchestrator plan payload, regardless
of the attack's actual publication status.

- **`safebreach_mcp_studio/studio_functions.py:1281`** — inside `sb_run_studio_attack`
  (function spans ~1180–1310), the payload is:
  ```python
  payload = {
      "plan": {
          "name": test_name,
          "steps": [{
              "attacksFilter": {"playbook": {"operator": "is", "values": [attack_id], "name": "playbook"}},
              "attackerFilter": attacker_filter,
              "targetFilter": target_filter,
              "systemFilter": {}
          }],
          "draft": True          # <-- hardcoded, line 1281
      }
  }
  ```
  Submitted via `_submit_to_queue(...)` with query params `enableFeedbackLoop=true`,
  `retrySimulations=false` (`studio_functions.py:1286-1289`).

### Why draft runs vanish from Test Results — confirmed by Sigi (platform behavior)
Per canonical platform behavior (CS Confluence / dev-on-duty): *"For draft custom breach methods,
these results only appear in the Breach Studio. For published custom breach methods, the results
appear in Simulation Results, like all the other published attacks."* Draft-scoped runs are
**intentionally hidden** from the global Test Results / test history surface. The data remains
retrievable by attack ID — which is exactly why `get_studio_attack_latest_result` still works.
Related backend bug history: **SAF-10419** ("Published attacks marked as draft", resolved Done);
P&G/Pepsico support cases (SB-16951, SB-34202) describe the same "ran as draft → hidden" friction.

### Contrast with sibling tools (these DO appear in Test Results)
Field-by-field diff of the `plan` payload (all in `safebreach_mcp_studio/studio_functions.py`):

| Field | `run_studio_attack` (~1266) | `run_scenario` (~2916) | `run_adhoc_scenario` (~2705) |
|-------|------------------------------|------------------------|------------------------------|
| `plan.name` | ✓ | ✓ | ✓ |
| `plan.steps` | ✓ (single step) | ✓ | ✓ |
| `plan.systemTags` | **absent** | ✓ | ✓ (`[]`) |
| `plan.actions` | **absent** | ✓ | ✓ |
| `plan.edges` | **absent** | ✓ | ✓ |
| **`plan.draft`** | **✓ `True`** | **absent** | **absent** |

`run_scenario` and `run_adhoc_scenario` omit `draft` entirely and their runs show up in Test Results.
The prior design note in `prds/SAF-31295-run-adhoc-scenario/context.md:43` / `prd.md:158` explicitly
warns: *"DO NOT use `"draft": True` (that is for studio draft attacks only)."* The original Studio
design (`prds/saf-28235/prd.md:251-259`) defines: DRAFT status → "Requires `"draft": true` flag";
PUBLISHED → "Standard execution". So the flag was meant to be **conditional on attack status**, but
`run_studio_attack` applies it unconditionally.

### How Test Results is queried (no client-side draft filter in MCP)
- `get_tests` → `GET /api/data/v1/accounts/{account_id}/testsummaries?size=1000&includeArchived=false`
  (`safebreach_mcp_data/data_functions.py:234`). Client-side filtering is only by test type
  (ALM/Propagate vs BAS/Validate via `systemTags`, `data_functions.py:295-301`,
  `data_types.py:142-150`). There is **no** MCP-side draft filter — the exclusion happens
  **server-side** because the run was tagged draft.
- `get_studio_attack_latest_result` → `GET /api/data/v1/accounts/{account_id}/executionsHistoryResults`
  queried by `Playbook_id:("{attack_id}")` (`studio_functions.py:1398`). This per-playbook execution
  search is not subject to the test-history draft exclusion → still returns the run.

## Problem Analysis

**Problem scope.** `run_studio_attack` unconditionally queues every run with `plan.draft = True`.
The SafeBreach platform deliberately scopes draft-flagged custom-breach runs to Breach Studio only and
hides them from the global Test Results / test history surface. As a result, every HELM-launched custom
Studio attack run — even ones for attacks that are already PUBLISHED — is invisible in Test Results,
even though it executed successfully and is retrievable by attack ID.

**Affected area.** Single function: `sb_run_studio_attack` in
`safebreach_mcp_studio/studio_functions.py` (payload at lines 1266–1283; the `draft` key at line 1281).
The fix is isolated to payload construction; the `_submit_to_queue` call and downstream result handling
are unaffected. No data-server change is needed — Test Results visibility is governed server-side by the
draft tag the MCP sends.

**Expected behavior.** A PUBLISHED Studio attack run must be queued with `draft:false` (or with the
`draft` key omitted), exactly like `run_scenario` / `run_adhoc_scenario` and the UI "quick run", so the
run appears in Test Results. A DRAFT attack run may legitimately remain draft-scoped (Studio-only), but
the tool should make that consequence explicit to the agent/user.

**Fix direction (root-cause + plan).** Make the `draft` flag conditional on the attack's publication
status rather than hardcoding `True`:
1. Before building the payload, resolve the attack's current status (DRAFT vs PUBLISHED). The Studio
   server already reads attack status elsewhere (`get_all_studio_attacks` supports `status_filter`
   "draft"/"published", `studio_functions.py:843-864`; `set_studio_attack_status`,
   `studio_functions.py:1601-1767`) — reuse that read path.
2. Set `plan.draft = False` (or omit the key) when the attack is PUBLISHED; only send `draft:true`
   when the attack is genuinely in DRAFT.
3. When an attack is in DRAFT at run time, surface a clear `hint_to_agent`/warning that the run will be
   visible only in Breach Studio (not Test Results), and recommend publishing first — optionally support
   an explicit opt-in to publish-then-run. (Auto-publish has production impact — `set_studio_attack_status`
   requires explicit confirmation per saf-28235:267 — so prefer warn-or-opt-in over silent auto-publish.)

**Risks / edge cases.**
- *DRAFT-only runs are still legitimately hidden.* The fix must not claim DRAFT runs will appear in Test
  Results; it should warn instead. Tying visibility to status is the correct contract.
- *Backend "sticky draft" history (SAF-10419).* Sigi notes a backend bug where an attack run once as draft
  stayed draft-tagged even after publishing. SAF-10419 is resolved Done, but the target env (mgmt 2026.2.4
  develop) should be verified to include the fix; otherwise the MCP-side fix alone may not fully resolve
  visibility for attacks previously run as draft. Acceptance testing must use a freshly published attack
  that was never run as draft.
- *Status resolution cost/failure.* Adding a status lookup before queue introduces one extra API read and
  a new failure mode; handle lookup failure gracefully (e.g., default to safe behavior + warn) so a
  transient read error doesn't block execution.
- *Rate limiting unaffected* — `record_action` gate placement (after successful queue) does not change.

**Verification.** E2E: publish a brand-new Studio attack (never run as draft), run it via
`run_studio_attack`, confirm it appears in `get_tests` / Test Results UI with the returned planRunId.
Unit: assert the queued payload omits `draft` (or sends `false`) for a published attack and `true` for a
draft attack; assert the DRAFT-run warning/hint is present.

## Sigi Consultation (recorded)
Asked Sigi (sb-answers) about expected DRAFT vs PUBLISHED run behavior. Key confirmations: draft runs are
hidden from Test Results by design (visible only in Breach Studio); the `draft` flag should follow the
attack's publication status; a PUBLISHED attack should never be queued with `draft:true`; canonical
one-off run = publish first, queue with `draft:false`/no flag via the standard plan/orchestration endpoint.
Cited SAF-10419 and support cases SB-16951 / SB-34202.
