"""
MCPPanel - A scrollable panel displaying MCP servers and their artifacts.
"""

from typing import Any
from textual.widgets import Static
from textual.containers import Vertical, ScrollableContainer
from textual.app import ComposeResult
from rich.text import Text
from rich.console import Group
from nxs.mcp_client.client import ConnectionStatus
from nxs.utils import format_time_hhmmss
from nxs.logger import get_logger

logger = get_logger("mcp_panel")


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


def _format_server_display(
    server_name: str,
    status: ConnectionStatus,
    artifacts: dict[str, list[str]],
    last_check_timestamp: float,
    operational_status: str = "",
    reconnect_info: dict[str, Any] | None = None,
    error_message: str | None = None,
) -> Group:
    """
    Format server display as Rich Group.
    
    This is a reusable function extracted from the original rendering logic.
    
    Args:
        server_name: Name of the server
        status: Connection status
        artifacts: Dictionary with keys "tools", "prompts", "resources"
        last_check_timestamp: Unix timestamp of last check
        operational_status: Operational status message (e.g., "Fetching artifacts...")
        reconnect_info: Reconnection progress information
        error_message: Error message if status is ERROR
        
    Returns:
        Rich Group containing formatted server display
    """
    status_icon = get_status_icon(status)
    status_text = get_status_text(status)
    
    # Build status line with reconnection progress or error message
    status_details = []
    
    # Add reconnection progress if reconnecting
    if status == ConnectionStatus.RECONNECTING and reconnect_info:
        attempts = reconnect_info.get("attempts", 0)
        max_attempts = reconnect_info.get("max_attempts", 10)
        next_retry = reconnect_info.get("next_retry_delay")
        if next_retry is not None:
            status_details.append(f"[dim]attempt {attempts}/{max_attempts}, retry in {next_retry:.0f}s[/]")
        else:
            status_details.append(f"[dim]attempt {attempts}/{max_attempts}[/]")
    
    # Add error message if ERROR status
    if status == ConnectionStatus.ERROR and error_message:
        status_details.append(f"[red]{error_message}[/]")
    
    # Build status line
    status_line = status_text
    if status_details:
        status_line += f" [dim]| {' | '.join(status_details)}[/]"
    
    # Build lines for server display as Text objects
    lines = []
    
    # Server header - use Text.from_markup to parse Rich markup
    header_text = f"\n[bold yellow]📡 {server_name}[/] {status_icon} {status_line}"
    lines.append(Text.from_markup(header_text))
    
    # Operational status line (if present) - parse markup
    if operational_status:
        op_status_line = f"  Status: {operational_status}"
        lines.append(Text.from_markup(op_status_line))
    
    # Last check time
    last_check_str = format_time_hhmmss(last_check_timestamp)
    lines.append(Text.from_markup(f"  [dim]Checked: {last_check_str}[/]"))
    
    # Tools
    tools = artifacts.get("tools", [])
    if tools:
        for tool in tools:
            lines.append(Text.from_markup(f"  [cyan](T)[/] {tool}"))
    
    # Prompts
    prompts = artifacts.get("prompts", [])
    if prompts:
        for prompt in prompts:
            lines.append(Text.from_markup(f"  [green](P)[/] {prompt}"))
    
    # Resources
    resources = artifacts.get("resources", [])
    if resources:
        for resource in resources:
            # Extract resource name from URI if it's a full URI
            resource_display = resource
            if "://" in resource:
                parts = resource.split("/")
                resource_display = parts[-1] if parts else resource
            lines.append(Text.from_markup(f"  [magenta](R)[/] {resource_display}"))
    
    # Show counts if any artifacts exist
    total = len(tools) + len(prompts) + len(resources)
    if total == 0:
        lines.append(Text.from_markup("  [dim]No artifacts[/]"))
    else:
        lines.append(Text.from_markup(f"  [dim]({len(tools)} tools, {len(prompts)} prompts, {len(resources)} resources)[/]"))
    
    # Divider
    lines.append(Text.from_markup("[dim]" + "─" * 30 + "[/]"))
    
    return Group(*lines)


