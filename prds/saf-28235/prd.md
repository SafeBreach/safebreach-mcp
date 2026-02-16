# Studio MCP Server — Requirements

## Objective

Add a new MCP server — the **Studio Server** — that enables AI agents to author, validate, manage, and execute
custom Python-based **attacks** through SafeBreach Breach Studio.

## Terminology

- **Attack** — the authored artifact: Python code with OS constraints and parameters, created in Breach Studio
- **Test** — a collection of attacks executed together in one or more **Steps**
- **Simulation** — the runtime result of executing an attack within a test

The Studio Server is an **attack authoring** tool. It creates and manages attacks. When an attack is run,
it executes as part of a test and produces simulations as results.

## Motivation

Today, creating custom attacks in Breach Studio requires manual work by security engineers through the SafeBreach UI.
By exposing Studio operations as MCP tools, an AI agent becomes an attack developer — an operator can describe an
attack scenario in natural language (e.g., _"Create an attack that exfiltrates data over DNS on Windows"_) and the
agent handles authoring, validation, saving, and execution.

## User Flows

The following flows describe how an AI coding agent would use the MCP tools to develop and iterate on custom attacks.
They represent the primary interaction patterns the tool set must support.

### Flow 1: Create a New Attack

The agent authors a new custom attack from a natural language description.
**Always start from the boilerplate** — the recommended paradigm is "start from template, then customize."

```
1. create_new_studio_attack → get boilerplate code for the chosen attack type
2. Customize the code          (agent modifies boilerplate based on user's scenario)
3. validate_studio_code     → validate syntax, signature, OS constraints, parameters
4. Fix validation errors       (agent iterates on code until validation passes)
5. save_studio_attack_draft → save as draft with attack type, OS constraints, and parameters
```

The agent must choose the correct **attack type** (Host, Exfil, Infil, Lateral) based on the scenario.
Attack type accepts case-insensitive values and aliases (e.g., "exfiltration" → "exfil",
"lateral_movement" → "lateral"). For dual-script attacks (Exfil, Infil, Lateral), the boilerplate
provides both target and attacker script templates, each implementing the
`def main(system_data, asset, proxy, *args, **kwargs):` signature.

### Flow 2: Edit an Existing Attack

The agent modifies a previously saved draft attack.

```
1. get_all_studio_attacks       → list attacks, identify the one to edit
2. get_studio_attack_source     → retrieve current source code (target + attacker)
3. Modify the code                 (agent edits based on user request)
4. validate_studio_code         → validate the modified code
5. update_studio_attack_draft   → save the updated draft
```

### Flow 3: Run and Analyze Results

The agent executes an attack and interprets simulation outcomes. Running requires **explicit simulator
selection** — the agent must choose which simulators to execute on.

```
1. get_console_simulators            → (Config Server) list available simulators, filter by OS/status
2. Select simulators:
   - Host attacks: choose target simulator(s)
   - Network attacks: choose attacker simulator(s) AND target simulator(s)
   - Only **connected** simulators can execute — disconnected simulators will produce no results
   - Simulators must match the attack's OS constraints (WINDOWS, LINUX, MAC)
   - "All connected" is available but NOT the default — the agent should be explicit
3. run_studio_attack              → queue a test with attack ID + simulator IDs; obtain a test ID
4. get_studio_attack_latest_result → poll the test ID to completion, then retrieve simulation results
5. Analyze results:
   a. Check finalStatus per simulation (missed, stopped, prevented, detected, logged, no-result, inconsistent)
   b. Review resultDetails for outcome descriptions
   c. For multi-parameter attacks: compare results across parameter permutations
   d. For dual-script attacks: examine per-node results (attacker vs target)
```

**Simulation result statuses:**

