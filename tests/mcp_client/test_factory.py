import pytest
from unittest.mock import AsyncMock, MagicMock

from nxs.application.artifact_manager import ArtifactManager
from nxs.domain.events import EventBus
from nxs.application.mcp_config import MCPServerConfig, MCPServersConfig
from nxs.domain.types import ConnectionStatus
from nxs.infrastructure.mcp.client import MCPAuthClient
from nxs.infrastructure.mcp.factory import ClientFactory


def _remote_config(url: str) -> MCPServerConfig:
    return MCPServerConfig(
        command="npx",
        args=["mcp-remote", url],
    )


def test_client_factory_creates_client() -> None:
    factory = ClientFactory()
    status_events: list[tuple[str, ConnectionStatus]] = []

    client = factory.create_client(
        "demo",
        _remote_config("https://example.com/mcp"),
        status_callback=lambda name, status: status_events.append((name, status)),
    )

    assert isinstance(client, MCPAuthClient)
    assert client.server_url == "https://example.com/mcp"
    assert client.connection_manager.status == ConnectionStatus.DISCONNECTED

    # Simulate status change to ensure callback wiring works
    client.connection_manager._lifecycle.set_status(ConnectionStatus.CONNECTED)  # type: ignore[attr-defined]
    assert status_events == [("demo", ConnectionStatus.CONNECTED)]


def test_client_factory_creates_multiple_clients() -> None:
    factory = ClientFactory()
    configs = {
        "alpha": _remote_config("https://alpha.example.com"),
        "beta": _remote_config("https://beta.example.com"),
    }

    clients = factory.create_clients(configs)

    assert set(clients.keys()) == {"alpha", "beta"}
    assert all(isinstance(client, MCPAuthClient) for client in clients.values())


@pytest.mark.asyncio
async def test_artifact_manager_uses_client_factory() -> None:
    mock_client = MagicMock(spec=MCPAuthClient)
    mock_client.connect = AsyncMock()
    mock_client.disconnect = AsyncMock()

    mock_factory = MagicMock(spec=ClientFactory)
    mock_factory.create_clients.return_value = {"alpha": mock_client}

    config = MCPServersConfig(
        mcpServers={
            "alpha": _remote_config("https://alpha.example.com"),
        }
    )

    manager = ArtifactManager(
        config=config,
        client_provider=mock_factory,
        event_bus=EventBus(),
    )

    await manager.initialize()
    mock_factory.create_clients.assert_called_once()
    mock_client.connect.assert_awaited_once()

    await manager.cleanup()
    mock_client.disconnect.assert_awaited()