class ServerWidget(Static):
    """Individual server display widget that can be updated independently."""
    
    def __init__(self, server_name: str, **kwargs):
        """Initialize the server widget."""
        super().__init__(**kwargs)
        self.server_name = server_name
        self._connection_status = ConnectionStatus.DISCONNECTED
        self._operational_status = ""
        self._reconnect_info: dict[str, Any] = {}
        self._error_message: str | None = None
        self._artifacts: dict[str, list[str]] = {"tools": [], "prompts": [], "resources": []}
        self._last_check_time = 0.0
        # Initialize with placeholder content so widget is visible
        self.update(Text.from_markup(f"[dim]Loading {server_name}...[/]"))
    
    def update_data(
        self,
        connection_status: ConnectionStatus | None = None,
        operational_status: str | None = None,
        artifacts: dict[str, list[str]] | None = None,
        last_check_time: float | None = None,
        reconnect_info: dict[str, Any] | None = None,
        error_message: str | None = None,
    ):
        """
        Update the server widget display data and re-render.
        
        Args:
            connection_status: Connection status (if None, keeps current)
            operational_status: Operational status message (if None, keeps current; empty string clears)
            artifacts: Artifacts dict (if None, keeps current)
            last_check_time: Last check timestamp (if None, keeps current)
            reconnect_info: Reconnection info (if None, keeps current)
            error_message: Error message (if None, keeps current; empty string clears)
        """
        # Update internal state
        if connection_status is not None:
            self._connection_status = connection_status
            if connection_status != ConnectionStatus.ERROR:
                self._error_message = None
        
        if operational_status is not None:
            self._operational_status = operational_status
        
        if artifacts is not None:
            self._artifacts = artifacts
        
        if last_check_time is not None:
            self._last_check_time = last_check_time
        
        if reconnect_info is not None:
            self._reconnect_info = reconnect_info
        
        if error_message is not None:
            self._error_message = error_message
        
        # Re-render using shared formatting function
        display = _format_server_display(
            server_name=self.server_name,
            status=self._connection_status,
            artifacts=self._artifacts,
            last_check_timestamp=self._last_check_time,
            operational_status=self._operational_status,
            reconnect_info=self._reconnect_info if self._reconnect_info else None,
            error_message=self._error_message,
        )
        
        # Update widget content (call parent Static.update method)
        super().update(display)


