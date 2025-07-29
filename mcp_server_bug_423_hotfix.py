"""
This file is used to fix the notorious 'Received request before initialization was complete' error.
This issue is difficult to resolve due to its origin within the MCP library itself.
This patch simply overrides the function that throws the exception, allowing the service to run,
although it may come with unforeseen consequences.

Keep this patch in place until MCP addresses the issue.
For more information, please see https://github.com/modelcontextprotocol/python-sdk/issues/423
"""
import logging
from enum import Enum
import mcp.types as types
from mcp.shared.session import (
    RequestResponder,
)

from mcp.shared.version import SUPPORTED_PROTOCOL_VERSIONS
import mcp.server.session


class InitializationState(Enum):
    NotInitialized = 1
    Initializing = 2
    Initialized = 3


async def _received_request(
    self, responder: RequestResponder[types.ClientRequest, types.ServerResult]
):
    match responder.request.root:
        case types.InitializeRequest(params=params):
            requested_version = params.protocolVersion
            self._initialization_state = InitializationState.Initializing
            self._client_params = params
            with responder:
                await responder.respond(
                    types.ServerResult(
                        types.InitializeResult(
                            protocolVersion=(
                                requested_version
                                if requested_version in SUPPORTED_PROTOCOL_VERSIONS
                                else types.LATEST_PROTOCOL_VERSION
                            ),
                            capabilities=self._init_options.capabilities,
                            serverInfo=types.Implementation(
                                name=self._init_options.server_name,
                                version=self._init_options.server_version,
                            ),
                            instructions=self._init_options.instructions,
                        )
                    )
                )
            # Mark initialization as complete after responding
            self._initialization_state = InitializationState.Initialized
            
        case types.InitializedNotification():
            # Handle initialized notification
            self._initialization_state = InitializationState.Initialized
            
        case _:
            if self._initialization_state != InitializationState.Initialized:
                # Log the issue but allow the request to proceed
                logging.warning(f"Received request before initialization was complete: {type(responder.request.root).__name__}")
                # Set to initialized state to prevent further warnings
                self._initialization_state = InitializationState.Initialized
            
            # The original method doesn't handle non-initialization requests at all
            # Just let it pass through - the framework will handle request routing
            pass


def apply_patch() -> None:
    """
    Apply the patch to the MCP library.
    """
    logging.info("Applying MCP initialization patch")
    mcp.server.session.ServerSession._received_request = _received_request