| Status | Meaning |
|--------|---------|
| `missed` | Attack succeeded — security controls did not detect or block it |
| `stopped` | Attack was blocked by a security control before execution |
| `prevented` | Attack was blocked during execution by a security control |
| `reported` | Attack executed but was detected and reported by a security control |
| `logged` | Attack executed and was logged but not actively blocked |
| `no-result` | Execution did not produce a result (timeout, error, etc.) |

### Flow 4: Debug and Iterate

The agent uses detailed simulation logs to diagnose issues, fix code, and re-run.

When `get_studio_attack_latest_result` returns a problematic status (`stopped` or `no-result`),
the response includes a **debug hint** pointing the agent to `get_full_simulation_logs` on the
Data Server for comprehensive execution traces (~40KB). This breadcrumb pattern prevents the agent
from satisficing — stopping at surface-level logs and speculating about root cause.

```
1. get_studio_attack_latest_result → retrieve detailed results including:
   - SIMULATION_STEPS: step-by-step execution trace with timestamps and log levels
   - LOGS: raw simulator debug logs (contains nodeNameInMove for dual-script attacks)
   - OUTPUT: process stdout/stderr from execution
   - DEBUG HINT: for "stopped"/"no-result" statuses, a pointer to get_full_simulation_logs
2. get_full_simulation_logs → retrieve role-based comprehensive logs:
   - Returns `target` node data (always present) and `attacker` node data (dual-script only, null for host)
   - Each role contains: logs (~40KB), simulation_steps, error, output, os_type, os_version, state
   - For dual-script attacks: both nodes' logs are available — diagnose which node failed
3. Diagnose the issue:
   - Syntax/runtime errors visible in OUTPUT and LOGS per role (target vs attacker)
   - Execution flow visible in SIMULATION_STEPS (STATUS, DEBUG, INFO, WARNING, ERROR levels)
   - For dual-script attacks: compare target.logs vs attacker.logs to identify which node failed
   - For "stopped"/"no-result": the failing node's error and logs pinpoint root cause
4. get_studio_attack_source         → retrieve current code
5. Fix the code                        (agent patches based on log analysis)
6. validate_studio_code             → validate the fix
7. update_studio_attack_draft       → save the updated draft
8. run_studio_attack                → re-run with same simulators to verify the fix
9. get_studio_attack_latest_result  → confirm improved results
```

This debug loop — **run → analyze logs → fix code → validate → update → re-run** — is the core
inner loop for attack development. The MCP tools must provide enough detail in simulation results
for the agent to diagnose failures without requiring the user to inspect logs manually.

### Flow 5: Publish or Unpublish an Attack

The agent transitions an attack between DRAFT and PUBLISHED states. This flow requires
explicit user confirmation before execution due to production impact.

```
1. get_all_studio_attacks              → list attacks, identify the target attack and its current status
2. Confirm with user                      (agent MUST get explicit approval before status change)
3. set_studio_attack_status            → publish or unpublish the attack
4. Verify transition:
   - Publish: get_playbook_attacks     → (Playbook Server) confirm attack appears in Playbook
   - Unpublish: get_studio_attack_source → confirm attack is editable, proceed with modifications
```

**Publish workflow** (DRAFT → PUBLISHED): After development and testing are complete, the attack
is promoted to production. It becomes read-only on the console and available in SafeBreach Playbook.

**Unpublish workflow** (PUBLISHED → DRAFT): When a published attack needs modifications, it must
be unpublished first. After changes are made via `update_studio_attack_draft`, it can be
re-published.

## Requirements

### 1. Attack Types

The server must support all four SafeBreach custom attack types:

| methodType | Type | Scripts | Description |
|------------|------|---------|-------------|
| 0 | Exfiltration | target.py + attacker.py | Data exfiltration from target to attacker |
| 1 | Lateral Movement | target.py + attacker.py | Movement between hosts |
| 2 | Infiltration | target.py + attacker.py | Data infiltration from attacker to target |
| 5 | Host | target.py only | Executes on a single host |

