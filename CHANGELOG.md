# Changelog

All notable changes to the safebreach-mcp project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
