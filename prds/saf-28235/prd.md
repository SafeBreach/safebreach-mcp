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

```
1. Write Python code           (agent generates target.py, and attacker.py if network attack)
2. sb_validate_studio_code     → validate syntax, signature, OS constraints, parameters
3. Fix validation errors       (agent iterates on code until validation passes)
4. sb_save_studio_attack_draft → save as draft with attack type, OS constraints, and parameters
```

The agent must choose the correct **attack type** (Host, Exfil, Infil, Lateral) based on the scenario.
For dual-script attacks (Exfil, Infil, Lateral), the agent authors both target and attacker scripts,
each implementing the `def main(system_data, asset, proxy, *args, **kwargs):` signature.

### Flow 2: Edit an Existing Attack

The agent modifies a previously saved draft attack.

```
1. sb_get_all_studio_attacks       → list attacks, identify the one to edit
2. sb_get_studio_attack_source     → retrieve current source code (target + attacker)
3. Modify the code                 (agent edits based on user request)
4. sb_validate_studio_code         → validate the modified code
5. sb_update_studio_attack_draft   → save the updated draft
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
3. sb_run_studio_attack              → queue a test with attack ID + simulator IDs; obtain a test ID
4. sb_get_studio_attack_latest_result → poll the test ID to completion, then retrieve simulation results
5. Analyze results:
   a. Check finalStatus per simulation (missed, stopped, prevented, reported, logged, no-result)
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

```
1. sb_get_studio_attack_latest_result → retrieve detailed results including:
   - SIMULATION_STEPS: step-by-step execution trace with timestamps and log levels
   - LOGS: raw simulator debug logs (contains nodeNameInMove for dual-script attacks)
   - OUTPUT: process stdout/stderr from execution
2. Diagnose the issue:
   - Syntax/runtime errors visible in OUTPUT and LOGS
   - Execution flow visible in SIMULATION_STEPS (STATUS, DEBUG, INFO, WARNING, ERROR levels)
   - For dual-script attacks: identify which node (attacker/target) failed