**Dual-script attacks** (Exfil, Infil, Lateral) involve two simulator nodes — attacker and target — each running
its own Python script. **Host attacks** execute a single script on one simulator.

Each script must define the required function signature:
`def main(system_data, asset, proxy, *args, **kwargs):`

### 2. Code Validation and Linting

Validation is **two-tier**: local checks run first (fast, no API call), then backend API validation runs
for Python code quality (Pylint-style analysis by the SafeBreach backend).

#### Tier 1 — Local Validation (upfront, before API call)

These checks prevent common mistakes before making a round-trip to the backend:

- **Function signature (AST-based)**: Each script must define `def main(system_data, asset, proxy, *args, **kwargs):`.
  Validated using `ast.parse()` to verify the exact parameter names, `*args`, and `**kwargs` — not just a regex
  pattern match. This catches code like `def main(x, y, z, *args, **kwargs):` that matches the regex but fails
  at runtime.
- **Syntax**: Verify code compiles without errors (`compile()`)
- **OS constraints**: Validate target/attacker OS selection — `All`, `WINDOWS`, `LINUX`, `MAC`
- **Attack type consistency**: Validate that dual-script attacks provide both target and attacker code
- **Parameter structure**: Validate required fields (name, value), valid types, PORT range, PROTOCOL values
- **Parameter name validity** (`SB011`): Each parameter name must be a valid Python identifier
  (`str.isidentifier()`). AI agents may generate names like `my-param` or `2nd_attempt` that fail at runtime.
- **Duplicate parameter names** (`SB012`): No two parameters may share the same name. AI agents
  generating parameter lists may accidentally repeat names.

#### Tier 2 — Backend API Validation (SafeBreach server-side)

After local checks pass, submit code to the SafeBreach validation endpoint:

- `PUT /api/content/v1/accounts/{account_id}/customMethods/validate`
- Returns Pylint-style error codes (E=error, W=warning, F=fatal, C=convention, R=refactor)
- For dual-script attacks: validate target.py and attacker.py independently
- This catches code quality issues (unused imports, broad exceptions, naming conventions, etc.)
  that local validation cannot detect

#### Design Rationale

The VS Code extension (`/Users/yossiattas/projects/vsextension/`) implements 17 local lint rules
(SB001-SB068) for parameter validation because human developers edit raw `parameters.json` files.
In the MCP context, the AI agent passes structured parameters through the tool interface, so most
structural validations (JSON shape, required fields, type enums, PORT range, PROTOCOL values) are
handled by the existing `_validate_and_build_parameters()` function as **upfront validation**.

Only SB011 (Python identifier) and SB012 (duplicate names) are kept as explicit lint checks because
these are mistakes AI agents can realistically make despite structured input.

### 3. Parameter Support

Attacks may define configurable parameters that create **simulation permutations** — each unique combination of
parameter values produces a distinct simulation when the attack is run
(e.g., 2 values x 3 values = 6 simulations).

**Parameter Sources:**

| Source | Description |
|--------|-------------|
| `PARAM` | Simple text/string values stored directly in the parameter |
| `FEED` | Binary files stored in SafeBreach feeds, referenced by UUID |

**Parameter Types:**

| Type | Source | Validation |
|------|--------|------------|
| `NOT_CLASSIFIED` | PARAM | No specific validation |
| `PORT` | PARAM | Must be integer in range 1-65535 |
| `URI` | PARAM | Format checking for URI values |
| `PROTOCOL` | PARAM | Must be a recognized protocol (HTTP, HTTPS, SSH, RDP, DNS, etc. — 50+ supported) |
| `BINARY` | FEED | Binary file referenced by feed UUID |

**Multi-value parameters**: Parameters that accept lists of values, contributing to simulation permutations.

### 4. Draft Management

The server must support the full lifecycle of attack drafts:

