from nxs.mcp_client.client import ConnectionStatus
from nxs.tui.formatters import (
    format_artifact_counts_text,
    format_last_check_text,
    format_server_header_text,
    format_status_line_markup,
    get_status_icon,
    sanitize_widget_id,
)


def test_get_status_icon_connected():
    icon = get_status_icon(ConnectionStatus.CONNECTED)
    assert icon == "🟢"


def test_format_status_line_with_reconnect_details():
    markup = format_status_line_markup(
        ConnectionStatus.RECONNECTING,
        {"attempts": 2, "max_attempts": 5, "next_retry_delay": 3.2},
        None,
    )
    assert "attempt 2/5" in markup
    assert "retry in 3" in markup


def test_format_server_header_includes_status():
    header = format_server_header_text(
        "server1",
        ConnectionStatus.CONNECTED,
        reconnect_info=None,
        error_message=None,
    )
    assert "server1" in header.plain
    assert "Connected" in header.plain


def test_format_last_check_text(monkeypatch):
    monkeypatch.setattr("nxs.utils.format_time_hhmmss", lambda value: "12:34:56")
    text = format_last_check_text(0.0)
    assert "12:34:56" in text.plain


def test_format_artifact_counts_text():
    text = format_artifact_counts_text(1, 2, 3)
    assert "(1 tools, 2 prompts, 3 resources)" in text.plain


def test_sanitize_widget_id_removes_special_characters():
    sanitized = sanitize_widget_id("http://example.com/resource")
    assert sanitized.isidentifier()

