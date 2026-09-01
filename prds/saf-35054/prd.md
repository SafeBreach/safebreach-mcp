# SAF-35054 — Reduce sbmcp-proxy log volume

Ticket: https://safebreach.atlassian.net/browse/SAF-35054
Epic: https://safebreach.atlassian.net/browse/SAF-30456

## Problem

`sb-server-logs` in the central-logging prod cluster is **98.0% one service**. Measured with a 6h
aggregation against `central-logs-customers`:

```
app.keyword
  5,162,704  sbmcp-proxy      <- 98.0% of 5,269,861
    107,157  otel-agent

log.file.path.keyword
  5,162,325  /datadb/logs/sbmcp-proxy.log
```

That is 3.62 GB/day of primary ingest across 29.2M documents, at 133 bytes/doc. The stream costs a
90-day frozen retention window and 90 indices / 94 shards.

## What is in it

Three distinct sources, sampled from prod:

**1. uvicorn access log, shipped with raw ANSI colour escapes**

```
'\x1b[32mINFO\x1b[0m:     127.0.0.1:48294 - "\x1b[1mPOST /api/mcp/playbook HTTP/1.1\x1b[0m" \x1b[32m200 OK\x1b[0m'
```

The escape sequences are stored, indexed and full-text analysed. Every MCP call over the SSE/HTTP
transport produces one of these.

**2. MCP library request tracing**

```
'2026-08-16 10:33:13 - INFO: mcp.server.lowlevel.server - server.py: 733: Processing request of type ListToolsRequest'
```

Emitted by the vendored MCP SDK, not by our code.

**3. The bug-423 hotfix warning, firing continuously**

```
'2026-08-16 10:33:13 - WARNING: root - mcp_server_bug_423_hotfix.py: 63: Received request before initialization was complete: ListToolsRequest'
```

`mcp_server_bug_423_hotfix.py` patches around
https://github.com/modelcontextprotocol/python-sdk/issues/423. The handler sets
`_initialization_state = Initialized` immediately after logging (line 65), so it self-suppresses after
the first occurrence *per session*. Observing it at this volume means sessions are being created
constantly — see "Open question" below.

## Approach

Two changes, both in this repo.

### 1. `safebreach_mcp_core/safebreach_base.py` — disable the uvicorn access log

Single `uvicorn.Config` call site in the repo (line 299). Add `access_log`, defaulting to off, with an
environment escape hatch matching the existing `SAFEBREACH_MCP_*` convention used for
`SAFEBREACH_MCP_CONCURRENCY_LIMIT`, `SAFEBREACH_MCP_TRANSPORT`, `SAFEBREACH_MCP_BASE_URL`:

```python
access_log = os.environ.get('SAFEBREACH_MCP_ACCESS_LOG', 'false').strip().lower() == 'true'
config = uvicorn.Config(app=app, host=bind_host, port=port, log_level="info",
                        access_log=access_log, timeout_graceful_shutdown=3)
```

Default off rather than removing the capability, so an operator can re-enable per-deployment without
a code change.

### 2. `mcp_server_bug_423_hotfix.py` — demote the warning to debug

The condition being reported is one we have already decided to tolerate — the whole point of the file
is to swallow it and continue. Logging it at `WARNING` on every new session is noise about a known,
accepted state.

## Why not other options

**Strip ANSI at the shipper instead.** Would leave the volume unchanged and only shrink each document.
The access log itself has no diagnostic value here: HTTP status codes are already exposed by the
proxy's own metrics, and the source IP is always `127.0.0.1` because the proxy sits behind a local
listener.

**Set `log_level="warning"` on uvicorn.** Blunter — it would also suppress startup/shutdown lines that
are genuinely useful and low-volume. `access_log=False` targets exactly the high-volume stream.

**Silence source 2 (MCP SDK request tracing).** Not addressed here. It comes from vendored library
code, and suppressing it means configuring the `mcp.server.lowlevel.server` logger, which risks hiding
library errors. Left for a follow-up once the two larger sources are gone and the residual can be
re-measured.

## Open question, raised not answered

The bug-423 warning self-suppresses per session. Its volume therefore implies session churn — clients
reconnecting rather than holding a session. Demoting the log hides the symptom. **This should be
looked at independently**; it is a connection-lifecycle question, not a logging one, and it is out of
scope for this ticket.

## Testing

- `pytest tests/` — existing suite must pass unchanged. No test asserts on access-log behaviour.
- `SAFEBREACH_MCP_ACCESS_LOG=true` restores the previous behaviour; verified by inspection of the
  uvicorn config object rather than by starting a server.

## Verification after deploy

The container is `sbmcp-proxy`, which is the `mcp-proxy` repo vendoring this package into its venv.
This change lands here first; `mcp-proxy` must then bump the dependency for it to reach production.

Before-state and the exact verification query are recorded in the SAF-35054 Jira comment. Target:
`sb-server-logs` 6h total below 500k documents, no `\x1b[` sequences in sampled `message` fields.

## Rollback

Two lines, one file each. Revert the commit. `SAFEBREACH_MCP_ACCESS_LOG=true` restores access logging
without a deploy.