- **Save** — Create new draft attacks with code, OS constraints, attack type, and parameters
- **Update** — Modify existing drafts (code, metadata, parameters)
- **List** — Retrieve all studio attacks with filtering support
- **Retrieve source** — Fetch the source code of any saved attack (both target and attacker scripts)
- **Publish/Unpublish** — Transition attacks between DRAFT and PUBLISHED states

#### Attack Status Model

Studio attacks have two statuses:

| Status | Editable | In Playbook | Execution |
|--------|----------|-------------|-----------|
| **DRAFT** | Yes | No | Requires `"draft": true` flag |
| **PUBLISHED** | No (read-only) | Yes | Standard execution |

- **DRAFT → PUBLISHED**: Attack becomes read-only on the console, appears in SafeBreach Playbook
  for production test scenarios
- **PUBLISHED → DRAFT**: Attack becomes editable again, removed from Playbook, requires
  `"draft": true` flag to execute

**Implementation**: There are no dedicated `/publish` or `/unpublish` API endpoints. Status
transitions are performed via the standard PUT update endpoint (`/customMethods/{id}`) with the
`status` field changed in the multipart form-data payload. The function fetches the current attack
data and source code, then re-submits everything with only the `status` field changed. This matches
the VS Code extension's implementation.

Status transitions require explicit user confirmation due to their production impact.

### 5. Attack Execution

The server must support running attacks and retrieving simulation results:

- **Execute** — Queue a test comprised of the attack ID and explicit simulator selection:
  - **Host attacks**: accept target simulator ID(s)
  - **Network attacks**: accept attacker simulator ID(s) and target simulator ID(s)
  - **All connected** mode available but **actively discouraged** — tool description steers the agent
    toward explicit simulator selection, and using `all_connected=True` triggers a warning in the response
    advising the agent to use explicit IDs next time (reduces noise on the SafeBreach platform)
  - Returns a test ID for tracking
- **Results** — Retrieve simulation results with optional `test_id` filter:
  - Without `test_id`: queries latest results for the attack across all test runs
  - With `test_id`: filters to results from a specific test run (returned by `run_studio_attack`)
  - For problematic statuses (`stopped`, `no-result`), response includes a **debug hint** pointing
    to `get_full_simulation_logs` on the Data Server for comprehensive execution traces
  - Note: `missed` is NOT a problematic status — it means the attack achieved its success criteria
    without being detected or blocked by a security control (best possible outcome)

Simulator discovery is handled by the Config Server's existing `get_console_simulators` tool.
The agent is expected to query available simulators, filter for **connected** simulators that match
the attack's OS constraints, and pass specific IDs to the run tool. Only connected simulators can
execute simulations — selecting disconnected simulators will produce no results.

### 6. Integration

The Studio Server must integrate with the existing multi-server architecture:

- **Port 8004** on the multi-server launcher
- **Extends `SafeBreachMCPBase`** — reuse shared auth, caching, error handling
- **External connection support** — opt-in with Bearer token authentication
- **Entry point** — registered in `pyproject.toml` as `safebreach-mcp-studio-server`

### 7. MCP Tools

Nine tools exposed to AI agents:

| Tool Name (MCP) | Python Function | Description |
|------------------|-----------------|-------------|
| `create_new_studio_attack` | `sb_get_studio_attack_boilerplate` | Get boilerplate code for a new attack (recommended starting point) |
| `validate_studio_code` | `sb_validate_studio_code` | Validate Python attack code (two-tier: local + backend) |
| `save_studio_attack_draft` | `sb_save_studio_attack_draft` | Save a new attack as a Breach Studio draft |
| `get_all_studio_attacks` | `sb_get_all_studio_attacks` | List studio attacks with filtering and pagination |
| `update_studio_attack_draft` | `sb_update_studio_attack_draft` | Update an existing draft attack |
| `get_studio_attack_source` | `sb_get_studio_attack_source` | Retrieve saved attack source code |
| `run_studio_attack` | `sb_run_studio_attack` | Queue a test for the attack with explicit simulator selection |
| `get_studio_attack_latest_result` | `sb_get_studio_attack_latest_result` | Get latest simulation results with optional `test_id` filter |
| `set_studio_attack_status` | `sb_set_studio_attack_status` | Publish or unpublish an attack (DRAFT ↔ PUBLISHED transition) |

