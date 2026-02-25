"""
E2E test for SAF-28585: Concurrency rate limiter fix verification.

Starts a real MCP server with uvicorn, connects via SSE, and proves that
POST /messages/ requests ARE correctly rate-limited via query string
session_id parsing (fix for ContextVar bypass).

This test does NOT require a real SafeBreach environment — it tests the
local MCP server infrastructure only.
"""

import asyncio
import re
import socket
import pytest

import httpx
import uvicorn

from safebreach_mcp_core.safebreach_base import (
    SafeBreachMCPBase,
    _session_semaphores,
)


def _find_free_port() -> int:
    """Find an available TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def _wait_for_server(port: int, timeout: float = 5.0) -> None:
    """Wait until the server accepts connections."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        try:
            _, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.close()
            await writer.wait_closed()
            return
        except (ConnectionRefusedError, OSError):
            await asyncio.sleep(0.1)
    raise TimeoutError(f"Server on port {port} did not start within {timeout}s")


async def _connect_sse_raw(port: int) -> tuple[str, asyncio.StreamReader, asyncio.StreamWriter]:
    """Connect to SSE endpoint via raw TCP and extract the messages URL.

    httpx does not flush chunked SSE data reliably, so we use raw TCP
    to read the endpoint event and extract the session_id / messages URL.

    Returns (messages_url, reader, writer). Caller must close writer.
    """
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(
        b"GET /sse HTTP/1.1\r\n"
        b"Host: localhost\r\n"
        b"Accept: text/event-stream\r\n"
        b"\r\n"
    )
    await writer.drain()

    # Read in a loop — headers and SSE endpoint event may arrive in separate chunks
    accumulated = b""
    deadline = asyncio.get_event_loop().time() + 5.0
    while asyncio.get_event_loop().time() < deadline:
        chunk = await asyncio.wait_for(reader.read(4096), timeout=5.0)
        accumulated += chunk
        text = accumulated.decode("utf-8", errors="replace")
        match = re.search(r"data:\s*(/messages/?\?session_id=\S+)", text)
        if match:
            return match.group(1).strip(), reader, writer

    text = accumulated.decode("utf-8", errors="replace")
    raise AssertionError(f"Failed to parse messages URL from SSE within 5s: {text[:300]}")


@pytest.mark.e2e
class TestConcurrencyLimiterE2ESAF28585:
    """E2E tests verifying the concurrency limiter works (SAF-28585 fix).

    Starts a real MCP server with uvicorn and connects via HTTP, proving
    the limiter correctly throttles concurrent requests via query string
    session_id parsing.

    NOTE: All assertions are in a single test to avoid sse_starlette's
    AppStatus.should_exit_event event loop binding issue between
    separate asyncio.run() calls.
    """

    def test_concurrency_limiter_enforced(self):
        """Prove the concurrency limiter correctly throttles in real SSE flow.

        This test:
        1. Starts a real MCP server with uvicorn + concurrency limiter middleware
        2. Opens an SSE connection (raw TCP) to establish a session
        3. Initializes MCP and sends concurrent POST /messages/ tool calls
        4. Asserts: some 429 responses appear (limiter is enforced)
        5. Asserts: all responses are either 202 (accepted) or 429 (throttled)
        """
        async def run():
            port = _find_free_port()
            server = SafeBreachMCPBase("test-e2e", description="E2E concurrency test")

            @server.mcp.tool(name="echo_test")
            async def echo_test(message: str = "hello") -> str:  # noqa: ARG001
                return f"echo: {message}"

            mcp_app = server.mcp.sse_app()
            app = server._create_concurrency_limited_app(mcp_app)

            config = uvicorn.Config(
                app=app, host="127.0.0.1", port=port, log_level="warning"
            )
            uvi_server = uvicorn.Server(config)
            server_task = asyncio.create_task(uvi_server.serve())

            sse_writer = None
            try:
                await _wait_for_server(port)
                _session_semaphores.clear()

                # --- Phase 1: Connect SSE, extract session ---
                messages_url, _, sse_writer = await _connect_sse_raw(port)
                full_url = f"http://127.0.0.1:{port}{messages_url}"

                async with httpx.AsyncClient(timeout=10.0) as client:
                    # --- Phase 2: Initialize MCP session ---
                    init_resp = await client.post(full_url, json={
                        "jsonrpc": "2.0",
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {},
                            "clientInfo": {"name": "e2e-test", "version": "1.0"},
                        },
                        "id": 1,
                    })
                    assert init_resp.status_code in (200, 202), (
                        f"Initialize failed: {init_resp.status_code}"
                    )

                    await client.post(full_url, json={
                        "jsonrpc": "2.0",
                        "method": "notifications/initialized",
                        "params": {},
                    })

                    # --- Phase 3: Fire concurrent tool calls ---
                    async def send_tool_call(call_id: int) -> int:
                        resp = await client.post(full_url, json={
                            "jsonrpc": "2.0",
                            "method": "tools/call",
                            "params": {
                                "name": "echo_test",
                                "arguments": {"message": f"concurrent-{call_id}"},
                            },
                            "id": call_id + 100,
                        })
                        return resp.status_code

                    statuses = await asyncio.gather(
                        *[send_tool_call(i) for i in range(10)]
                    )

                    # --- Assertion 1: Some 429s — limiter is enforced ---
                    num_429 = sum(1 for s in statuses if s == 429)
                    assert num_429 > 0, (
                        f"Expected some HTTP 429 (proving limiter works), "
                        f"got 0. Statuses: {statuses}"
                    )

                    # --- Assertion 2: All responses are valid ---
                    for status in statuses:
                        assert status in (200, 202, 429), (
                            f"Unexpected status {status}"
                        )

            finally:
                if sse_writer:
                    sse_writer.close()
                uvi_server.should_exit = True
                await asyncio.sleep(0.3)
                server_task.cancel()
                try:
                    await server_task
                except (asyncio.CancelledError, SystemExit):
                    pass

        asyncio.run(run())
