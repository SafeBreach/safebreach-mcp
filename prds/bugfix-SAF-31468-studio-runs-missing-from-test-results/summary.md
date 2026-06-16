# Summary: SAF-31468

**Proposed Title:**
`run_studio_attack hardcodes draft:true, hiding HELM-launched Studio runs from Test Results`

**Type:** Bug | **Priority:** High | **Component/Tags:** Breach-genie, MCP | **Repo:** safebreach-mcp

---

## Description (proposed)

### Summary
Custom Breach Studio attacks executed via HELM through the MCP `run_studio_attack` tool complete
successfully on the target simulator and are retrievable via `get_studio_attack_latest_result(attack_id)`,
but the resulting test run **never appears in the Test Results / test history UI**. The same attack run as
a manual "quick run" from the UI does appear. Reproduced on `pentest-findings-9c4d7f.dev.sbops.com`
(attack `10000026`, test `1779631053907.18`) and again on Pentest01 (attack `10004721`, test
`1780579449522.31`). Publishing the attack via HELM before running does **not** fix it.

### Root cause
`sb_run_studio_attack` hardcodes `"draft": True` in the queue/orchestrator plan payload, **regardless of
the attack's publication status**:

- `safebreach_mcp_studio/studio_functions.py:1281` — `plan.draft = True` (function `sb_run_studio_attack`,
  payload at lines 1266–1283), submitted via `_submit_to_queue` with `enableFeedbackLoop=true`,
  `retrySimulations=false`.

Per canonical SafeBreach platform behavior (confirmed via Sigi / CS Confluence): *"For draft custom breach
methods, results only appear in Breach Studio. For published custom breach methods, results appear in
Simulation Results like all other published attacks."* Draft-flagged runs are **intentionally hidden** from
the global Test Results surface. Because the MCP always sends `draft:true`, every run — including runs of
already-PUBLISHED attacks — is draft-scoped and hidden. `get_studio_attack_latest_result` still works
because it queries `executionsHistoryResults` by `Playbook_id` (`studio_functions.py:1398`), which is not
subject to the test-history draft exclusion.

The sibling tools `run_scenario` (`studio_functions.py:~2916`) and `run_adhoc_scenario` (`~2705`) omit the
`draft` key entirely and their runs appear in Test Results. Prior design note `SAF-31295` explicitly warns:
*"DO NOT use draft:true (that is for studio draft attacks only)."* The flag was designed to be conditional
on attack status (saf-28235: DRAFT → requires `draft:true`; PUBLISHED → standard execution) but is applied
unconditionally.

### Reproduction
1. In HELM: "write a Windows host-level attack, run it and report me result and run id".
2. HELM creates a draft Studio attack, validates, saves, and publishes it (DRAFT → PUBLISHED).
3. HELM calls `run_studio_attack`; reports COMPLETED with a Run ID.
4. Open Test Results in the same account → the run is absent.

### Expected
A successful run reported by HELM for a PUBLISHED attack is discoverable from the Test Results page, like a
UI quick-run.

### Proposed fix (root-cause)
Make the `draft` flag conditional on the attack's publication status instead of hardcoding `True`:
1. Resolve the attack's current status (DRAFT vs PUBLISHED) before building the payload — reuse the existing
   read path (`get_all_studio_attacks` status handling at `studio_functions.py:843-864`;
   `set_studio_attack_status` at `1601-1767`).
2. Set `plan.draft = False` (or omit the key) when the attack is PUBLISHED; send `draft:true` only when the
   attack is genuinely DRAFT.
3. When an attack is DRAFT at run time, return a clear `hint_to_agent`/warning that the run will be visible
   only in Breach Studio (not Test Results) and recommend publishing first. Prefer warn / explicit opt-in
   over silent auto-publish (status transitions have production impact and require confirmation per
   saf-28235).
4. Handle the new status lookup failure gracefully so a transient read error does not block execution.

### Out of scope / caveats
- DRAFT-only runs remain legitimately Studio-scoped — the fix warns rather than forcing them into Test Results.
- Backend "sticky draft" history (**SAF-10419**, resolved Done): an attack run once as draft could stay
  draft-tagged even after publishing. Verify the target env (mgmt 2026.2.4 develop) includes that fix;
  acceptance testing must use a freshly published attack never previously run as draft.
- No data-server change required — Test Results visibility is governed server-side by the draft tag the MCP
  sends; `get_tests` has no client-side draft filter.

---

## Acceptance Criteria (proposed)

1. Running `run_studio_attack` against a **PUBLISHED** attack queues the test with `plan.draft = false`
   (or with the `draft` key omitted) and the run appears in `get_tests` and the Test Results UI under the
   returned planRunId.
2. Running `run_studio_attack` against a **DRAFT** attack still executes, and the response includes a clear
   warning/`hint_to_agent` that results are visible only in Breach Studio and recommends publishing first.
3. The attack's publication status is resolved before queuing via the existing Studio status-read path; a
   lookup failure degrades gracefully (does not crash the run) and is logged/warned.
4. Behavior of `run_scenario` and `run_adhoc_scenario` is unchanged.
5. Unit tests assert: published-attack payload omits `draft`/sends `false`; draft-attack payload sends
   `true` and includes the warning; status-lookup-failure path is covered.
6. E2E (or documented manual test): publish a brand-new attack (never run as draft), run it via
   `run_studio_attack`, and confirm it appears in Test Results.

---

## Investigation Sources
- Code: `safebreach_mcp_studio/studio_functions.py` (1266–1283, 1398, 843–864, 1601–1767);
  `safebreach_mcp_data/data_functions.py:234,295-301`; `safebreach_mcp_data/data_types.py:142-150`.
- Prior design: `prds/saf-28235/prd.md:251-267`; `prds/SAF-31295-run-adhoc-scenario/context.md:43`.
- Sigi (sb-answers): platform draft-vs-published behavior; SAF-10419; support cases SB-16951, SB-34202.
