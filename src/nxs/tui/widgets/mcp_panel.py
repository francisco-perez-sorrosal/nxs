"""
MCPPanel - A scrollable panel displaying MCP servers and their artifacts.
"""

from textual.widgets import RichLog
from nxs.mcp_client.client import ConnectionStatus


def get_status_icon(status: ConnectionStatus) -> str:
    """Get status icon for connection status."""
    status_icons = {
        ConnectionStatus.CONNECTED: "🟢",
        ConnectionStatus.DISCONNECTED: "🔴",
        ConnectionStatus.CONNECTING: "🟡",
        ConnectionStatus.RECONNECTING: "🟡",
        ConnectionStatus.ERROR: "🔴",
    }
    return status_icons.get(status, "⚪")


def get_status_text(status: ConnectionStatus) -> str:
    """Get status text for connection status."""
    status_texts = {
        ConnectionStatus.CONNECTED: "[green]Connected[/]",
        ConnectionStatus.DISCONNECTED: "[red]Disconnected[/]",
        ConnectionStatus.CONNECTING: "[yellow]Connecting...[/]",
        ConnectionStatus.RECONNECTING: "[yellow]Reconnecting...[/]",
        ConnectionStatus.ERROR: "[red]Error[/]",
    }
    return status_texts.get(status, "[dim]Unknown[/]")


class MCPPanel(RichLog):
    """
    A panel that displays MCP servers and their artifacts.

    Features:
    - Displays each connected MCP server
    - Shows tools (T), prompts (P), and resources (R) for each server
    - Auto-scrolling
    - Compact, efficient display
    """

    BORDER_TITLE = "MCP Servers"

    def __init__(self, **kwargs):
        """Initialize the MCP panel with Rich markup enabled."""
        super().__init__(
            markup=True,
            highlight=False,
            auto_scroll=True,
            wrap=True,
            **kwargs
        )
        self.write("[bold cyan]MCP Servers & Artifacts[/]\n")
        self.add_divider()
        # Track connection status for each server
        self._server_statuses: dict[str, ConnectionStatus] = {}

    def update_server_status(self, server_name: str, status: ConnectionStatus):
        """
        Update the connection status for a specific server.

        Args:
            server_name: Name of the server
            status: Connection status
        """
        self._server_statuses[server_name] = status
        # Refresh the display to show updated status
        # Note: This requires the full servers_data to be passed again
        # For now, we'll just store it and show it in the next update

    def update_servers(
        self,
        servers_data: dict[str, dict[str, list[str]]],
        server_statuses: dict[str, ConnectionStatus] | None = None,
    ):
        """
        Update the panel with server data and connection status.

        Args:
            servers_data: Dictionary mapping server names to their artifacts.
                         Format: {
                             "server_name": {
                                 "tools": ["tool1", "tool2"],
                                 "prompts": ["prompt1", "prompt2"],
                                 "resources": ["resource1", "resource2"]
                             }
                         }
            server_statuses: Dictionary mapping server names to their connection status.
                             If None, uses cached statuses.
        """
        # Update cached statuses if provided
        if server_statuses:
            self._server_statuses.update(server_statuses)

        # Clear existing content
        self.clear()
        self.write("[bold cyan]MCP Servers & Artifacts[/]\n")
        self.add_divider()

        if not servers_data:
            self.write("[dim]No MCP servers connected[/]\n")
            return

        for server_name, artifacts in servers_data.items():
            # Get connection status for this server
            status = self._server_statuses.get(server_name, ConnectionStatus.DISCONNECTED)
            status_icon = get_status_icon(status)
            status_text = get_status_text(status)
            
            # Server header with connection status
            self.write(f"\n[bold yellow]📡 {server_name}[/] {status_icon} {status_text}\n")
            
            # Tools
            tools = artifacts.get("tools", [])
            if tools:
                for tool in tools:
                    self.write(f"  [cyan](T)[/] {tool}\n")
            
            # Prompts
            prompts = artifacts.get("prompts", [])
            if prompts:
                for prompt in prompts:
                    self.write(f"  [green](P)[/] {prompt}\n")
            
            # Resources
            resources = artifacts.get("resources", [])
            if resources:
                for resource in resources:
                    # Extract resource name from URI if it's a full URI
                    resource_display = resource
                    if "://" in resource:
                        parts = resource.split("/")
                        resource_display = parts[-1] if parts else resource
                    self.write(f"  [magenta](R)[/] {resource_display}\n")
            
            # Show counts if any artifacts exist
            total = len(tools) + len(prompts) + len(resources)
            if total == 0:
                self.write("  [dim]No artifacts[/]\n")
            else:
                self.write(f"  [dim]({len(tools)} tools, {len(prompts)} prompts, {len(resources)} resources)[/]\n")
            
            self.add_divider()

    def add_divider(self):
        """Add a visual divider between sections."""
        self.write("[dim]" + "─" * 30 + "[/]\n")
