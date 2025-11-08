"""
MCPPanel - Scrollable overview of MCP servers and their artifacts.
"""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.containers import ScrollableContainer, Vertical
from textual.widgets import Static

from nxs.logger import get_logger
from nxs.domain.types import ConnectionStatus
from nxs.presentation.formatters import sanitize_widget_id
from nxs.presentation.widgets.artifact_item import ArtifactItem
from nxs.presentation.widgets.artifact_overlay import ArtifactDescriptionOverlay
from nxs.presentation.widgets.server_widget import ServerWidget
from nxs.presentation.widgets.static_no_margin import StaticNoMargin

logger = get_logger("mcp_panel")


class MCPPanel(Vertical):
    """Panel displaying MCP servers and associated artifacts."""

    BORDER_TITLE = "MCP Servers"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._server_widgets: dict[str, ServerWidget] = {}
        self._artifact_overlay: ArtifactDescriptionOverlay | None = None
        self._empty_message: Static | None = None
        self._scroll_container: ScrollableContainer | None = None

    def compose(self) -> ComposeResult:
        overlay = ArtifactDescriptionOverlay(
            artifact_name="",
            artifact_type="T",
            description="",
            id="artifact-description-overlay",
        )
        overlay.display = False
        self._artifact_overlay = overlay
        yield overlay

        header = Static("[bold cyan]MCP Servers & Artifacts[/]", id="mcp-header")
        yield header

        yield Static("[dim]" + "─" * 30 + "[/]", id="mcp-divider-top")

        with ScrollableContainer(id="mcp-servers-container") as servers_container:
            servers_container.styles.gap = 0
            servers_container.styles.height = "auto"
            servers_container.styles.padding = 0
            servers_container.styles.margin = 0
            self._scroll_container = servers_container
            empty_message = StaticNoMargin(
                "[dim]No MCP servers connected[/]",
                id="mcp-empty-message",
            )
            self._empty_message = empty_message
            yield empty_message

    def on_mount(self) -> None:
        self._ensure_scroll_container()

    def update_server(
        self,
        server_name: str,
        connection_status: ConnectionStatus | None = None,
        operational_status: str | None = None,
        artifacts: dict[str, list[dict[str, str | None]]] | None = None,
        last_check_time: float | None = None,
        reconnect_info: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> None:
        widget = self._server_widgets.get(server_name)
        if widget is None:
            widget = self._create_server_widget(server_name)
        widget.update_data(
            connection_status=connection_status,
            operational_status=operational_status,
            artifacts=artifacts,
            last_check_time=last_check_time,
            reconnect_info=reconnect_info,
            error_message=error_message,
        )
        self._update_empty_message()

    def _create_server_widget(self, server_name: str) -> ServerWidget:
        container = self._ensure_scroll_container()
        safe_name = sanitize_widget_id(server_name)
        widget = ServerWidget(server_name, id=f"mcp-server-{safe_name}")
        if self._empty_message is not None:
            if self._empty_message.parent:
                self._empty_message.remove()
            self._empty_message = None
        if self._server_widgets:
            container.mount(
                StaticNoMargin("[dim]" + "─" * 30 + "[/]", id=f"mcp-divider-{safe_name}")
            )
        container.mount(widget)
        self._server_widgets[server_name] = widget
        return widget

    def _ensure_scroll_container(self) -> ScrollableContainer:
        if self._scroll_container is None:
            try:
                self._scroll_container = self.query_one(
                    "#mcp-servers-container", ScrollableContainer
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.error("Unable to locate servers container: %s", exc)
                raise
        return self._scroll_container

    def _update_empty_message(self) -> None:
        if self._empty_message:
            self._empty_message.display = len(self._server_widgets) == 0

    def _remove_server_widget(self, server_name: str) -> None:
        widget = self._server_widgets.pop(server_name, None)
        if widget is None:
            return

        # Remove divider preceding the widget if it exists
        divider_id = f"mcp-divider-{sanitize_widget_id(server_name)}"
        if widget.parent is not None:
            try:
                divider = widget.parent.query_one(f"#{divider_id}", Static)
            except Exception:
                divider = None
            if divider is not None:
                divider.remove()

        widget.remove()

        if not self._server_widgets and self._empty_message is None:
            container = self._ensure_scroll_container()
            empty_message = StaticNoMargin(
                "[dim]No MCP servers connected[/]", id="mcp-empty-message"
            )
            if container.children:
                container.mount(empty_message, before=container.children[0])
            else:
                container.mount(empty_message)
            self._empty_message = empty_message

    def update_all_servers(
        self,
        servers_data: dict[str, dict[str, list[dict[str, str | None]]]],
        server_statuses: dict[str, ConnectionStatus] | None = None,
        server_last_check: dict[str, float] | None = None,
    ) -> None:
        if server_statuses and not servers_data:
            for server_name in server_statuses:
                servers_data[server_name] = {"tools": [], "prompts": [], "resources": []}

        for server_name, artifacts in servers_data.items():
            status = server_statuses.get(server_name) if server_statuses else None
            last_check = server_last_check.get(server_name) if server_last_check else None

            operational_status_override: str | None = None
            existing_widget = self._server_widgets.get(server_name)
            if existing_widget and "Fetching artifacts" in existing_widget.operational_status:
                if not any(token in existing_widget.operational_status for token in ("✓", "✗", "Error", "No artifacts")):
                    operational_status_override = ""

            self.update_server(
                server_name=server_name,
                connection_status=status,
                operational_status=operational_status_override,
                artifacts=artifacts,
                last_check_time=last_check,
            )

        existing_servers = set(servers_data.keys())
        for server_name in list(self._server_widgets):
            if server_name not in existing_servers:
                self._remove_server_widget(server_name)

        self._update_empty_message()

    def update_servers(
        self,
        servers_data: dict[str, dict[str, list[dict[str, str | None]]]],
        server_statuses: dict[str, ConnectionStatus] | None = None,
        server_last_check: dict[str, float] | None = None,
    ) -> None:
        self.update_all_servers(servers_data, server_statuses, server_last_check)

    def update_server_status(self, server_name: str, status: ConnectionStatus) -> None:
        self.update_server(server_name, connection_status=status)

    def update_reconnect_info(self, server_name: str, reconnect_info: dict[str, Any]) -> None:
        self.update_server(server_name, reconnect_info=reconnect_info)
        error_message = reconnect_info.get("error_message")
        if error_message:
            self.update_server(server_name, error_message=error_message)

    def set_fetch_status(self, server_name: str, status_message: str) -> None:
        self.update_server(server_name, operational_status=status_message)

    def clear_fetch_status(self, server_name: str) -> None:
        self.update_server(server_name, operational_status="")

    def on_artifact_item_clicked(self, event: ArtifactItem.Clicked) -> None:
        overlay = self._artifact_overlay
        if overlay is None:
            logger.error("Artifact overlay not initialized; cannot show artifact details")
            return

        def _show_overlay() -> None:
            try:
                overlay.update_content(
                    artifact_name=event.artifact_name,
                    artifact_type=event.artifact_type,
                    description=event.description,
                )
                overlay.show_and_start_timer()
            except Exception as exc:  # pragma: no cover - defensive
                logger.error("Failed to show artifact overlay: %s", exc, exc_info=True)

        self.app.call_after_refresh(_show_overlay)

