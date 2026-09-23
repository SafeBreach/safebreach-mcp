# Changelog

All notable changes to the safebreach-mcp project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

### Added

- `get_scenario_blocked_entities` gains a `simulator_ids` filter (SAF-35508 Phases 6-7) that makes the per-step
  listing a **per-simulator** answer: every attack the console recorded a constraint against on a named machine,
  independent of that attack's scenario-wide count. An attack that ran elsewhere but produced nothing *here* is
  listed; a scenario-wide zero citing no named machine is not. The scoped list is deliberately **not a subset** of
  the unscoped one, and carries its own hint saying so. Each listed attack shows only
  the codes cited *on* them. The ratio is reported against the step's attacks; the verdict, every total and
  both simulator-side sections stay scenario-wide. Each named simulator is answered `ran` / `blocked` /
  `excluded` / `not computed` / `not in this scenario` so an empty scoped list is never read as a clean
  scenario. Excluded (offline/disabled/unapproved) simulators are dropped from the match set — they carry
  a constraint against every move, so scoping to one naively would report a switched-off machine as
  incompatible with the entire step — and the list is withheld with a stated reason only when that empties
  the scope. Composes with `attack_ids`. Also repairs five never-executed assertions in the e2e suite
  whose field names never matched the emitted shape.

- `get_scenario_blocked_entities` (SAF-35508) — the sibling of `get_scenario_simulation_counts`,
  answering what in a scenario will not run and why. Same three inputs plus an optional `attack_ids`
  filter (`ran` outranks `blocked`, so a step-order-dependent answer is impossible). Reports every
  attack and simulator the console measured at exactly `0` with the constraints cited against it;
  an entity that merely runs on fewer simulators than offered is a reduction, not a block, and is not
  listed. Distinguishes **blocked** (scored `0`) from **excluded** (absent from scoring — offline,
  disabled or unapproved), which the raw response conflates only if you read absence as zero. Asks for
  `getConstraints=true, getAllConstraints=true`, so every applicable reason is recorded rather than the
  first; the caps and per-code grouping are what keep that affordable. Constraint meanings are relayed
  verbatim from the response's own `constraintCatalog` and none is authored here. The verdict
  (blocked / clean / partially evaluated / not evaluated) is decided by whether counts were computed,
  never by whether the lists are empty.
- The counts tool's hint now routes to `get_scenario_blocked_entities` for why a step produces nothing;
  previously it could only say that it did not answer that.

### Changed

- `get_scenario_blocked_entities` no longer calls a machine useless that runs in another step. Its verdict counted any
  entity scored zero in any step and said those "contribute nothing in this scenario"; on a live console that read
  "20 simulator(s)" where 15 of them produce simulations elsewhere. The sentence now states both halves — "5
  contribute nothing anywhere in this scenario; 15 more contribute nothing in at least one step but run in another" —
  from new `blocked_everywhere_attack_count` / `blocked_everywhere_simulator_count` fields. The verdict state and the
  existing counts are unchanged.
- Both scenario-statistics tools now register with `structured_output=False`. A tool returning `str` otherwise gets
  an auto-generated `{result: string}` output schema, and the MCP SDK then ships the whole answer twice — once as
  text and once as `structuredContent`. Measured on a ten-simulator step, the wire payload drops from 2,506 to
  1,471 characters with the rendered output unchanged.
- `get_scenario_simulation_counts` names both routes back when a step offers more than 20 simulators. Narrowing the
  step's simulators filter is still the better one, but it is open only to a caller holding the scenario body — the
  `scenario_id` and `test_id` forms are resolved server-side — so the omission now also points at `simulator_ids`,
  and at `get_console_simulators` as the place those ids come from.
- The per-simulator breakdown states that a machine's two numbers are its participation per role, not two batches to
  add up. Five simulators reading `attacker: 1, target: 1` under a total of `5` otherwise invites reading 10. The
  note rides on the step line only where rows follow it.
- `get_scenario_simulation_counts` reports a measured zero as `0 (measured)` rather than `0 - measured`, which
  parsed as a range on first read.
- Both tools accept `scenario` as a parsed object as well as JSON text. The prose offered both; the schema
  advertised only a string. A malformed JSON string still reaches the worded error rather than a validation failure.
