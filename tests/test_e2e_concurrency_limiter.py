"""
E2E test for the concurrency limiter over the streamable-http transport.

Starts a real MCP server with uvicorn (streamable-http app + limiter middleware),
initializes a session on POST /mcp, then fires concurrent tools/call POSTs carrying
the Mcp-Session-Id header and proves the limiter throttles them with HTTP 429.

Originally written for SAF-28585 against the SSE transport; rewritten for
streamable-http in SAF-32387 when SSE was removed.

This test does NOT require a real SafeBreach environment — it tests the
local MCP server infrastructure only.
"""

import asyncio
import socket
import pytest

import httpx
import uvicorn

from safebreach_mcp_core.safebreach_base import (
    SafeBreachMCPBase,
    _session_semaphores,
)

_MCP_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}


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


@pytest.mark.e2e
class TestConcurrencyLimiterE2E:
    """Concurrency limiter enforced end-to-end over streamable-http."""

    def test_concurrency_limiter_enforced(self):
        """
        1. Starts a real MCP server (streamable-http) with the limiter middleware
        2. POSTs initialize to /mcp and captures the Mcp-Session-Id response header
        3. Fires concurrent tools/call POSTs with that session header
        4. Asserts: some 429 responses appear (limiter is enforced)
        5. Asserts: all responses are either 200/202 (accepted) or 429 (throttled)
        """
        async def run():
            port = _find_free_port()
            server = SafeBreachMCPBase("test-e2e", description="E2E concurrency test")

            @server.mcp.tool(name="echo_test")
            async def echo_test(message: str = "hello") -> str:  # noqa: ARG001
                await asyncio.sleep(0.2)  # hold the slot long enough for overlap
                return f"echo: {message}"

            server.mcp.settings.streamable_http_path = server.endpoint_path
            app = server._create_concurrency_limited_app(server.mcp.streamable_http_app())

            config = uvicorn.Config(app=app, host="127.0.0.1", port=port, log_level="warning")
            uvi_server = uvicorn.Server(config)
            server_task = asyncio.create_task(uvi_server.serve())

            try:
                await _wait_for_server(port)
                _session_semaphores.clear()
                url = f"http://127.0.0.1:{port}{server.endpoint_path}"

                async with httpx.AsyncClient(timeout=10.0, headers=_MCP_HEADERS) as client:
                    init_resp = await client.post(url, json={
                        "jsonrpc": "2.0",
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2025-03-26",
                            "capabilities": {},
                            "clientInfo": {"name": "e2e-test", "version": "1.0"},
                        },
                        "id": 1,
                    })
                    assert init_resp.status_code == 200, f"Initialize failed: {init_resp.status_code}"
                    session_id = init_resp.headers.get("mcp-session-id")
                    assert session_id, "Server did not return an Mcp-Session-Id header"
                    session_headers = {"Mcp-Session-Id": session_id}

                    await client.post(url, headers=session_headers, json={
                        "jsonrpc": "2.0",
                        "method": "notifications/initialized",
                        "params": {},
                    })

                    async def send_tool_call(call_id: int) -> int:
                        resp = await client.post(url, headers=session_headers, json={
                            "jsonrpc": "2.0",
                            "method": "tools/call",
                            "params": {
                                "name": "echo_test",
                                "arguments": {"message": f"concurrent-{call_id}"},
                            },
                            "id": call_id + 100,
                        })
                        return resp.status_code

                    statuses = await asyncio.gather(*[send_tool_call(i) for i in range(10)])

                    num_429 = sum(1 for s in statuses if s == 429)
                    assert num_429 > 0, (
                        f"Expected some HTTP 429 (proving limiter works), got 0. Statuses: {statuses}"
                    )
                    for status in statuses:
                        assert status in (200, 202, 429), f"Unexpected status {status}"

            finally:
                uvi_server.should_exit = True
                await asyncio.sleep(0.3)
                server_task.cancel()
                try:
                    await server_task
                except (asyncio.CancelledError, SystemExit):
                    pass

        asyncio.run(run())
