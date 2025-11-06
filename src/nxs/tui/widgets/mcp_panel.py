"""
MCPPanel - A scrollable panel displaying MCP servers and their artifacts.
"""

from typing import Any, TYPE_CHECKING
from textual.widgets import Static, Label
from textual.containers import Vertical, ScrollableContainer
from textual.app import ComposeResult
from textual.message import Message
from rich.text import Text
from rich.console import Group
from nxs.mcp_client.client import ConnectionStatus
from nxs.utils import format_time_hhmmss
from nxs.logger import get_logger
from nxs.tui.widgets.artifact_overlay import ArtifactDescriptionOverlay

logger = get_logger("mcp_panel")


def sanitize_widget_id(name: str) -> str:
    """
    Sanitize a name to be used as a widget ID.
    
    Replaces special characters that are problematic in CSS selectors
    and widget IDs with safe alternatives.
    
    Args:
        name: The name to sanitize
        
    Returns:
        Sanitized name safe for use as widget ID
    """
    # Replace special characters with underscores
    # This ensures IDs are valid for CSS selectors
    sanitized = name.replace("://", "_").replace(":", "_").replace("/", "_").replace(" ", "_")
    sanitized = sanitized.replace(".", "_").replace("-", "_").replace("+", "_")
    # Remove any remaining problematic characters
    sanitized = "".join(c if c.isalnum() or c == "_" else "_" for c in sanitized)
    return sanitized


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
    artifacts: dict[str, list[dict[str, str | None]]],
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
            tool_name = tool.get("name", "") if isinstance(tool, dict) else tool
            lines.append(Text.from_markup(f"  [cyan](T)[/] {tool_name}"))
    
    # Prompts
    prompts = artifacts.get("prompts", [])
    if prompts:
        for prompt in prompts:
            prompt_name = prompt.get("name", "") if isinstance(prompt, dict) else prompt
            lines.append(Text.from_markup(f"  [green](P)[/] {prompt_name}"))
    
    # Resources
    resources = artifacts.get("resources", [])
    if resources:
        for resource in resources:
            # Extract resource name from URI if it's a full URI
            resource_name = resource.get("name", "") if isinstance(resource, dict) else resource
            if resource_name:
                resource_display = resource_name
                if "://" in resource_name:
                    parts = resource_name.split("/")
                    resource_display = parts[-1] if parts else resource_name
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


class ArtifactItem(Static):
    """Clickable artifact item widget."""
    
    class Clicked(Message):
        """Message sent when artifact is clicked."""
        def __init__(self, artifact_name: str, artifact_type: str, description: str | None):
            super().__init__()
            self.artifact_name = artifact_name
            self.artifact_type = artifact_type
            self.description = description
    
    def __init__(self, artifact_name: str, artifact_type: str, description: str | None, **kwargs):
        """Initialize the artifact item."""
        super().__init__(**kwargs)
        self.artifact_name = artifact_name
        self.artifact_type = artifact_type
        self.description = description
        
        # Format display text
        type_colors = {
            "T": "cyan",
            "P": "green",
            "R": "magenta"
        }
        color = type_colors.get(artifact_type, "white")
        display_text = f"  [{color}]({artifact_type})[/] {artifact_name}"
        self.update(Text.from_markup(display_text))
    
    def on_click(self) -> None:
        """Handle click event - send message to parent."""
        self.post_message(
            self.Clicked(self.artifact_name, self.artifact_type, self.description)
        )