> **Naming convention**: Tool names registered with MCP use **no prefix** (e.g., `validate_studio_code`),
> matching the pattern in Config (`get_console_simulators`), Data (`get_tests_history`), and Playbook
> (`get_playbook_attacks`). The `sb_` prefix is used only on internal Python function names.

### 8. Testing

**245 unit tests** covering:

- All four attack types (Host, Exfil, Infil, Lateral) including dual-script validation
- Validation logic (syntax, function signatures, OS constraints, attack type consistency)
- Two-tier linting (SB011 Python identifier check, SB012 duplicate name check, backend API validation)
- Parameter validation (all types: PORT, URI, PROTOCOL, NOT_CLASSIFIED, BINARY/FEED)
- Simulation permutation logic (multi-value parameter combinations)
- Draft management operations (save, update, list, retrieve)
- Status transitions (publish/unpublish via PUT update)
- Attack execution and simulation result retrieval
- Pagination for list attacks (page_number, PAGE_SIZE, hint_to_agent)
- Cross-server entity naming consistency (attack_id, test_id, simulation_id)
- Caching behavior and cache invalidation on status change
- Error handling and edge cases

**13 E2E tests** (require real SafeBreach environment) covering:

- Code validation (valid host code, invalid code, SB011 lint check)
- Attack listing (basic retrieval, pagination, filtering by status/name)
- Source code retrieval (content structure, target + attacker files)
- Draft lifecycle (create → update roundtrip)
- Execution (run attack, retrieve latest result)
- Debug flow (run → analyze logs → iterate)
- Status transition (draft → published → verify → unpublished → verify roundtrip)

**497 cross-server tests** (all servers combined, excluding E2E).

## Implementation Details

### Implementation Status

The Studio Server implementation is **complete** on the `studio-mcp` branch. All 9 MCP tools are
implemented and tested with 245 unit tests and 13 E2E tests (36 E2E tests across all servers).

All naming has been migrated from the original "simulation"-based naming to "attack"-based
terminology consistent with the Playbook and Data servers. The multi-server launcher
(`start_all_servers.py`) and `pyproject.toml` are configured — port 8004, entry point, and
package discovery are in place.

### Existing Constants

Already defined in `studio_functions.py`:

```python
VALID_OS_CONSTRAINTS = {"All", "WINDOWS", "LINUX", "MAC"}        # Case-insensitive input accepted
VALID_PARAMETER_TYPES = {"NOT_CLASSIFIED", "PORT", "URI", "PROTOCOL"}
VALID_PROTOCOLS = {"BGP", "BITS", "BOOTP", "DHCP", "DNS", "DROPBOX", "DTLS", "FTP",
    "HTTP", "HTTPS", "ICMP", "IMAP", "IP", "IPSEC", "IRC", "KERBEROS",
    "LDAP", "LLMNR", "mDNS", "MGCP", "MYSQL", "NBNS", "NNTP", "NTP",
    "POP3", "RADIUS", "RDP", "RPC", "SCTP", "SIP", "SMB", "SMTP",
    "SNMP", "SSH", "SSL", "SSDP", "STUN", "SYSLOG", "TCP", "TCPv6",
    "TDS", "TELNET", "TFTP", "TLS", "UDP", "UTP", "VNC", "WEBSOCKET",
    "WHOIS", "XMLRPC", "XMPP", "YMSG"}

VALID_ATTACK_TYPES = {
    "host": 5,       # Host — target.py only
    "exfil": 0,      # Exfiltration — target.py + attacker.py
    "infil": 2,      # Infiltration — target.py + attacker.py
    "lateral": 1,    # Lateral Movement — target.py + attacker.py
}
DUAL_SCRIPT_TYPES = {"exfil", "infil", "lateral"}

# Case-insensitive aliases for attack types — normalized via _normalize_attack_type()
ATTACK_TYPE_ALIASES = {
    "exfiltration": "exfil",
    "infiltration": "infil",
    "lateral_movement": "lateral",
    "lateral-movement": "lateral",
    "host-level": "host",
    "host_level": "host",
}
```

