import pytest
from textual.app import App, ComposeResult

from nxs.infrastructure.mcp.client import ConnectionStatus
from nxs.presentation.widgets.mcp_panel import MCPPanel


class _MCPPanelApp(App):
    def __init__(self, panel: MCPPanel) -> None:
        super().__init__()
        self._panel = panel

    def compose(self) -> ComposeResult:
        yield self._panel


@pytest.mark.asyncio
async def test_panel_renders_multiple_servers_with_special_names():
    panel = MCPPanel()
    app = _MCPPanelApp(panel)

    servers = {
        "filesystem://local": {"tools": [], "prompts": [], "resources": []},
        "remote-api": {"tools": [], "prompts": [], "resources": []},
    }
    statuses = {
        "filesystem://local": ConnectionStatus.CONNECTED,
        "remote-api": ConnectionStatus.CONNECTED,
    }

    async with app.run_test() as pilot:
        panel.update_all_servers(servers, statuses, {})
        await pilot.pause()
        assert set(panel._server_widgets.keys()) == set(servers.keys())
        empty_message = getattr(panel, "_empty_message")
        assert empty_message is None or empty_message.display is False