- `get_scenario_simulation_counts` hint now says simulators are reported as ids and points at
  `get_console_simulators` to resolve them — ten bare UUIDs were otherwise a dead end.
- `get_scenario_blocked_entities` no longer returns a partial attack list when a step blocks more than 50
  attacks. It now drops the per-attack detail whole and reports a tally of blocked attacks per constraint
  code, so all of them are accounted for rather than the first fifty — measured on a 60-attack fixture the
  answer went from 8,462 characters covering 50 attacks to 1,793 covering 60, and the dominant reason (one
  offline machine implicated in every one) became a single line instead of being spread across fifty.
  Tally rows carry no validator detail, since a row stands for many attacks and one leaf's `required`/`actual`
  pair must not speak for all of them. Cited codes are now collected before capping so the catalog still
  covers every code any blocked entity cites. A named `attack_id` carries its blockers, which replaces the
  previous mechanism of pinning named ids ahead of the cap — there is no list left to pin into, and without
  it naming an attack past the cap would have returned a bare "blocked" with no reason.
- `get_scenario_simulation_counts` (SAF-35508) — a read-only Studio tool that scores a scenario
  against the fleet without running it, answering how many simulations it would produce and which
  simulators produce them. Takes exactly one of `scenario` (an ad-hoc body never saved, so a
  configuration can be scored while it is still being assembled), `scenario_id` (a saved plan's numeric
  id, passed through to Core as `{id}`) or `test_id` (a planRunId), plus an optional `simulator_ids`
  filter that answers each named simulator in both roles. An OOB scenario's UUID is refused rather
  than resolved, so no input form lists the console and every call costs exactly one request. Every
  query
  parameter to `POST /plan/statistics` is fixed internally: counts are *runnable*
  (`includeDisabled=false`), and constraints are never requested, since this answer renders none and
  one ordinary step measured 38,531 of them. A count the orchestrator never computed is reported as
  not computed rather than as a zero, and a reply shorter than the submitted plan is reported as
  early termination. Under 20 simulators offered, a step returns its simulation count plus a
  per-simulator breakdown — each simulator with what it would produce *as attacker* and *as target*,
  which is the pairing a choice of attackers and targets is made on; at or over the cap it returns
  only the count and asks the caller to narrow the step's simulators filter. Named `simulator_ids`
  are answered either way.

## 1.14.0 — 2026-09-07

### Removed

- The legacy SSE transport (SAF-32387). The servers now serve MCP streamable-http only, on a single
  `/mcp` endpoint (or `$SAFEBREACH_MCP_BASE_URL`); `GET /sse` and `POST /messages/` are gone, and the
  `SAFEBREACH_MCP_TRANSPORT` environment variable is no longer read. mcp-proxy (the production
  launcher) has pinned streamable-http since 2026-06-11, so no deployment is affected.
- The SSE-only auth plumbing that existed to bridge the two-request SSE session: the per-request
  `_user_auth_artifacts` ContextVar, the `_session_auth_artifacts` session store and its TTL cleanup,
  and the SSE session-id/semaphore migration in the concurrency middleware. Rate limiting and
  user-scoped cache keys now derive the caller identity only from the live MCP request (same rule
  SAF-32359 applied to outbound auth), so a token captured from an earlier request can never be
  reused across users.
- Test suite: the `conftest.py` ContextVar-to-request bridge from SAF-32359 is removed; tests inject
  auth through the MCP SDK request context (`mcp_request_auth` fixture).

### Fixed

- `manage_test(action="cancel")` no longer refuses to cancel a **PAUSED** test (SAF-32305). A
  client-side guard added in SAF-31111 raised `ValueError("Cannot cancel a paused test...")` before
  any API call, so agents were told to resume the test first — a step that is unnecessary, and that
  routes through `resume`, which has a documented orchestrator crash (SAF-32835). The transition was
  always supported: the orchestrator's `deletePlan()` has a dedicated branch for deleting a plan
  while paused, and the UI's "Remove test" has always used the same `DELETE .../queue/{planRunId}`
  endpoint. The guard came from misreading an intermittent 500 (`no plan was stopped`, a
  matrix-publisher retry race) as a state rule. Cancelling a paused test now issues that DELETE
  directly; a backend error propagates untouched rather than being re-described as a pause
  restriction.
- The `manage_test` tool description now states that a paused test can be cancelled directly, and
  `CLAUDE.md` documents all four actions including `delete`, live since SAF-29972 but never listed
  there.

