# Manual Test Plan — SAF-29967 run_scenario

Manual test cases to be triggered as prompts from Claude Desktop against a live
SafeBreach console (e.g., pentest01). Each test verifies end-to-end behavior through
the MCP tool interface as the LLM would use it.

**Pre-requisites:**
- All MCP servers running (`uv run start_all_servers.py`)
- Claude Desktop connected to Config Server (port 8000) and Studio Server (port 8004)
- Target console has connected simulators

---

## Slice 1: Ready-to-run OOB Scenario

### T1.1 — Discover and run a ready OOB scenario

**Prompt:**
> List the available scenarios on pentest01 that are ready to run. Pick one and run it.

**Expected behavior:**
1. Agent calls `get_scenarios` (Config Server) with `ready_to_run_filter=True`
2. Agent picks a scenario and calls `run_scenario` (Studio Server) with the UUID
3. Response shows: test_id, predicted simulations per step, "Scenario successfully queued"
4. Agent suggests using `get_test_details` with the test_id to track progress

**Verify:**
- [ ] Scenario listed with `is_ready_to_run=True`
- [ ] Queue response includes test_id and step_run_ids
- [ ] Predicted simulation counts shown per step
- [ ] Test appears on the console (check UI)

---

### T1.2 — Run with custom test name

**Prompt:**
> Run the scenario "Step 1 - Fortify your Network Perimeter" on pentest01 with
> the test name "Manual Sign-off Test T1.2"

**Expected behavior:**
1. Agent calls `run_scenario` with `test_name="Manual Sign-off Test T1.2"`
2. Response shows the custom name in the output

**Verify:**
- [ ] Response shows `Test Name: Manual Sign-off Test T1.2`
- [ ] Test visible on console with the custom name

---

### T1.3 — Attempt to run non-existent scenario

**Prompt:**
> Run scenario with ID "00000000-0000-0000-0000-000000000000" on pentest01

**Expected behavior:**
1. Agent calls `run_scenario` with the fake UUID
2. Response shows error: "not found"

**Verify:**
- [ ] Clear error message returned (not a crash)
- [ ] No test created on the console

---

### T1.4 — Dry run a ready scenario

**Prompt:**
> I want to preview how many simulations scenario "Step 1 - Fortify your Network Perimeter"
> would produce on pentest01 without actually running it.

**Expected behavior:**
1. Agent calls `run_scenario` with `dry_run=True`
2. Response shows "Dry Run" header with per-step simulation counts
3. Response states "No test was queued"

**Verify:**
- [ ] Per-step breakdown shown with real numbers (e.g., Step 1: 1,676)
- [ ] Total predicted simulations shown
- [ ] No test appears on the console

---

## Slice 2: Ready-to-run Custom Plan

### T2.1 — Discover and run a custom plan

**Prompt:**
> List the custom plans on pentest01 that are ready to run. Pick one with a small
> number of predicted simulations and run it.

**Expected behavior:**
1. Agent calls `get_scenarios` with `creator_filter='custom'` and `ready_to_run_filter=True`
2. Agent may call `run_scenario` with `dry_run=True` first to preview
3. Agent calls `run_scenario` with the plan's integer ID
4. Response shows test_id, source_type=custom

**Verify:**
- [ ] Custom plan identified by integer ID
- [ ] Response shows `source_type: custom`
- [ ] Test appears on the console
- [ ] Predicted simulation counts shown

---

### T2.2 — Dry run a custom plan

**Prompt:**
> How many simulations would custom plan 130 produce on pentest01?

**Expected behavior:**
1. Agent calls `run_scenario` with `scenario_id="130"`, `dry_run=True`
2. Response shows per-step prediction for the custom plan

**Verify:**
- [ ] Response shows "Dry Run" with source_type=custom
- [ ] No test queued

---

## Slice 3: Non-ready OOB Scenario + Augmentation

### T3.1 — Two-turn diagnostic workflow

**Prompt:**
> Try to run the scenario "Magic Hound (APT35)" on pentest01

**Expected behavior:**
1. Agent calls `run_scenario` with the scenario UUID
2. Response shows "Scenario Not Ready to Run" diagnostic
3. Diagnostic lists each step with missing filters
4. Diagnostic shows augmentation examples (OS filter, role filter, etc.)

**Verify:**
- [ ] Diagnostic lists all steps that need augmentation
- [ ] Each missing filter type identified (targetFilter, attackerFilter)
- [ ] attacksFilter context shown (attack types per step)
- [ ] Augmentation examples provided

---

### T3.2 — Full three-turn workflow (diagnostic, preview, execute)

**Prompt:**
> I want to run the scenario "KongTuke" on pentest01. It's not ready to run —
> help me configure the missing filters, preview the predictions, and then execute.