### API Endpoints

All endpoints use `x-apitoken` header for authentication and 120-second timeout.

| Operation | Method | URL |
|-----------|--------|-----|
| Validate | PUT | `/api/content/v1/accounts/{account_id}/customMethods/validate` |
| Save draft | POST | `/api/content/v1/accounts/{account_id}/customMethods` |
| Update draft | PUT | `/api/content/v1/accounts/{account_id}/customMethods/{id}` |
| List all | GET | `/api/content/v1/accounts/{account_id}/customMethods?status=all` |
| Get source (target) | GET | `/api/content/v1/accounts/{account_id}/customMethods/{id}/files/target` |
| Get source (attacker) | GET | `/api/content/v1/accounts/{account_id}/customMethods/{id}/files/attacker` |
| Publish/Unpublish | PUT | `/api/content/v1/accounts/{account_id}/customMethods/{id}` (same as Update, with `status` field changed) |
| Run (queue test) | POST | `/api/orch/v4/accounts/{account_id}/queue` |
| Get results | POST | `/api/data/v1/accounts/{account_id}/executionsHistoryResults` |

### Save/Update API Payload Format

Multipart form-data with these fields:

```
name:           attack name
timeout:        seconds (string)
status:         "draft" | "published"  (used for publish/unpublish transitions)
class:          "python"
description:    text
parameters:     JSON string of parameter array
tags:           "[]"
methodType:     "0"|"1"|"2"|"5" (from VALID_ATTACK_TYPES)
targetFileName: "target.py"
metaData:       JSON string with filenames

# File parts:
targetFile:     (target.py, code, text/x-python-script)
attackerFile:   (attacker.py, code, text/x-python-script)  # dual-script only

# OS constraint parts (only if not "All"):
targetConstraints:    '{"os":"WINDOWS"}'
attackerConstraints:  '{"os":"LINUX"}'  # dual-script only
```

### Run API Payload Format

```json
{
  "plan": {
    "name": "test name",
    "steps": [{
      "attacksFilter": {
        "playbook": {"operator": "is", "values": [attack_id], "name": "playbook"}
      },
      "attackerFilter": {
        "simulators": {"operator": "is", "values": ["uuid1"], "name": "simulators"}
      },
      "targetFilter": {
        "simulators": {"operator": "is", "values": ["uuid2"], "name": "simulators"}
      },
      "systemFilter": {}
    }],
    "draft": true
  }
}
```

For "all connected" mode, replace simulator filters with:
```json
{"connection": {"operator": "is", "values": [true], "name": "connection"}}
```

### Results API Query Format

```json
{
  "page": 1,
  "runId": "*",
  "pageSize": 100,
  "query": "Playbook_id:(\"attack_id\")",
  "orderBy": "desc",
  "sortBy": "startTime"
}
```

When `test_id` is provided, the query appends `AND runId:{test_id}` to filter results to a specific
test execution.

### Internal Helpers

- `_normalize_attack_type(attack_type)` — lowercases, resolves aliases, validates against `VALID_ATTACK_TYPES`
- `_validate_os_constraint(os_constraint)` — case-insensitive validation, returns canonical case value
- `_validate_main_signature_ast(code, label)` — AST-based main function signature validation
- `_validate_and_build_parameters(parameters)` — validates types/values, builds API JSON
- `_get_draft_from_cache(cache_key)` — cache retrieval with TTL check
- All `studio_types.py` transformation functions
- `studio_templates.py` — boilerplate code templates for all attack types