## 1.13.0 — 2026-08-31

### Changed

- `get_playbook_attacks` and `get_playbook_attacks_by_tags` now default to Validate-scope,
  published attacks, so the reported total matches the Playbook UI beside it. Two new optional
  filters control the scope: `test_type` (`validate` default, `propagate`, or `all`) and
  `include_drafts` (default `False`). Both apply before pagination so the total self-corrects,
  and both disclose what they excluded through `hint_to_agent` rather than hiding it silently.
  **Behaviour change**: the default result set narrows twice — a consumer asserting the old
  merged total will see a different number. The schema stays compatible (both params optional)
- `test_type='all'` renders a split total (Validate vs Propagate) and marks Propagate and draft
  rows as unreachable from the Playbook. `get_playbook_attack_details` carries the same markers

### Fixed

- Two `TypeError` crashes on a null attack description in the playbook render blocks. A missing
  API description arrives as `None` rather than absent, so `dict.get`'s default never fired

## 1.12.0 — 2026-08-31

### Changed

- Migrated integration-discovery tools into the Config server

## 1.11.0 — 2026-08-18

### Changed

- Quick Run tests are now named after the attack, matching the Playbook UI

## 1.10.1 — 2026-08-04

### Fixed

- `get_tests` accepts `status_filter='paused'` again. The status allowlist added in 1.10.0 was
  built from the documented values and omitted `paused`, which had worked by pass-through before —
  the call then failed immediately with a validation error, regardless of whether a paused test
  existed. Note that pause state is authoritative in the orchestrator, so if a console's test-list
  API does not report `paused`, the filter may return no rows rather than an error; that case needs
  a separate orchestrator-backed fix
- `get_scenarios` no longer fails outright when a scenario or custom plan has a null `steps` field.
  Such a record is now listed as a scenario with zero steps (`step_count: 0`) instead of raising a
  `TypeError` that discarded the entire scenario catalog for the console

## 1.10.0 — 2026-07-30

### Added

- `get_tests` now includes tests waiting in the orchestrator execution queue: a fresh
  (never-cached) queue snapshot is merged on every call that could match non-terminal tests.
  Queued entries carry `status='queued'`, `queue_position` (1-based), and `queued_time`
  (submission time), are pinned to the top of the first page (newest submission first), and
  the response includes `queued_tests_count`
- New `'queued'` value for the `get_tests` `status_filter` — slotted-but-still-preparing
  (PENDING) tests are normalized to `'queued'` as well; `status_filter` values are now
  explicitly validated with a clear error listing allowed options
- `get_tests` warns via `hint_to_agent` when the orchestrator queue is paused (queued tests
  will not start until the queue is resumed)

### Fixed

- Capped the `mcp` SDK dependency below 2.0 (`mcp>=1.10.0,<2.0.0`) — mcp 2.x removed
  `mcp.server.fastmcp`, which crashed all servers on first import for fresh standalone installs

## 1.9.0 — 2026-07-29

### Changed

- The playbook MCP server no longer exposes the tag write tools — add, remove and rename a
  custom tag on a playbook attack, plus the three bulk variants. Tag mutation is unsupported
  backend-side, so these are withdrawn until that support returns. The playbook server now
  advertises four tools instead of ten.
- The read-only tag tools, `get_playbook_attack_tags` and `get_playbook_attacks_by_tags`, are
  unaffected and remain available.
- Release tooling now regenerates `uv.lock` when bumping the version.

## 1.8.0 — 2026-07-20

### Added