**Expected behavior:**
1. Agent calls `run_scenario` → gets diagnostic
2. Agent calls `get_console_simulators` to discover available simulators
3. Agent constructs `step_overrides` JSON based on diagnostic + available simulators
4. Agent calls `run_scenario` with `step_overrides` + `dry_run=True` → preview
5. Agent presents prediction to user
6. Agent calls `run_scenario` with `step_overrides` (no dry_run) → executes

**Verify:**
- [ ] Agent correctly reads the diagnostic output
- [ ] Agent discovers simulators and builds appropriate filters
- [ ] Dry run shows per-step predictions
- [ ] Final execution queues the test with augmented filters
- [ ] Test appears on the console

---

### T3.3 — Partial augmentation with allow_partial_steps

**Prompt:**
> Run the scenario "CISA Alert AA24-109A (StopRansomware: Akira Ransomware)" on pentest01.
> Some steps might not produce simulations — that's OK, run it with partial coverage.

**Expected behavior:**
1. Agent gets diagnostic, builds overrides
2. Agent may preview with dry_run (some steps might show 0)
3. Agent calls `run_scenario` with `allow_partial_steps=True`

**Verify:**
- [ ] Response notes which steps have 0 simulations
- [ ] Test still queues despite partial coverage
- [ ] `allow_partial_steps` correctly passed

---

### T3.4 — Augmentation with specific simulator UUIDs

**Prompt:**
> I want to run a non-ready scenario on pentest01 but target only Windows simulators.
> First list the Windows simulators, then configure and run the scenario.

**Expected behavior:**
1. Agent calls `get_console_simulators` with `os_type_filter="Windows"`
2. Agent gets scenario diagnostic
3. Agent builds overrides using specific simulator UUIDs or Windows OS filter
4. Agent previews with dry_run, then executes

**Verify:**
- [ ] Agent correctly filters simulators by OS
- [ ] Overrides use appropriate filter format
- [ ] Scenario executes with targeted simulators

---

## Slice 4: Non-ready Custom Plan + Augmentation

### T4.1 — Augment and run a non-ready custom plan

**Prompt:**
> Run custom plan "China Scenario draft" (id 134) on pentest01. It's not ready —
> configure the missing filters and run it.

**Expected behavior:**
1. Agent calls `run_scenario(scenario_id="134")` → diagnostic
2. Agent builds overrides for missing steps
3. Agent previews with dry_run
4. Agent executes

**Verify:**
- [ ] Diagnostic shows source_type=custom
- [ ] Overrides applied to custom plan
- [ ] Full payload sent (not planId reference) since overrides applied
- [ ] Test appears on the console

---

### T4.2 — Dry run a non-ready custom plan with overrides

**Prompt:**
> How many simulations would custom plan 132 "Russian Based Threat Actor Coverage"
> produce if I configure all steps with broad Windows+Linux filters?

**Expected behavior:**
1. Agent gets diagnostic for plan 132
2. Agent builds broad overrides
3. Agent calls with `dry_run=True` + `step_overrides`
4. Shows prediction without queuing

**Verify:**
- [ ] Prediction includes per-step counts for all 3 steps
- [ ] No test queued
- [ ] Response clearly states "No test was queued"

---

## Cross-cutting Scenarios

### T5.1 — End-to-end autonomous workflow

**Prompt:**
> Analyze the security posture of pentest01 by running a comprehensive network
> perimeter scenario. Choose the best available scenario, preview it, and run it.
> Then check the test status after a minute.

**Expected behavior:**
1. Agent discovers scenarios via Config Server
2. Agent evaluates options (ready vs not-ready, step count, categories)
3. Agent previews with dry_run
4. Agent runs the chosen scenario
5. Agent waits, then checks status via `get_test_details` on Data Server

**Verify:**
- [ ] Agent makes informed scenario selection
- [ ] Preview step happens before execution
- [ ] Test status retrieved after execution
- [ ] Coherent end-to-end conversation

---

### T5.2 — Error recovery

**Prompt:**
> Run scenario "abcd-1234" on pentest01

**Expected behavior:**
1. Agent calls `run_scenario` with the invalid ID
2. Error returned (not found)
3. Agent suggests discovering available scenarios

**Verify:**
- [ ] Graceful error handling
- [ ] Agent provides helpful next steps

---

### T5.3 — Cross-server workflow (Config + Studio + Data)

**Prompt:**
> List all ready-to-run OOB scenarios on pentest01, run the one with the fewest steps,
> and show me the simulation results once some complete.

**Expected behavior:**
1. Config Server: `get_scenarios` with `ready_to_run_filter=True`, `order_by="step_count"`
2. Studio Server: `run_scenario` with the first result
3. Data Server: `get_test_details` / `get_test_simulations` with the test_id

**Verify:**
- [ ] All three servers used correctly
- [ ] Agent tracks the test_id across servers
- [ ] Simulation results retrieved and presented
