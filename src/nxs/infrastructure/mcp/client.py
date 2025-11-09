"""MCP client with OAuth support and connection management."""

from __future__ import annotations

import asyncio
import json
from datetime import timedelta
from typing import Any, Callable, Optional, cast

from mcp import types
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import CallToolResult
from pydantic import AnyUrl

from nxs.logger import get_logger
from nxs.infrastructure.mcp.auth import oauth_context
from nxs.infrastructure.mcp.connection import SingleConnectionManager
from nxs.domain.types import ConnectionStatus

logger = get_logger("mcp_client")


class MCPAuthClient:
    """MCP protocol client with connection management and session operations.
    
    This client handles:
    - Connection lifecycle (connect, disconnect, reconnect)
    - Session management with health monitoring
    - Direct MCP operations (tools, prompts, resources)
    """

    def __init__(
        self,
        server_url: str,
        transport_type: str = "streamable_http",
        *,
        connection_manager: Optional[SingleConnectionManager] = None,
        on_status_change: Optional[Callable[[ConnectionStatus], None]] = None,
        on_reconnect_progress: Optional[Callable[[int, int, float], None]] = None,
    ):
        self.server_url = server_url
        self.transport_type = transport_type
        self._use_auth = False

        if connection_manager is not None and (on_status_change or on_reconnect_progress):
            logger.debug(
                "MCPAuthClient received both connection_manager and callbacks; "
                "callbacks will be ignored because the manager should already be configured.",
            )

        self._connection_manager = connection_manager or SingleConnectionManager(
            on_status_change=on_status_change,
            on_reconnect_progress=on_reconnect_progress,
        )

    # --------------------------------------------------------------------- #
    # Properties
    # --------------------------------------------------------------------- #

    @property
    def connection_status(self) -> ConnectionStatus:
        """Current connection status reported by the lifecycle manager."""
        return self._connection_manager.status

    @property
    def is_connected(self) -> bool:
        """Whether the client currently has an active session."""
        return self._connection_manager.is_connected

    @property
    def session(self) -> Optional[ClientSession]:
        """Expose the underlying MCP session."""
        return cast(Optional[ClientSession], self._connection_manager.session)

    def _get_session(self) -> Optional[ClientSession]:
        """Session getter passed to operations modules."""
        return cast(Optional[ClientSession], self._connection_manager.session)

    @property
    def reconnect_info(self) -> dict[str, Any]:
        """Reconnection metadata from the connection manager."""
        return self._connection_manager.reconnect_info

    @property
    def connection_manager(self) -> SingleConnectionManager:
        """Expose the underlying connection manager."""
        return self._connection_manager

    # --------------------------------------------------------------------- #
    # Connection lifecycle
    # --------------------------------------------------------------------- #

    async def connect(self, use_auth: bool = False) -> None:
        """
        Establish a connection to the MCP server and wait until ready.

        Args:
            use_auth: Whether OAuth authentication should be used.
        """
        self._use_auth = use_auth
        logger.info("Starting connection to %s (transport=%s)", self.server_url, self.transport_type)

        if self.transport_type == "sse":
            raise ValueError("SSE transport is not supported")

        await self._connection_manager.connect(self._connection_function)
        logger.info("Connection established to %s", self.server_url)

    async def retry_connection(self, use_auth: bool = False) -> None:
        """Retry connection after an error status."""
        self._use_auth = use_auth
        await self._connection_manager.retry_connection(self._connection_function)

    async def disconnect(self) -> None:
        """Terminate the connection and clean up resources."""
        logger.info("Disconnect requested for %s", self.server_url)
        await self._connection_manager.disconnect()
        logger.info("Disconnected from %s", self.server_url)

    # --------------------------------------------------------------------- #
    # MCP Operations - Tools
    # --------------------------------------------------------------------- #

    async def list_tools(self) -> list[types.Tool]:
        """List tools exposed by the connected server."""
        session = self._get_session()
        if session is None:
            logger.warning("Cannot list tools: no active MCP session")
            return []

        try:
            result = await session.list_tools()
            tools = getattr(result, "tools", None)
            return list(tools or [])
        except Exception as exc:
            logger.error("Failed to list tools: %s", exc)
            return []

    async def call_tool(
        self,
        tool_name: str,
        arguments: Optional[dict[str, Any]] = None,
    ) -> Optional[CallToolResult]:
        """Invoke a tool on the connected server."""
        session = self._get_session()
        if session is None:
            logger.warning("Cannot call tool '%s': no active MCP session", tool_name)
            return None

        try:
            return await session.call_tool(tool_name, arguments or {})
        except Exception as exc:
            logger.error("Failed to call tool '%s': %s", tool_name, exc)
            return None

    # --------------------------------------------------------------------- #
    # MCP Operations - Prompts
    # --------------------------------------------------------------------- #

    async def list_prompts(self) -> list[types.Prompt]:
        """List prompts exposed by the connected server."""
        session = self._get_session()
        if session is None:
            logger.warning("Cannot list prompts: no active MCP session")
            return []

        try:
            result = await session.list_prompts()
            prompts = getattr(result, "prompts", None)
            return list(prompts or [])
        except Exception as exc:
            logger.error("Failed to list prompts: %s", exc)
            return []

    async def get_prompt(
        self,
        prompt_name: str,
        args: dict[str, Any],
    ) -> list[types.PromptMessage]:
        """Retrieve a prompt with the provided arguments."""
        session = self._get_session()
        if session is None:
            logger.warning("Cannot get prompt '%s': no active MCP session", prompt_name)
            return []

        try:
            result = await session.get_prompt(prompt_name, args)
            messages = getattr(result, "messages", None)
            return list(messages or [])
        except Exception as exc:
            logger.error("Failed to get prompt '%s': %s", prompt_name, exc)
            return []

    # --------------------------------------------------------------------- #
    # MCP Operations - Resources
    # --------------------------------------------------------------------- #

    async def list_resources(self) -> list[types.Resource]:
        """List resources exposed by the connected server."""
        session = self._get_session()
        if session is None:
            logger.warning("Cannot list resources: no active MCP session")
            return []

        try:
            result = await session.list_resources()
            resources = getattr(result, "resources", None)
            return list(resources or [])
        except Exception as exc:
            logger.error("Failed to list resources: %s", exc)
            return []

    async def read_resource(self, uri: str) -> Optional[Any]:
        """Read and return the contents of a resource."""
        session = self._get_session()
        if session is None:
            logger.warning("Cannot read resource '%s': no active MCP session", uri)
            return None

        try:
            result = await session.read_resource(AnyUrl(uri))
            contents = getattr(result, "contents", None)
            if not contents:
                return None

            resource = contents[0]
            if isinstance(resource, types.TextResourceContents):
                if resource.mimeType == "application/json":
                    try:
                        return json.loads(resource.text)
                    except json.JSONDecodeError as exc:
                        logger.error("Invalid JSON in resource '%s': %s", uri, exc)
                        return None
                return resource.text

            return None
        except Exception as exc:
            logger.error("Failed to read resource '%s': %s", uri, exc)
            return None

    # --------------------------------------------------------------------- #
    # Internal connection helpers
    # --------------------------------------------------------------------- #

    async def _connection_function(self, stop_event: asyncio.Event) -> None:
        """
        Establish and maintain the MCP connection until the stop event is set.

        Args:
            stop_event: Event signaling that the connection should be terminated.
        """
        logger.debug("Connection function started (use_auth=%s)", self._use_auth)

        if self._use_auth:
            async with oauth_context(self.server_url) as oauth_provider:
                async with streamablehttp_client(
                    url=self.server_url,
                    auth=oauth_provider,
                    timeout=timedelta(seconds=60),
                ) as (read_stream, write_stream, get_session_id):
                    await self._setup_session(read_stream, write_stream, get_session_id, stop_event)
        else:
            async with streamablehttp_client(
                url=self.server_url,
                auth=None,
                timeout=timedelta(seconds=60),
            ) as (read_stream, write_stream, get_session_id):
                await self._setup_session(read_stream, write_stream, get_session_id, stop_event)

        logger.debug("Connection function exiting (connection lost or stopped)")

    async def _setup_session(
        self,
        read_stream,
        write_stream,
        get_session_id,
        stop_event: asyncio.Event,
    ) -> None:
        """Initialize the MCP session and keep it alive until instructed to stop."""
        async with ClientSession(read_stream, write_stream) as session:
            logger.debug("Initializing MCP session")

            await session.initialize()
            logger.info("Session initialization completed for %s", self.server_url)

            self._connection_manager.set_session(session)

            if get_session_id:
                session_id = get_session_id()
                if session_id:
                    logger.info("Connected with session id %s", session_id)

            await stop_event.wait()
            logger.debug("Stop signal received; session cleanup will follow")