- New playbook tag tools: add, remove, and rename a custom tag on a playbook attack
  (the playbook server's first write tools; rate-limited and consent-gated).
- Bulk tag tools: add, remove, or rename tags across many attacks in one call, with
  hard guardrail caps (≤50 attacks, ≤20 tags) and partial-failure reporting.
- `get_playbook_attack_tags`: retrieve the custom tags on a given playbook attack.
- `get_playbook_attacks_by_tags`: find playbook attacks filtered by one or more custom tags.
- Account-wide and by-tag simulation search: `get_simulations` can now search across all
  tests (omit the test id) and filter by tag.

### Changed

- Renamed `get_test_simulations` to `get_simulations`: the test id is now optional, a `tags`
  filter was added, and all filters (status, attack id/name, time window, drift, tags) are
  applied server-side with server-side pagination. The former `get_simulation_results_by_tags`
  tool is removed (superseded by `get_simulations`).
- Lowered the bulk tag guardrail cap from 100 to 50 attacks per call.

### Fixed

- `get_studio_attack_latest_result`: the test overview status is now reported in lowercase
  (e.g. `completed`) to match the documented status values, instead of the backend's raw uppercase.

## 1.7.0 — 2026-07-08

### Fixed

- Concurrency limiter no longer lets one caller starve every MCP server at once: the per-caller limit bucket is now
  namespaced per server, so heavy load (or a tool-refresh fan-out) on one server no longer rate-limits the others. The
  long-lived streamable-HTTP GET stream is also no longer counted against the limit.

## 1.6.0 — 2026-07-07

### Added

- `get_test_drifts` can now compare any two arbitrary/non-consecutive test runs via `baseline_test_id`,
  with configurable join options (`include_baseline_only`, `include_current_only`, `include_no_results`).
  Each drift carries inline attack identity, and run-exclusive simulations are summarized per attack. (SAF-33124)
- `get_test_details` now surfaces the security-event correlation phase in test status. (SAF-32063)

### Changed

- `get_test_drifts`: `total_drifts` now counts genuine status transitions only (run-exclusive simulations
  no longer inflate the headline), and no-result/internal_fail transitions are included by default. (SAF-33124)
- Per-agent concurrency limiting is now keyed per-JWT instead of per shared mcp-session-id. (SAF-31903)
- Scenario guidance now steers agents to run non-ready scenarios via `step_overrides` / `ready_to_run_filter`
  rather than concluding none are runnable. (SAF-32210)
- Renamed run semantics for clarity: the `dry_run` parameter is now `evaluate` (previewed runs report an
  `evaluating` status), and the `run_adhoc_scenario` tool is now `quick_run`.

### Fixed

- Corrected stale running-test simulation counts in `get_test_details`. (SAF-32018)
- Fixed playbook attack id/name simulation filters (wrong key and int/str type mismatch). (SAF-32805)

## 1.5.0 — 2026-06-21

### Added

- Paginated, filterable simulation logs via two new read-only data tools backed by the data v3
  `/simulationLogs` endpoint:
  - `get_paginated_simulation_logs` — fetch one simulation's logs incrementally and filtered by
    level/type/time/message, page by page. Use it only when the simulation object and steps
    (`get_test_simulation_details`) aren't enough; pull smartly by severity (errors first for failed
    simulations). `get_full_simulation_logs` remains for the full embedded blob / old-format sims.
  - `search_simulation_logs` — cross-simulation / fleet-wide log search (e.g. "every ERROR
    containing X in the last day"); pass a pipe-delimited `simulation_ids` list or omit it to
    search all simulations.
  - Filters: `min_level` (threshold) or explicit `levels`, `message_contains`, `start_time`/
    `end_time`, `log_type` (LOGS/OUTPUT/ALL), `sort_order`, and `node_id` (scope to a single
    simulator node — e.g. only the attacker or only the target node of a dual-script attack);
    offset pagination via `page`/`page_size` (max 1000) returning
    `{ logs, total, total_capped, page, page_size, has_more }`. Results cached ~10 minutes.
  - `total_capped` (bool): Elasticsearch caps `total` at 10,000, so for large cross-simulation
    searches `total` is a **lower bound**, not exact. `total_capped=true` signals this explicitly
    (with a `hint_to_agent`) so consumers don't report a capped total as the real count.

### Changed

- `get_test_simulation_details` now returns a **curated hybrid result** (logs excluded): the
  previous flat snake_case envelope (simulation_id, status, attacker/target nodes, attack info,
  result_details) PLUS a new `simulation_steps_by_node` field — the per-node execution steps
  (each tagged `role` = attacker/target/host, with `task_status`/`error`) that form the forensic
  middle tier — and a snake_case `logs_embedded` routing flag. The heavy per-node LOGS/OUTPUT
  blobs and the raw v3 document are NOT relayed. This makes it the primary investigation entry
  point — inspect the result + steps first, and only escalate to `get_paginated_simulation_logs`
  when they aren't enough (or `get_full_simulation_logs` when `logs_embedded=true`). Optional
  enrichments (MITRE techniques, basic attack logs, drift info) are merged into the envelope.
  Falls back to the curated list-API summary (empty `simulation_steps_by_node`) on older consoles
  without the v3 endpoint.
  **Shape change:** the curated snake_case fields (e.g. `simulation_id`, `status`) are preserved;
  `simulation_steps_by_node` and `logs_embedded` are added.
  Also now returns a graceful `{error, simulation_id, hint_to_agent}` when the simulation id does
  not exist on the console (e.g. an id from a different console) instead of raising an `IndexError`.
- `get_full_simulation_logs` now fetches via the data v3 result endpoint with `includeLogs=true`
  (falling back to v1 on older consoles) and exposes a new `logs_embedded` field: `true` means an
  old-format simulation whose logs exist only in the embedded blob (not in the logs index) — for
  those, use this tool rather than the paginated/search logs tools, which will return empty.
  Its description was rewritten to steer agents correctly: call it **only** when `logs_embedded=true`
  (the previous wording told agents to "always retrieve" logs for `stopped`/`no-result` simulations,
  causing them to over-call it and dump ~40KB into context when filtered `get_paginated_simulation_logs`
  would answer in a few lines).

## 1.4.0 — 2026-06-18

### Changed

- `run_studio_attack` now queues a test with its `draft` flag matching the attack's publication status: PUBLISHED attacks are queued
  with `draft=False` so the run is discoverable in Test Results (parity with a UI quick-run); DRAFT attacks are queued with
  `draft=True` and the response includes a hint to publish first.

### Fixed

- Outbound backend authentication is now resolved solely from the live MCP request instead of a ContextVar. This prevents a
  stale/expired token captured from an earlier request (under streamable-http transport) from being sent to the backend and causing
  401 errors ~15 minutes after a (re)start.

## 1.3.0 — 2026-05-21

### Added

- Ad-hoc attack execution via `run_adhoc_scenario` — run specific playbook attacks by ID with simulator targeting,
  dry-run preview, and per-attack override support

## 1.2.0 — 2026-05-18

### Added

- Delete historic test results via `manage_test` with storage impact preview — see how much space will be freed
  before committing
- See who launched each test with the new `launched_by` field in `get_tests` and `get_test_details`, plus filter
  test history by user
- Rate limiting for write operations to prevent accidental bulk actions
- Automated release preparation workflow via `/mcp-create-release`
- Test overview context in `get_studio_attack_latest_result` — see test status, duration, and simulation breakdown
  at a glance

### Changed

- `get_tests_history` renamed to `get_tests` — now also supports filtering for currently running tests
- Rate limiting is off by default and opt-in for deployments that need it
- `manage_test` lifecycle actions (pause, resume, cancel) now verify current state before acting, preventing
  conflicting operations

### Fixed

- Reduced false positive security alerts in CI scanning

## 1.1.0 — 2026-05-07

### Added

- Multi-server MCP architecture with domain-specific servers: Config (port 8000), Data (port 8001),
  Utilities (port 8002), Playbook (port 8003), Studio (port 8004)
- External connection support with Bearer token authentication and localhost bypass
- SSE and Streamable HTTP transport modes
- Playbook attack filtering by MITRE ATT&CK techniques/tactics and attacker/target platform
- Drift analysis tools: test-run-centric (`get_test_drifts`) and time-window-based
  (`get_simulation_result_drifts`, `get_simulation_status_drifts`)
- Scenario execution (`run_scenario`) with three-turn augmentation workflow, dry-run mode,
  step overrides, and constraint diagnostics
- Test lifecycle management (`manage_test`) for pause, resume, and cancel operations
- Per-user RBAC enforcement across all MCP servers
- Peer benchmark scoring (`get_peer_benchmark_score`) with industry comparison
- Full simulation log retrieval (`get_full_simulation_logs`) for forensic analysis
- Bounded TTL caching (`SafeBreachCache`) with per-type LRU eviction and background monitoring
- Pluggable secret provider interface (AWS SSM, AWS Secrets Manager, environment variables)
- Dynamic environment loading via `SAFEBREACH_ENVS_FILE` and `SAFEBREACH_LOCAL_ENV`
- Concurrent multi-server launcher (`start_all_servers.py`)
- Security scanning CI workflow (Gitleaks, TruffleHog, GitGuardian, detect-secrets)