3. sb_get_studio_attack_source         → retrieve current code
4. Fix the code                        (agent patches based on log analysis)
5. sb_validate_studio_code             → validate the fix
6. sb_update_studio_attack_draft       → save the updated draft
7. sb_run_studio_attack                → re-run with same simulators to verify the fix
8. sb_get_studio_attack_latest_result  → confirm improved results
```

This debug loop — **run → analyze logs → fix code → validate → update → re-run** — is the core
inner loop for attack development. The MCP tools must provide enough detail in simulation results
for the agent to diagnose failures without requiring the user to inspect logs manually.

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

### 2. Code Validation

The server must validate custom Python attack code before submission to the SafeBreach API:

- **Function signature**: Each script must define `def main(system_data, asset, proxy, *args, **kwargs):`
- **OS constraints**: Validate target/attacker OS selection — `All`, `WINDOWS`, `LINUX`, `MAC`
- **Syntax**: Verify code compiles without errors
- **Attack type consistency**: Validate that dual-script attacks provide both target and attacker code
- **Parameters**: Validate attack parameter definitions (types, values, ranges)
- **API validation**: After local checks pass, submit to SafeBreach for server-side validation via
  `PUT /api/content/v1/accounts/{account_id}/customMethods/validate`

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

### 5. Attack Execution

The server must support running attacks and retrieving simulation results:

- **Execute** — Queue a test comprised of the attack ID and explicit simulator selection:
  - **Host attacks**: accept target simulator ID(s)
  - **Network attacks**: accept attacker simulator ID(s) and target simulator ID(s)
  - **All connected** mode available as an option but not the default
  - Returns a test ID for tracking
- **Results** — Poll the test ID to completion, then retrieve simulation results and execution logs

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

Seven tools exposed to AI agents:

| Tool | Description |
|------|-------------|
| `sb_validate_studio_code` | Validate Python attack code (signature, syntax, constraints, parameters) |
| `sb_save_studio_attack_draft` | Save a new attack as a Breach Studio draft |
| `sb_get_all_studio_attacks` | List studio attacks with filtering |
| `sb_update_studio_attack_draft` | Update an existing draft attack |
| `sb_get_studio_attack_source` | Retrieve saved attack source code |
| `sb_run_studio_attack` | Queue a test for the attack with explicit simulator selection |
| `sb_get_studio_attack_latest_result` | Get latest simulation results and execution logs |

> **Renaming required**: The current implementation on `studio-mcp` uses `simulation`-based naming
> (e.g., `sb_get_all_studio_simulations`, `sb_run_studio_simulation`). All tool names, internal function names,
> and test references must be renamed to use `attack`-based terminology as specified above.

### 8. Testing

Comprehensive test coverage for:

- All four attack types (Host, Exfil, Infil, Lateral) including dual-script validation
- Validation logic (syntax, function signatures, OS constraints, attack type consistency)
- Parameter validation (all types: PORT, URI, PROTOCOL, NOT_CLASSIFIED, BINARY/FEED)
- Simulation permutation logic (multi-value parameter combinations)
- Draft management operations (save, update, list, retrieve)
- Attack execution and simulation result retrieval
- Caching behavior
- Error handling and edge cases

## Implementation Details

### Current State

A working Studio server already exists on the `studio-mcp` branch with Host-only (methodType 5),
single-script (target.py) support using "simulation" naming. The multi-server launcher
(`start_all_servers.py`) and `pyproject.toml` are already configured — port 8004, entry point, and
package discovery are in place. The implementation work is a **refactor and extension**, not a
greenfield build.

### What Exists (to be renamed and extended)

| Current function | Rename to | What changes |
|-----------------|-----------|--------------|
| `sb_validate_studio_code` | (same) | Add `attack_type`, `attacker_code`, `target_os`, `attacker_os`, `parameters` params |
| `sb_save_studio_draft` | `sb_save_studio_attack_draft` | Add `attack_type`, `attacker_code`, `attacker_os`; rename `os_constraint` → `target_os` |
| `sb_update_studio_draft` | `sb_update_studio_attack_draft` | Same changes as save |
| `sb_get_all_studio_simulations` | `sb_get_all_studio_attacks` | Rename only |
| `sb_get_studio_simulation_source` | `sb_get_studio_attack_source` | Add attacker.py retrieval for dual-script |
| `sb_run_studio_simulation` | `sb_run_studio_attack` | Split `simulator_ids` into `target_simulator_ids` + `attacker_simulator_ids`; add `all_connected` |
| `sb_get_studio_simulation_latest_result` | `sb_get_studio_attack_latest_result` | Add `include_logs`; extract SIMULATION_STEPS, LOGS, OUTPUT |

### Existing Constants (reuse as-is)

Already defined in `studio_functions.py`:

```python
MAIN_FUNCTION_PATTERN = r'(?<!\w)def\s+main\s*\(\s*system_data\s*,\s*asset\s*,\s*proxy\s*,\s*\*args\s*,\s*\*\*kwargs\s*\)\s*:'
VALID_OS_CONSTRAINTS = {"All", "WINDOWS", "LINUX", "MAC"}
VALID_PARAMETER_TYPES = {"NOT_CLASSIFIED", "PORT", "URI", "PROTOCOL"}
VALID_PROTOCOLS = {"BGP", "BITS", "BOOTP", "DHCP", "DNS", "DROPBOX", "DTLS", "FTP",
    "HTTP", "HTTPS", "ICMP", "IMAP", "IP", "IPSEC", "IRC", "KERBEROS",
    "LDAP", "LLMNR", "mDNS", "MGCP", "MYSQL", "NBNS", "NNTP", "NTP",
    "POP3", "RADIUS", "RDP", "RPC", "SCTP", "SIP", "SMB", "SMTP",
    "SNMP", "SSH", "SSL", "SSDP", "STUN", "SYSLOG", "TCP", "TCPv6",
    "TDS", "TELNET", "TFTP", "TLS", "UDP", "UTP", "VNC", "WEBSOCKET",
    "WHOIS", "XMLRPC", "XMPP", "YMSG"}
```

### New Constants (to add)

```python
VALID_ATTACK_TYPES = {
    "host": 5,       # Host — target.py only
    "exfil": 0,      # Exfiltration — target.py + attacker.py
    "infil": 2,      # Infiltration — target.py + attacker.py
    "lateral": 1,    # Lateral Movement — target.py + attacker.py
}
DUAL_SCRIPT_TYPES = {"exfil", "infil", "lateral"}
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
| Run (queue test) | POST | `/api/orch/v4/accounts/{account_id}/queue` |
| Get results | POST | `/api/data/v1/accounts/{account_id}/executionsHistoryResults` |

### Save/Update API Payload Format

Multipart form-data with these fields:

```
name:           attack name
timeout:        seconds (string)
status:         "draft"
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

### Existing Helpers (reuse as-is)

- `_validate_os_constraint(os_constraint)` — validates against `VALID_OS_CONSTRAINTS`
- `_validate_and_build_parameters(parameters)` — validates types/values, builds API JSON
- `_get_draft_from_cache(cache_key)` — cache retrieval with TTL check
- All `studio_types.py` transformation functions (to be renamed and extended)

### Integration Already Done (no changes needed)

- `start_all_servers.py` — already imports `SafeBreachStudioServer`, port 8004, `--external-studio` flag
- `pyproject.toml` — already has `safebreach-mcp-studio-server` entry point and `safebreach_mcp_studio*` package

## Files

| File | Purpose |
|------|---------|
| `safebreach_mcp_studio/__init__.py` | Package init |
| `safebreach_mcp_studio/studio_functions.py` | Core business logic and validation |
| `safebreach_mcp_studio/studio_server.py` | MCP server and tool registration |
| `safebreach_mcp_studio/studio_types.py` | API response transformations |
| `safebreach_mcp_studio/tests/test_studio_functions.py` | Test suite |
| `start_all_servers.py` | Multi-server launcher (already configured) |
| `pyproject.toml` | Package and entry point registration (already configured) |
