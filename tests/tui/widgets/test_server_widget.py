import pytest
from textual.app import App, ComposeResult

from nxs.infrastructure.mcp.client import ConnectionStatus
from nxs.presentation.widgets.server_widget import ServerWidget


class _ServerWidgetApp(App):
    def __init__(self, widget: ServerWidget) -> None:
        super().__init__()
        self._widget = widget

    def compose(self) -> ComposeResult:
        yield self._widget


@pytest.mark.asyncio
async def test_server_widget_updates_status():
    widget = ServerWidget("test-server")
    app = _ServerWidgetApp(widget)

    async with app.run_test() as pilot:
        widget.update_data(connection_status=ConnectionStatus.CONNECTED, last_check_time=0.0)
        await pilot.pause()
        assert "Connected" in widget.header_text.plain


@pytest.mark.asyncio
async def test_server_widget_renders_artifacts():
    widget = ServerWidget("test-server")
    app = _ServerWidgetApp(widget)

    artifacts = {
        "tools": [{"name": "tool-a", "description": "Tool A"}],
        "prompts": [{"name": "prompt-a", "description": "Prompt A"}],
        "resources": [{"name": "file:///tmp/resource.txt", "description": "Resource"}],
    }

    async with app.run_test() as pilot:
        widget.update_data(artifacts=artifacts)
        await pilot.pause()
        container = getattr(widget, "_artifacts_container")
        assert len(container.children) == 3
