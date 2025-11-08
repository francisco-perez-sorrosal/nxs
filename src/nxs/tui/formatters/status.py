"""
Formatting helpers for MCP connection status and artifact displays.
"""

from __future__ import annotations

from typing import Any

from rich.text import Text

from nxs.mcp_client.client import ConnectionStatus


def sanitize_widget_id(name: str) -> str:
    """
    Sanitize a value for safe usage as a Textual widget id.

    Textual ids are also used in CSS selectors, so replace characters that
    would break selectors with underscores.
    """
    sanitized = (
        name.replace("://", "_")
        .replace(":", "_")
        .replace("/", "_")
        .replace(" ", "_")
        .replace(".", "_")
        .replace("-", "_")
        .replace("+", "_")
    )
    return "".join(char if char.isalnum() or char == "_" else "_" for char in sanitized)


def get_status_icon(status: ConnectionStatus) -> str:
    """Return the emoji used for the given connection status."""
    status_icons = {
        ConnectionStatus.CONNECTED: "🟢",
        ConnectionStatus.DISCONNECTED: "🔴",
        ConnectionStatus.CONNECTING: "🟡",
        ConnectionStatus.RECONNECTING: "🟡",
        ConnectionStatus.ERROR: "🔴",
    }
    return status_icons.get(status, "⚪")


def get_status_text(status: ConnectionStatus) -> str:
    """Return the Rich markup representing the connection status."""
    status_texts = {
        ConnectionStatus.CONNECTED: "[green]Connected[/]",
        ConnectionStatus.DISCONNECTED: "[red]Disconnected[/]",
        ConnectionStatus.CONNECTING: "[yellow]Connecting...[/]",
        ConnectionStatus.RECONNECTING: "[yellow]Reconnecting...[/]",
        ConnectionStatus.ERROR: "[red]Error[/]",
    }
    return status_texts.get(status, "[dim]Unknown[/]")


def format_status_line_markup(
    status: ConnectionStatus,
    reconnect_info: dict[str, Any] | None,
    error_message: str | None,
) -> str:
    """
    Build the markup for the status line, including reconnection details or errors.
    """
    status_details: list[str] = []

    if status == ConnectionStatus.RECONNECTING and reconnect_info:
        attempts = reconnect_info.get("attempts", 0)
        max_attempts = reconnect_info.get("max_attempts", 10)
        next_retry = reconnect_info.get("next_retry_delay")
        if next_retry is not None:
            status_details.append(
                f"[dim]attempt {attempts}/{max_attempts}, retry in {next_retry:.0f}s[/]"
            )
        else:
            status_details.append(f"[dim]attempt {attempts}/{max_attempts}[/]")

    if status == ConnectionStatus.ERROR and error_message:
        status_details.append(f"[red]{error_message}[/]")

    status_line = get_status_text(status)
    if status_details:
        status_line += f" [dim]| {' | '.join(status_details)}[/]"
    return status_line


def format_server_header_text(
    server_name: str,
    status: ConnectionStatus,
    reconnect_info: dict[str, Any] | None,
    error_message: str | None,
) -> Text:
    """Return the Rich Text header for the server widget."""
    status_line = format_status_line_markup(status, reconnect_info, error_message)
    status_icon = get_status_icon(status)
    header_text = f"[bold yellow]📡 {server_name}[/] {status_icon} {status_line}"
    return Text.from_markup(header_text)


def format_last_check_text(last_check_timestamp: float) -> Text:
    """Return the Rich Text describing the last check instant."""
    from nxs.utils import format_time_hhmmss  # Lazy import to avoid cycles

    last_check_str = format_time_hhmmss(last_check_timestamp)
    return Text.from_markup(f"  [dim]Checked: {last_check_str}[/]")


def format_artifact_counts_text(
    tools: int,
    prompts: int,
    resources: int,
) -> Text:
    """Return the Rich Text describing artifact counts."""
    if tools + prompts + resources == 0:
        return Text.from_markup("  [dim]No artifacts[/]")
    return Text.from_markup(
        f"  [dim]({tools} tools, {prompts} prompts, {resources} resources)[/]"
    )