### Integration

- `start_all_servers.py` — imports `SafeBreachStudioServer`, port 8004, `--external-studio` flag
- `pyproject.toml` — `safebreach-mcp-studio-server` entry point and `safebreach_mcp_studio*` package

## Cross-Server Consistency Alignment

The Studio Server is consistent with the vocabulary, naming conventions, and patterns used by the
existing Config, Data, Playbook, and Utilities servers.

### 1. Tool Name Convention (no `sb_` prefix)

All servers register tools **without** the `sb_` prefix. The `sb_` prefix is only for internal
Python function names.

| Server | Tool Name | Python Function |
|--------|-----------|-----------------|
| Config | `get_console_simulators` | `sb_get_console_simulators` |
| Data | `get_tests_history` | `sb_get_tests_history` |
| Playbook | `get_playbook_attacks` | `sb_get_playbook_attacks` |
| **Studio** | `validate_studio_code` | `sb_validate_studio_code` |

### 2. Entity ID Naming — `attack_id` not `simulation_id`

Studio uses `attack_id` for the custom method ID, consistent with Playbook server's `attack_id: int`
and avoiding conflict with Data server's `simulation_id` (which means a runtime execution result).

| Context | Name | Type | Rationale |
|---------|------|------|-----------|
| Custom method (authored artifact) | `attack_id` | `int` | Matches Playbook `attack_id`; avoids Data `simulation_id` clash |
| Test execution run | `test_id` | `str` | Matches Data `test_id` (same as API `planRunId`) |
| Runtime simulation result | `simulation_id` | `str` | Matches Data `simulation_id` |
| Draft to update | `attack_id` | `int` | Not `draft_id` — the status is a property, not part of the ID |

### 3. Run Result Returns `test_id`

`run_studio_attack` returns `test_id`, matching the Data server's parameter name in `get_test_details`,
`get_test_simulations`, and `get_full_simulation_logs`. This enables seamless cross-server workflows:

```
run_studio_attack → returns test_id
get_test_details(test_id=...) → Data server
get_test_simulations(test_id=...) → Data server
```

### 4. Pagination for List Tool

All list tools use consistent pagination with `page_number: int = 0`, `PAGE_SIZE = 10`, and
`hint_to_agent`:

| Server | Tool | Pattern |
|--------|------|---------|
| Data | `get_tests_history` | `page_number: int = 0`, `PAGE_SIZE = 10`, returns `hint_to_agent` |
| Playbook | `get_playbook_attacks` | `page_number: int = 0`, `PAGE_SIZE = 10`, returns `hint_to_agent` |
| **Studio** | `get_all_studio_attacks` | `page_number: int = 0`, `PAGE_SIZE = 10`, returns `hint_to_agent` |

Return structure:
```python
{
    "attacks_in_page": [...],
    "total_attacks": int,
    "page_number": int,
    "total_pages": int,
    "draft_count": int,
    "published_count": int,
    "applied_filters": {...},
    "hint_to_agent": "You can scan next page by calling with page_number=1"
}
```

### 5. Simulation Result Field Names

The `get_studio_attack_latest_result` tool returns execution results from the **same API** as the Data
server (`executionsHistoryResults`). Shared fields use the same vocabulary:

| Concept | Data Server Field | Studio Field |
|---------|------------------|--------------|
| Result ID | `simulation_id` | `simulation_id` |
| Attack/playbook ID | `playbook_attack_id` | `attack_id` |
| Attack name | `playbook_attack_name` | `attack_name` |
| Test run ID | `test_id` | `test_id` |
| Result status | `status` (finalStatus) | `status` |
| Drift tracking | `drift_tracking_code` | `drift_tracking_code` |
| Security action | `security_control_action` | `security_action` |
| Attack description | `attack_plan` | `attack_description` |
| Is drifted | `is_drifted` | `is_drifted` |

