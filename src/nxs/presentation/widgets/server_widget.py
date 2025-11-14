"""
Widget representing a single MCP server and its artifacts.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical

from nxs.logger import get_logger
from nxs.domain.types import ConnectionStatus
from nxs.presentation.formatters import (
    format_artifact_counts_text,
    format_last_check_text,
    format_server_header_text,
    sanitize_widget_id,
)

from .artifact_item import ArtifactItem
from .static_no_margin import StaticNoMargin

logger = get_logger("server_widget")


class ServerWidget(Vertical):
    """Display widget for an MCP server."""

    _ARTIFACT_MAPPINGS: tuple[tuple[str, str], ...] = (
        ("tools", "T"),
        ("prompts", "P"),
        ("resources", "R"),
    )

    def __init__(self, server_name: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.server_name = server_name
        self.styles.height = "auto"
        self.styles.width = "100%"
        self.styles.margin = 0
        self.styles.padding = 0
        self.styles.gap = 0  # type: ignore[attr-defined]
        self._connection_status: ConnectionStatus = ConnectionStatus.DISCONNECTED
        self._operational_status: str = ""
        self._reconnect_info: dict[str, Any] = {}
        self._error_message: str | None = None
        self._artifacts: dict[str, list[dict[str, str | None | bool]]] = {
            "tools": [],
            "prompts": [],
            "resources": [],
        }
        self._last_check_time = 0.0
        self._header_text: Text = Text("")

        safe_server_name = sanitize_widget_id(server_name)
        self._header = StaticNoMargin(
            "",
            id=f"server-header-{safe_server_name}",
        )
        self._operational = StaticNoMargin(
            "",
            id=f"server-op-status-{safe_server_name}",
        )
        self._operational.display = False
        self._last_check = StaticNoMargin(
            "",
            id=f"server-last-check-{safe_server_name}",
        )
        self._artifact_counts = StaticNoMargin(
            "",
            id=f"server-count-{safe_server_name}",
        )
        self._artifacts_container = Vertical(id=f"server-artifacts-{safe_server_name}")
        self._artifacts_container.styles.gap = 0  # type: ignore[attr-defined]
        self._artifacts_container.styles.margin = 0
        self._artifacts_container.styles.padding = 0
        self._artifacts_container.styles.height = "auto"
        self._artifacts_container.styles.min_height = 0
        self._divider = StaticNoMargin(
            "[dim]" + "─" * 30 + "[/]",
            id=f"server-divider-{safe_server_name}",
        )

    def compose(self) -> ComposeResult:
        yield self._header
        yield self._operational
        yield self._last_check
        yield self._artifact_counts
        yield self._artifacts_container
        yield self._divider

    @property
    def operational_status(self) -> str:
        return self._operational_status

    @property
    def header_text(self) -> Text:
        return self._header_text

    def update_data(
        self,
        connection_status: ConnectionStatus | None = None,
        operational_status: str | None = None,
        artifacts: dict[str, list[dict[str, str | None | bool]]] | None = None,
        last_check_time: float | None = None,
        reconnect_info: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> None:
        """
        Update the widget state and refresh relevant sections.
        """
        artifacts_changed = False

        if connection_status is not None:
            self._connection_status = connection_status
            if connection_status != ConnectionStatus.ERROR:
                self._error_message = None

        if operational_status is not None:
            self._operational_status = operational_status

        if artifacts is not None and artifacts != self._artifacts:
            self._artifacts = deepcopy(artifacts)
            artifacts_changed = True

        if last_check_time is not None:
            self._last_check_time = last_check_time

        if reconnect_info is not None:
            self._reconnect_info = reconnect_info

        if error_message is not None:
            self._error_message = error_message

        self._render_header()
        self._render_operational_status()
        self._render_last_check()
        self._render_counts()

        if artifacts_changed:
            self._render_artifacts()
        elif artifacts is not None:
            logger.debug(
                "Artifacts provided for %s but unchanged; skipping render",
                self.server_name,
            )

    def _render_header(self) -> None:
        # Don't show connection status for local tools (they don't have connections)
        show_connection_status = self.server_name != "Local Tools"
        header = format_server_header_text(
            self.server_name,
            self._connection_status,
            self._reconnect_info,
            self._error_message,
            show_connection_status=show_connection_status,
        )
        self._header_text = header
        self._header.update(header)

    def _render_operational_status(self) -> None:
        if self._operational_status:
            self._operational.update(Text.from_markup(f"  Status: {self._operational_status}"))
            self._operational.display = True
        else:
            self._operational.display = False

    def _render_last_check(self) -> None:
        # Don't show last check time for local tools
        if self.server_name == "Local Tools":
            self._last_check.display = False
        else:
            self._last_check.update(format_last_check_text(self._last_check_time))
            self._last_check.display = True

    def _render_counts(self) -> None:
        tools_count = len(self._artifacts.get("tools", []))
        prompts_count = len(self._artifacts.get("prompts", []))
        resources_count = len(self._artifacts.get("resources", []))
        self._artifact_counts.update(format_artifact_counts_text(tools_count, prompts_count, resources_count))

    def _render_artifacts(self) -> None:
        for child in list(self._artifacts_container.children):
            child.remove()

        for artifact in self._iterate_artifacts():
            self._artifacts_container.mount(artifact)

    def _iterate_artifacts(self) -> Iterable[ArtifactItem]:
        for key, code in self._ARTIFACT_MAPPINGS:
            for artifact in self._artifacts.get(key, []):
                name, description, enabled = self._extract_artifact_info(artifact, key)
                if not name:
                    continue
                artifact_id = f"artifact-{sanitize_widget_id(self.server_name)}-{code}-" f"{sanitize_widget_id(name)}"
                yield ArtifactItem(
                    artifact_name=name,
                    artifact_type=code,
                    description=description,
                    enabled=enabled,
                    id=artifact_id,
                )

    def _extract_artifact_info(
        self,
        artifact: dict[str, str | None | bool] | str | None,
        artifact_type: str,
    ) -> tuple[str, str | None, bool]:
        if artifact is None:
            logger.debug(f"Artifact is None for type {artifact_type}")
            return "", None, True

        if isinstance(artifact, dict):
            # Extract name - ensure it's a string
            name_value = artifact.get("name")
            if isinstance(name_value, str):
                raw_name = name_value
            elif name_value is None:
                raw_name = ""
            else:
                raw_name = str(name_value)
            
            # Extract description - ensure it's a string or None
            desc_value = artifact.get("description")
            if isinstance(desc_value, str):
                description = desc_value
            else:
                description = None
            
            # Extract enabled state (default to True for backward compatibility)
            enabled = artifact.get("enabled", True)
            if not isinstance(enabled, bool):
                enabled = True
            
            logger.debug(
                f"Extracted artifact info: name={raw_name!r}, type={artifact_type}, "
                f"has_description={description is not None}, enabled={enabled}"
            )
        else:
            raw_name = str(artifact)
            description = None
            enabled = True
            logger.debug(f"Artifact is string: {raw_name!r}")

        if artifact_type == "resources" and isinstance(raw_name, str) and "://" in raw_name:
            parts = raw_name.split("/")
            display = parts[-1] if parts else raw_name
        else:
            display = raw_name

        logger.debug(f"Final display name for {artifact_type}: {display!r}")
        return display, description, enabled