class ServerWidget(Vertical):
    """Individual server display widget that can be updated independently."""
    
    def __init__(self, server_name: str, **kwargs):
        """Initialize the server widget."""
        super().__init__(**kwargs)
        self.server_name = server_name
        self._connection_status = ConnectionStatus.DISCONNECTED
        self._operational_status = ""
        self._reconnect_info: dict[str, Any] = {}
        self._error_message: str | None = None
        self._artifacts: dict[str, list[dict[str, str | None]]] = {"tools": [], "prompts": [], "resources": []}
        self._last_check_time = 0.0
        self._artifact_widgets: dict[str, ArtifactItem] = {}
    
    def compose(self) -> ComposeResult:
        """Compose the server widget with header and artifacts."""
        # Header will be added dynamically
        # Sanitize server name for widget ID
        safe_server_name = sanitize_widget_id(self.server_name)
        yield Static("", id=f"server-header-{safe_server_name}")
    
    def on_mount(self) -> None:
        """Initialize display after mount."""
        self._update_display()
    
    def on_artifact_item_clicked(self, event: ArtifactItem.Clicked) -> None:
        """Handle artifact click - show overlay widget (non-blocking)."""
        # Defer overlay update to after current UI refresh to prevent blocking
        self.app.call_after_refresh(self._show_artifact_overlay, event)

    def _show_artifact_overlay(self, event: ArtifactItem.Clicked) -> None:
        """Actually show the overlay (called after UI refresh to prevent blocking)."""
        # Navigate up the widget tree to find MCPPanel
        # ServerWidget -> ScrollableContainer -> MCPPanel
        mcp_panel = None
        current = self.parent
        while current is not None:
            if isinstance(current, MCPPanel):
                mcp_panel = current
                break
            current = current.parent

        if mcp_panel is None:
            logger.error("Could not find MCPPanel in widget tree")
            return

        # Get the persistent overlay
        overlay = mcp_panel._artifact_overlay
        if overlay is None:
            logger.error("No artifact overlay found in MCPPanel")
            return

        # Update overlay content and show it
        try:
            logger.debug(f"Showing overlay for {event.artifact_name}")
            overlay.update_content(
                artifact_name=event.artifact_name,
                artifact_type=event.artifact_type,
                description=event.description
            )
            overlay.show_and_start_timer()
        except Exception as e:
            logger.error(f"Failed to show overlay: {e}", exc_info=True)
    
    def on_clicked(self, event: ArtifactItem.Clicked) -> None:
        """Handle artifact click - alternative handler name."""
        self.on_artifact_item_clicked(event)
    
    def _update_header_and_metadata(self) -> None:
        """Update header and metadata (status, timestamps) without touching artifacts."""
        # Get header widget
        safe_server_name = sanitize_widget_id(self.server_name)
        header_widget = self.query_one(f"#server-header-{safe_server_name}", Static)
        
        # Format header
        status_icon = get_status_icon(self._connection_status)
        status_text = get_status_text(self._connection_status)
        
        # Build status line with reconnection progress or error message
        status_details = []
        
        if self._connection_status == ConnectionStatus.RECONNECTING and self._reconnect_info:
            attempts = self._reconnect_info.get("attempts", 0)
            max_attempts = self._reconnect_info.get("max_attempts", 10)
            next_retry = self._reconnect_info.get("next_retry_delay")
            if next_retry is not None:
                status_details.append(f"[dim]attempt {attempts}/{max_attempts}, retry in {next_retry:.0f}s[/]")
            else:
                status_details.append(f"[dim]attempt {attempts}/{max_attempts}[/]")
        
        if self._connection_status == ConnectionStatus.ERROR and self._error_message:
            status_details.append(f"[red]{self._error_message}[/]")
        
        status_line = status_text
        if status_details:
            status_line += f" [dim]| {' | '.join(status_details)}[/]"
        
        header_text = f"\n[bold yellow]📡 {self.server_name}[/] {status_icon} {status_line}"
        header_widget.update(Text.from_markup(header_text))
        
        # Add operational status if present
        op_status_id = f"server-op-status-{safe_server_name}"
        try:
            op_status_widget = self.query_one(f"#{op_status_id}", Static)
        except:
            op_status_widget = Static("", id=op_status_id)
            self.mount(op_status_widget)
        
        if self._operational_status:
            op_status_widget.update(Text.from_markup(f"  Status: {self._operational_status}"))
            op_status_widget.display = True
        else:
            op_status_widget.display = False
        
        # Add last check time
        last_check_id = f"server-last-check-{safe_server_name}"
        try:
            last_check_widget = self.query_one(f"#{last_check_id}", Static)
        except:
            last_check_widget = Static("", id=last_check_id)
            self.mount(last_check_widget)
        last_check_str = format_time_hhmmss(self._last_check_time)
        last_check_widget.update(Text.from_markup(f"  [dim]Checked: {last_check_str}[/]"))
        
        # Update count line
        total = (
            len(self._artifacts.get("tools", [])) +
            len(self._artifacts.get("prompts", [])) +
            len(self._artifacts.get("resources", []))
        )
        count_id = f"server-count-{safe_server_name}"
        try:
            count_widget = self.query_one(f"#{count_id}", Static)
        except:
            count_widget = Static("", id=count_id)
            self.mount(count_widget)
        
        if total == 0:
            count_widget.update(Text.from_markup("  [dim]No artifacts[/]"))
        else:
            count_text = f"  [dim]({len(self._artifacts.get('tools', []))} tools, {len(self._artifacts.get('prompts', []))} prompts, {len(self._artifacts.get('resources', []))} resources)[/]"
            count_widget.update(Text.from_markup(count_text))
        
        # Add divider
        divider_id = f"server-divider-{safe_server_name}"
        try:
            divider_widget = self.query_one(f"#{divider_id}", Static)
        except:
            divider_widget = Static("", id=divider_id)
            self.mount(divider_widget)
        divider_widget.update(Text.from_markup("[dim]" + "─" * 30 + "[/]"))
    
    def _update_display(self) -> None:
        """Update the entire server widget display (used on initial mount)."""
        self._update_header_and_metadata()
        self._update_artifacts()
    
    def _update_artifacts(self) -> None:
        """Update artifact widgets."""
        # Calculate new artifact count
        new_total = (
            len(self._artifacts.get("tools", [])) +
            len(self._artifacts.get("prompts", [])) +
            len(self._artifacts.get("resources", []))
        )
        
        logger.debug(
            f"_update_artifacts called for {self.server_name}: "
            f"current widgets={len(self._artifact_widgets)}, "
            f"new artifacts: {len(self._artifacts.get('tools', []))} tools, "
            f"{len(self._artifacts.get('prompts', []))} prompts, "
            f"{len(self._artifacts.get('resources', []))} resources"
        )
        
        # Remove old artifact widgets
        removed_count = 0
        for artifact_id, widget in list(self._artifact_widgets.items()):
            try:
                widget.remove()
                removed_count += 1
            except Exception as e:
                logger.debug(f"Error removing artifact widget {artifact_id}: {e}")
            del self._artifact_widgets[artifact_id]
        
        logger.debug(f"Removed {removed_count} artifact widget(s) for {self.server_name}, will create {new_total} new one(s)")
        
        # Add new artifact widgets
        # Mount after the last check widget
        safe_server_name = sanitize_widget_id(self.server_name)
        try:
            last_check_widget = self.query_one(f"#server-last-check-{safe_server_name}", Static)
        except:
            last_check_widget = None
        
        # Tools
        tools = self._artifacts.get("tools", [])
        for tool in tools:
            tool_name = tool.get("name", "") if isinstance(tool, dict) else str(tool) if tool else ""
            if not tool_name:
                continue
            tool_desc = tool.get("description") if isinstance(tool, dict) else None
            # Sanitize the artifact ID to avoid special characters
            safe_tool_name = sanitize_widget_id(tool_name)
            artifact_id = f"artifact-{sanitize_widget_id(self.server_name)}-T-{safe_tool_name}"
            try:
                artifact_widget = ArtifactItem(
                    artifact_name=tool_name,
                    artifact_type="T",
                    description=tool_desc,
                    id=artifact_id
                )
                if last_check_widget:
                    self.mount(artifact_widget, after=last_check_widget)
                    last_check_widget = artifact_widget
                else:
                    self.mount(artifact_widget)
                    last_check_widget = artifact_widget
                self._artifact_widgets[artifact_id] = artifact_widget
            except Exception as e:
                logger.error(f"Error creating artifact widget for tool {tool_name}: {e}")
        
        # Prompts
        prompts = self._artifacts.get("prompts", [])
        for prompt in prompts:
            prompt_name = prompt.get("name", "") if isinstance(prompt, dict) else str(prompt) if prompt else ""
            if not prompt_name:
                continue
            prompt_desc = prompt.get("description") if isinstance(prompt, dict) else None
            # Sanitize the artifact ID to avoid special characters
            safe_prompt_name = sanitize_widget_id(prompt_name)
            artifact_id = f"artifact-{sanitize_widget_id(self.server_name)}-P-{safe_prompt_name}"
            try:
                artifact_widget = ArtifactItem(
                    artifact_name=prompt_name,
                    artifact_type="P",
                    description=prompt_desc,
                    id=artifact_id
                )
                if last_check_widget:
                    self.mount(artifact_widget, after=last_check_widget)
                    last_check_widget = artifact_widget
                else:
                    self.mount(artifact_widget)
                    last_check_widget = artifact_widget
                self._artifact_widgets[artifact_id] = artifact_widget
            except Exception as e:
                logger.error(f"Error creating artifact widget for prompt {prompt_name}: {e}")
        
        # Resources
        resources = self._artifacts.get("resources", [])
        for resource in resources:
            resource_name = resource.get("name", "") if isinstance(resource, dict) else str(resource) if resource else ""
            if not resource_name:
                continue
            resource_desc = resource.get("description") if isinstance(resource, dict) else None
            # Extract resource display name from URI if needed
            resource_display = resource_name
            if resource_name and "://" in resource_name:
                parts = resource_name.split("/")
                resource_display = parts[-1] if parts else resource_name
            # Sanitize the artifact ID to avoid special characters
            safe_resource_name = sanitize_widget_id(resource_name)
            artifact_id = f"artifact-{sanitize_widget_id(self.server_name)}-R-{safe_resource_name}"
            try:
                artifact_widget = ArtifactItem(
                    artifact_name=resource_display,
                    artifact_type="R",
                    description=resource_desc,
                    id=artifact_id
                )
                if last_check_widget:
                    self.mount(artifact_widget, after=last_check_widget)
                    last_check_widget = artifact_widget
                else:
                    self.mount(artifact_widget)
                    last_check_widget = artifact_widget
                self._artifact_widgets[artifact_id] = artifact_widget
            except Exception as e:
                logger.error(f"Error creating artifact widget for resource {resource_name}: {e}")
        
        logger.debug(
            f"Completed _update_artifacts for {self.server_name}: "
            f"created {len(self._artifact_widgets)} widget(s)"
        )
    
    def update_data(
        self,
        connection_status: ConnectionStatus | None = None,
        operational_status: str | None = None,
        artifacts: dict[str, list[dict[str, str | None]]] | None = None,
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
        artifacts_changed = False
        
        # Update internal state and track changes
        if connection_status is not None:
            self._connection_status = connection_status
            if connection_status != ConnectionStatus.ERROR:
                self._error_message = None
        
        if operational_status is not None:
            self._operational_status = operational_status
        
        if artifacts is not None:
            # Check if artifacts actually changed before updating
            # First check if we have no artifacts currently (initial state)
            current_total = (
                len(self._artifacts.get("tools", [])) +
                len(self._artifacts.get("prompts", [])) +
                len(self._artifacts.get("resources", []))
            )
            new_total = (
                len(artifacts.get("tools", [])) +
                len(artifacts.get("prompts", [])) +
                len(artifacts.get("resources", []))
            )
            
            # If we're going from empty to non-empty or vice versa, always update
            if (current_total == 0 and new_total > 0) or (current_total > 0 and new_total == 0):
                artifacts_changed = True
            # Otherwise, do a deep comparison of the actual content
            elif self._artifacts != artifacts:
                # Use deep comparison - Python's dict equality should work for nested structures
                # but we need to ensure we're comparing the actual content
                artifacts_changed = True
            
            if artifacts_changed:
                # Store a deep copy to avoid reference issues
                import copy
                self._artifacts = copy.deepcopy(artifacts)
        
        if last_check_time is not None:
            self._last_check_time = last_check_time
        
        if reconnect_info is not None:
            self._reconnect_info = reconnect_info
        
        if error_message is not None:
            self._error_message = error_message
        
        # Only update display if necessary
        # Update header/metadata always (status, timestamps, etc.)
        self._update_header_and_metadata()
        
        # Only update artifacts if they actually changed
        # This prevents unnecessary removal/recreation of artifact widgets
        if artifacts_changed:
            logger.debug(
                f"Artifacts changed for {self.server_name}: "
                f"{len(self._artifacts.get('tools', []))} tools, "
                f"{len(self._artifacts.get('prompts', []))} prompts, "
                f"{len(self._artifacts.get('resources', []))} resources"
            )
            self._update_artifacts()
        else:
            # Log when artifacts are provided but unchanged (for debugging)
            if artifacts is not None:
                logger.debug(
                    f"Artifacts unchanged for {self.server_name}, skipping widget update"
                )


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
        self._artifact_overlay: ArtifactDescriptionOverlay | None = None

    def compose(self) -> ComposeResult:
        """Compose the panel with header and scrollable content."""
        # Persistent artifact overlay - FIRST child so it appears at TOP when shown
        # This is a normal child (no layer/dock), so it will appear within the MCP panel area
        overlay = ArtifactDescriptionOverlay(
            artifact_name="",
            artifact_type="T",
            description="",
            id="artifact-description-overlay"
        )
        overlay.display = False  # Hidden by default
        self._artifact_overlay = overlay
        yield overlay

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
        artifacts: dict[str, list[dict[str, str | None]]] | None = None,
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
        servers_data: dict[str, dict[str, list[dict[str, str | None]]]],
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
        servers_data: dict[str, dict[str, list[dict[str, str | None]]]],
        server_statuses: dict[str, ConnectionStatus] | None = None,
        server_last_check: dict[str, float] | None = None,
    ):
        """
        Update the panel with server data and connection status.
        
        This is a compatibility method that calls update_all_servers.
        """
        self.update_all_servers(servers_data, server_statuses, server_last_check)
