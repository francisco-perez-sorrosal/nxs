"""ApprovalOverlay - Tool execution approval dialog.

This widget handles tool execution approvals with session memory options.
Query analysis (reasoning mode selection) is now handled via the footer checkbox.
"""

import json
from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Static

from nxs.application.approval import ApprovalRequest, ApprovalResponse, ApprovalType
from nxs.logger import get_logger

logger = get_logger("approval_overlay")


class ApprovalOverlay(ModalScreen[ApprovalResponse]):
    """Modal screen for tool execution approval requests.

    This screen handles tool execution approvals with session memory options.
    Note: Query analysis (reasoning mode) is now controlled via footer checkbox.
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", priority=True),
        Binding("ctrl+a", "approve", "Approve", show=True),
        Binding("ctrl+d", "deny", "Deny", show=False),
    ]

    def __init__(self, request: ApprovalRequest):
        """Initialize the unified approval overlay.

        Args:
            request: The approval request with all details
        """
        super().__init__()
        self.request = request
        logger.info(f"Created unified ApprovalOverlay for: {request.title}")
        logger.info(f"  Type: {request.type.value}")
        logger.info(f"  Details: {list(request.details.keys())}")

    def compose(self) -> ComposeResult:
        """Compose the unified approval dialog."""
        with Container(id="approval-dialog"):
            # Header
            yield Static(self.request.title, id="approval-header")

            # Scrollable content
            with VerticalScroll(id="approval-scroll"):
                # Section 1: Details
                with Vertical(classes="section"):
                    yield Static("[bold cyan]Details[/]", classes="section-title")
                    yield Static(self._format_details(), id="details-box")

                # Section 2: Options (Tool Execution only)
                if self.request.type == ApprovalType.TOOL_EXECUTION:
                    with Vertical(classes="section"):
                        yield Static("[bold green]Options[/]", classes="section-title")

                        # Remember checkbox
                        tool_name = self.request.details.get("tool_name", "this tool")
                        yield Checkbox(
                            f"Remember my choice for '{tool_name}' in this session",
                            value=False,
                            id="remember-checkbox",
                        )

            # Footer with action buttons
            with Horizontal(id="approval-footer"):
                yield from self._compose_buttons()

    def _compose_buttons(self) -> ComposeResult:
        """Compose action buttons for tool execution approval."""
        yield Button("Approve", id="btn-approve", classes="btn-approve")
        yield Button("Deny", id="btn-deny", classes="btn-deny")
        yield Button("Approve All", id="btn-approve-all", classes="btn-approve-all")
        yield Button("Deny All", id="btn-deny-all", classes="btn-deny-all")

    def _format_details(self) -> str:
        """Format request details for display."""
        details = self.request.details

        if self.request.type == ApprovalType.TOOL_EXECUTION:
            return self._format_tool_execution(details)
        else:
            return f"[yellow]Details:[/]\n{json.dumps(details, indent=2)}"

    def _format_tool_execution(self, details: dict) -> str:
        """Format tool execution details."""
        lines = []

        # Tool name
        tool_name = details.get("tool_name", "Unknown")
        lines.append(f"[bold]Tool:[/] [yellow]{tool_name}[/]")

        # Description
        description = details.get("description", "")
        if description:
            lines.append(f"\n[bold]Description:[/]\n[dim]{description}[/]")

        # Input parameters
        input_params = details.get("input", {})
        if input_params:
            lines.append(f"\n[bold]Parameters:[/]")
            params_json = json.dumps(input_params, indent=2)
            lines.append(f"[dim]{params_json}[/]")

        return "\n".join(lines)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events."""
        button_id = event.button.id
        logger.info(f"Button pressed: {button_id}")

        if button_id == "btn-approve":
            self._handle_approve()
        elif button_id == "btn-deny":
            self._handle_deny()
        elif button_id == "btn-approve-all":
            self._handle_approve_all()
        elif button_id == "btn-deny-all":
            self._handle_deny_all()

    def _handle_approve(self) -> None:
        """Handle approve action."""
        logger.info("User clicked Approve")

        # Get remember checkbox state
        remember = False
        try:
            checkbox = self.query_one("#remember-checkbox", Checkbox)
            remember = checkbox.value
        except Exception:
            remember = False

        metadata: dict[str, Any] = {"remember_for_session": remember}

        response = ApprovalResponse(
            request_id=self.request.id,
            approved=True,
            selected_option="Approve",
            metadata=metadata,
        )

        logger.info(f"Dismissing with response: approved=True, metadata={metadata}")
        self.dismiss(response)

    def _handle_deny(self) -> None:
        """Handle deny action."""
        logger.info("User clicked Deny")

        # Get remember checkbox state
        try:
            checkbox = self.query_one("#remember-checkbox", Checkbox)
            remember = checkbox.value
        except Exception:
            remember = False

        response = ApprovalResponse(
            request_id=self.request.id,
            approved=False,
            selected_option="Deny",
            metadata={"remember_for_session": remember},
        )

        self.dismiss(response)

    def _handle_approve_all(self) -> None:
        """Handle approve all action."""
        logger.info("User clicked Approve All")

        response = ApprovalResponse(
            request_id=self.request.id,
            approved=True,
            selected_option="Approve All",
            metadata={"approve_all": True, "remember_for_session": True},
        )

        self.dismiss(response)

    def _handle_deny_all(self) -> None:
        """Handle deny all action."""
        logger.info("User clicked Deny All")

        response = ApprovalResponse(
            request_id=self.request.id,
            approved=False,
            selected_option="Deny All",
            metadata={"deny_all": True, "remember_for_session": True},
        )

        self.dismiss(response)

    def action_approve(self) -> None:
        """Keyboard shortcut: Approve (Ctrl+A)."""
        self._handle_approve()

    def action_deny(self) -> None:
        """Keyboard shortcut: Deny (Ctrl+D)."""
        self._handle_deny()

    def action_cancel(self) -> None:
        """Cancel the approval request (ESC)."""
        logger.info("User cancelled")

        response = ApprovalResponse(
            request_id=self.request.id,
            approved=False,
            selected_option="Cancel",
            metadata={"cancelled": True},
        )

        self.dismiss(response)