The Studio result tool adds fields not present in Data (LOGS, SIMULATION_STEPS, OUTPUT) for the
debug use case.

### 6. `console` Parameter Position

Follows the existing pattern: entity ID **first**, `console` **second** for entity operations;
`console` first for list/search operations.

| Pattern | Example |
|---------|---------|
| List operations | `get_all_studio_attacks(console, page_number, ...)` |
| Entity operations | `get_studio_attack_source(attack_id, console)` |
| Entity operations | `run_studio_attack(attack_id, console, ...)` |
| Creation operations | `save_studio_attack_draft(name, python_code, ..., console)` |

### 7. Error Return Pattern

Studio follows the **raise exception** pattern (used by Data, Playbook, and most servers) — the
server layer catches and formats errors into user-facing messages.

## UX Improvements (Claude Desktop Feedback)

Based on real Claude Desktop sessions using the Studio MCP tools, the following UX improvements were
implemented to address AI agent behavior patterns:

### 1. Case-Insensitive Input Normalization

All `attack_type` and OS constraint parameters accept case-insensitive input. Attack types also accept
common aliases (e.g., `"exfiltration"` → `"exfil"`, `"lateral_movement"` → `"lateral"`). This matches
the pattern used by Config, Data, and Playbook servers (which all use `.lower()` normalization) and
eliminates unnecessary validation failures from agent-generated input.

### 2. Boilerplate-First Paradigm

The `create_new_studio_attack` tool (renamed from `get_studio_attack_boilerplate` for tool search
discoverability) returns ready-to-customize template code for each attack type. The tool name and
description are designed so that agents searching for "create attack" or "new attack" find it as the
first step. Cross-references from `save_studio_attack_draft` reinforce the pattern.

### 3. AST-Based Signature Validation

Replaced regex-based main function detection with `ast.parse()` validation that verifies exact parameter
names (`system_data`, `asset`, `proxy`), `*args`, and `**kwargs`. Catches structurally valid but
semantically wrong signatures like `def main(x, y, z, *args, **kwargs):` that pass regex but fail at
runtime.

### 4. Explicit Simulator Selection Steering

Claude Desktop preferred `all_connected=True` over explicit simulator selection, generating noise on the
SafeBreach platform. The tool description now actively steers agents toward explicit selection with a
recommended workflow. When `all_connected=True` is used, the response includes a warning advising the
agent to use explicit IDs next time.

### 5. Debug Hint Breadcrumbs

When `get_studio_attack_latest_result` returns a simulation with status `stopped` or `no-result`, the
response includes a debug hint pointing to `get_full_simulation_logs` on the Data Server. This addresses
the agent tendency to satisfice — stopping at surface-level logs and speculating about root cause instead
of retrieving comprehensive execution traces (~40KB).

### 6. test_id Result Filtering

`run_studio_attack` returns a `test_id` that can be passed to `get_studio_attack_latest_result` to filter
results to a specific test run, enabling the run → check workflow without ambiguity from prior test runs.

## Files

| File | Purpose |
|------|---------|
| `safebreach_mcp_studio/__init__.py` | Package init |
| `safebreach_mcp_studio/studio_functions.py` | Core business logic and validation |
| `safebreach_mcp_studio/studio_server.py` | MCP server and tool registration |
| `safebreach_mcp_studio/studio_types.py` | API response transformations |
| `safebreach_mcp_studio/studio_templates.py` | Boilerplate code templates for all attack types |
| `safebreach_mcp_studio/tests/test_studio_functions.py` | Unit test suite (245 tests) |
| `safebreach_mcp_studio/tests/test_e2e.py` | End-to-end test suite (13 tests) |
| `start_all_servers.py` | Multi-server launcher (already configured) |
| `pyproject.toml` | Package and entry point registration (already configured) |