class MCPPanel(Vertical):
    """
    A panel that displays MCP servers and their artifacts.
    
    Uses per-server Static widgets that can be updated independently.
    
    Features:
    - Displays each connected MCP server in its own widget
    - Shows tools (T), prompts (P), and resources (R) for each server
    - Independent updates per server (no full panel refresh)
    - Scrollable container for many servers
    """

    BORDER_TITLE = "MCP Servers"

    def __init__(self, **kwargs):
        """Initialize the MCP panel."""
        super().__init__(**kwargs)
        # Track widgets
        self._server_widgets: dict[str, ServerWidget] = {}
        self._header_widget: Static | None = None
        self._empty_message_widget: Static | None = None
        self._scroll_container: ScrollableContainer | None = None

    def compose(self) -> ComposeResult:
        """Compose the panel with header and scrollable content."""
        # Header
        header = Static("[bold cyan]MCP Servers & Artifacts[/]", id="mcp-header")
        self._header_widget = header
        yield header
        
        # Divider
        yield Static("[dim]" + "─" * 30 + "[/]", id="mcp-divider-top")
        
        # Scrollable container for servers - use context manager to properly yield container
        with ScrollableContainer(id="mcp-servers-container") as servers_container:
            # Store reference for later use
            self._scroll_container = servers_container
            # Empty message (hidden by default)
            empty_msg = Static("[dim]No MCP servers connected[/]", id="mcp-empty-message")
            self._empty_message_widget = empty_msg
            yield empty_msg
    
    def on_mount(self) -> None:
        """Called when the panel is mounted - ensure scroll container is accessible."""
        # Ensure scroll container reference is set after mount
        if self._scroll_container is None:
            try:
                self._scroll_container = self.query_one("#mcp-servers-container", ScrollableContainer)
            except Exception:
                pass

    def update_server(
        self,
        server_name: str,
        connection_status: ConnectionStatus | None = None,
        operational_status: str | None = None,
        artifacts: dict[str, list[str]] | None = None,
        last_check_time: float | None = None,
        reconnect_info: dict[str, Any] | None = None,
        error_message: str | None = None,
    ):
        """
        Update a specific server widget.
        
        Args:
            server_name: Name of the server
            connection_status: Connection status
            operational_status: Operational status message
            artifacts: Artifacts dict
            last_check_time: Last check timestamp
            reconnect_info: Reconnection info
            error_message: Error message
        """
        # Create widget if it doesn't exist
        if server_name not in self._server_widgets:
            self._add_server_widget(server_name)
        
        # Update the widget
        widget = self._server_widgets[server_name]
        widget.update_data(
            connection_status=connection_status,
            operational_status=operational_status,
            artifacts=artifacts,
            last_check_time=last_check_time,
            reconnect_info=reconnect_info,
            error_message=error_message,
        )
        
        # Show/hide empty message
        self._update_empty_message()

    def _add_server_widget(self, server_name: str):
        """Add a new server widget to the panel."""
        logger.debug(f"Adding server widget for {server_name}")
        
        # Get or set container reference
        if self._scroll_container is None:
            try:
                container = self.query_one("#mcp-servers-container", ScrollableContainer)
                self._scroll_container = container
                logger.debug(f"Retrieved scroll container: {container}")
            except Exception as e:
                # Container not ready yet
                logger.error(f"Failed to get scroll container: {e}")
                return
        else:
            container = self._scroll_container
        
        # Add divider before server (except first)
        if self._server_widgets:
            divider = Static("[dim]" + "─" * 30 + "[/]", id=f"mcp-divider-{server_name}")
            container.mount(divider)
            logger.debug(f"Mounted divider for {server_name}")
        
        # Create server widget
        widget = ServerWidget(server_name, id=f"mcp-server-{server_name}")
        
        # Mount widget directly into the main scroll container
        # The main container handles scrolling for all servers
        container.mount(widget)
        
        self._server_widgets[server_name] = widget
        
        logger.debug(f"Mounted server widget for {server_name}, total widgets: {len(self._server_widgets)}")
        
        # Initialize widget display after mount - this will update with actual data
        # The widget already has placeholder content from __init__
        widget.update_data()

    def _update_empty_message(self):
        """Show/hide empty message based on whether there are any servers."""
        if self._empty_message_widget:
            has_servers = len(self._server_widgets) > 0
            self._empty_message_widget.display = not has_servers

    def update_all_servers(
        self,
        servers_data: dict[str, dict[str, list[str]]],
        server_statuses: dict[str, ConnectionStatus] | None = None,
        server_last_check: dict[str, float] | None = None,
    ):
        """
        Update all servers at once.
        
        This updates each server widget independently, so it's efficient.
        
        Args:
            servers_data: Dictionary mapping server names to their artifacts
            server_statuses: Dictionary mapping server names to connection status
            server_last_check: Dictionary mapping server names to last check timestamp
        """
        logger.debug(f"update_all_servers called with {len(servers_data)} server(s), statuses: {server_statuses}")
        
        # If we have server statuses but no servers_data, create entries for all connected servers
        if server_statuses and not servers_data:
            logger.debug(f"No servers_data but have {len(server_statuses)} server status(es), creating empty entries")
            for server_name in server_statuses.keys():
                servers_data[server_name] = {"tools": [], "prompts": [], "resources": []}
        
        # Update each server
        for server_name, artifacts in servers_data.items():
            status = server_statuses.get(server_name) if server_statuses else None
            last_check = server_last_check.get(server_name) if server_last_check else None
            
            logger.debug(f"Updating server {server_name}: status={status}, artifacts={len(artifacts.get('tools', []))} tools")
            
            # Check if we should clear the operational status
            # If artifacts are provided and current status is "Fetching artifacts...", clear it
            # This handles the case where artifacts were just fetched and we want to remove the "Fetching..." message
            operational_status_to_set = None
            if server_name in self._server_widgets:
                current_widget = self._server_widgets[server_name]
                current_op_status = current_widget._operational_status or ""
                # Clear "Fetching artifacts..." status when artifacts are successfully provided
                # Only clear if it's a plain "Fetching artifacts..." message (not success/error messages)
                if "Fetching artifacts" in current_op_status:
                    # Don't clear if it's already a success or error message
                    if "✓" not in current_op_status and "✗" not in current_op_status and "Error" not in current_op_status and "No artifacts" not in current_op_status:
                        operational_status_to_set = ""  # Clear the status
                        logger.debug(f"Clearing 'Fetching artifacts...' status for {server_name} after artifacts loaded")
            
            self.update_server(
                server_name=server_name,
                connection_status=status,
                operational_status=operational_status_to_set if operational_status_to_set is not None else None,
                artifacts=artifacts,
                last_check_time=last_check,
            )
        
        # Remove widgets for servers that are no longer in data
        existing_servers = set(servers_data.keys())
        for server_name in list(self._server_widgets.keys()):
            if server_name not in existing_servers:
                self._remove_server_widget(server_name)
        
        self._update_empty_message()

    def _remove_server_widget(self, server_name: str):
        """Remove a server widget from the panel."""
        if server_name in self._server_widgets:
            widget = self._server_widgets[server_name]
            try:
                widget.remove()
            except Exception:
                # Widget might not exist, just continue
                pass
            del self._server_widgets[server_name]

    # Compatibility methods for existing code
    def update_server_status(self, server_name: str, status: ConnectionStatus):
        """Update the connection status for a specific server."""
        self.update_server(server_name, connection_status=status)

    def update_reconnect_info(self, server_name: str, reconnect_info: dict[str, Any]):
        """Update reconnection progress information for a server."""
        self.update_server(server_name, reconnect_info=reconnect_info)
        # Store error message if present
        error_message = reconnect_info.get("error_message")
        if error_message:
            self.update_server(server_name, error_message=error_message)

    def set_fetch_status(self, server_name: str, status_message: str):
        """Set the operational status message for a server."""
        self.update_server(server_name, operational_status=status_message)

    def clear_fetch_status(self, server_name: str):
        """Clear the operational status for a server."""
        self.update_server(server_name, operational_status="")

    def update_servers(
        self,
        servers_data: dict[str, dict[str, list[str]]],
        server_statuses: dict[str, ConnectionStatus] | None = None,
        server_last_check: dict[str, float] | None = None,
    ):
        """
        Update the panel with server data and connection status.
        
        This is a compatibility method that calls update_all_servers.
        """
        self.update_all_servers(servers_data, server_statuses, server_last_check)
