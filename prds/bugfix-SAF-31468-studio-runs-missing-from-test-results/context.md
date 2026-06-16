# Context: SAF-31468

**Status:** Phase 6: PRD Created (planning-dev-task)
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

---

# Planning (planning-dev-task)

## Decisions (confirmed with user)
- **DRAFT-attack behavior at run time:** WARN ONLY — run as draft (Studio-only), but return a clear
  `hint_to_agent` that results won't appear in Test Results and recommend publishing first. No status change.
- **Draft-flag mechanism:** AUTO-RESOLVE the attack's current publication status before queuing and set
  `plan.draft` accordingly. NO change to `run_studio_attack`'s public signature.
- **SAF-10419 (backend "sticky draft"):** Resolved long ago — NOT a concern. Dropped as a caveat/task.
- **Status-lookup failure handling:** Distinguish two cases. **Attack not found** → raise a clear `ValueError`
  (mirrors `set_studio_attack_status`). **GET itself fails** (RequestException / RBAC / parse) → proceed as
  PUBLISHED (`draft:false`) and add a warning `hint_to_agent` that publication status could not be confirmed
  (prioritizes Test-Results visibility over reproducing the bug on flaky reads).

## Implementation Map (file:line, verified)

### Function to fix
- `safebreach_mcp_studio/studio_functions.py:1180-1310` — `sb_run_studio_attack(attack_id, console="default",
  target_simulator_ids=None, attacker_simulator_ids=None, all_connected=False, test_name=None)`.
  - Input validation: `1206-1219`.
  - Rate-limiter `check_limit`: `1232` (after validation, before filter/payload build).
  - Filter build: `1234-1263`.
  - Payload build: `1265-1283`; **hardcoded `"draft": True` at `1281`** → make conditional.
  - Queue submit: `1286-1289` via `_submit_to_queue(payload, console, query_params={"enableFeedbackLoop":"true","retrySimulations":"false"})`.
  - Result dict: `1296-1302` (`test_id`, `step_run_id`, `test_name`, `attack_id`, `status`).
  - Rate-limiter `record_action`: `1305` (after successful queue).

### Status-read path to reuse
- Existing pattern in `sb_set_studio_attack_status` (`studio_functions.py:1632-1661`):
  - `base_url = get_api_base_url(console, 'config')`, `account_id = get_api_account_id(console)`,
    `headers = {**get_auth_headers_for_console(console)}`.
  - `GET {base_url}/api/content/v1/accounts/{account_id}/customMethods?status=all`, `check_rbac_response`,
    `api_response.get("data", ...)`, loop to find `attack.get("id") == attack_id`.
  - Status field: lowercase `status` ("draft" | "published"); name via `attack.get("name")`.
- **Plan:** extract a small helper `_get_attack_status_by_id(attack_id, console) -> (status, name)` (raises
  `ValueError` if not found) to avoid duplicating the GET/filter logic; call it from both
  `sb_run_studio_attack` and (optionally, as a refactor) `sb_set_studio_attack_status`.
- `_submit_to_queue` signature: `studio_functions.py:146-199` — `(payload, console, query_params=None)`,
  POSTs `{base_url}/api/orch/v4/accounts/{account_id}/queue`.

### Hint/warning convention to follow
- `hint_to_agent` field on the result dict. Examples: `studio_functions.py:1466-1472` (poll hint),
  `2728-2751` (ad-hoc queued hint incl. skipped-attacks note); `studio_types.py:49-53` (pagination hint).

### Tests
- `safebreach_mcp_studio/tests/test_studio_functions.py` → class `TestRunStudioAttack` (`1396-1574`).
  - Tests currently mock ONLY `requests.post`; fixture `mock_run_response` at `242-257`.
  - `test_run_simulation_all_connected` asserts `payload['plan']['draft'] is True` at **line 1445** — must update.
  - Status-read GET is mocked elsewhere via `@patch('...studio_functions.requests.get')`
    (e.g. `TestGetAllStudioAttacks`, `665-694`); `mock_getall_response` fixture at `152-197` shows
    `status: "draft"`/`"published"`.

## Solution Approach (chosen)
Resolve the attack's status via `_get_attack_status_by_id` after `check_limit` (line ~1232) and before payload
build. Set `is_draft = (status == "draft")` and use `"draft": is_draft` at line 1281 (PUBLISHED → False).
When `is_draft`, append a `hint_to_agent` to the result explaining the run is visible only in Breach Studio
(not Test Results) and recommending `set_studio_attack_status` to publish first; also expose `draft: is_draft`
in the result dict. On status-lookup failure, degrade gracefully (log + warn) without blocking the run.

### Alternatives considered (and rejected)
- **Auto-publish DRAFT before running** — rejected: publishing has production impact and requires explicit
  confirmation (saf-28235:267); silent publish is unsafe. (User chose warn-only.)
- **New `draft`/run-mode parameter on the tool** — rejected: adds API surface; auto-resolve covers the real
  cases. (User chose auto-resolve, no signature change.)
- **Refuse to run DRAFT attacks** — rejected: too strict; draft testing in Studio is a legitimate flow.
- **Always omit `draft`** — rejected: DRAFT attacks genuinely require `draft:true` to execute (saf-28235:253).

## Risks / Edge Cases
- **Existing test breakage (certain):** all `TestRunStudioAttack` tests now trigger a `requests.get`; each needs
  a `requests.get` mock returning the attack with the intended status, and the `draft is True` assertion at
  `:1445` must flip to `False` (published) — update as part of the change.
- **Extra API read per run:** one additional GET before queue; handle failure gracefully (warn + proceed or
  surface a clear error) so a transient read error doesn't block execution. Decide default-on-failure behavior
  in the PRD (recommend: surface error if attack genuinely not found; warn-and-proceed-as-draft only if the
  read itself fails).
- **Attack not found:** raise a clear `ValueError` (mirrors `set_studio_attack_status` behavior).
- **Rate limiting unaffected:** `check_limit`/`record_action` placement unchanged.

## Verification
- Unit: published → payload `draft` False/omitted, no draft hint; draft → payload `draft` True + `hint_to_agent`
  present; attack-not-found → ValueError; status-GET failure → graceful path. Update existing TestRunStudioAttack
  mocks/assertions.
- E2E/manual: publish a brand-new attack (never run as draft), run via `run_studio_attack`, confirm it appears in
  `get_tests` / Test Results under the returned planRunId.
