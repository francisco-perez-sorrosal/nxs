"""Unified ApprovalOverlay - All-in-one approval dialog with strategy selection.

This widget combines approval, strategy selection, and session memory into ONE beautiful dialog.
No more multiple modals - everything in one place with clear visual organization.
"""

import json
from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, RadioButton, RadioSet, Static, Label

from nxs.application.approval import ApprovalRequest, ApprovalResponse, ApprovalType
from nxs.logger import get_logger

logger = get_logger("approval_overlay")


class ApprovalOverlay(ModalScreen[ApprovalResponse]):
    """Unified modal screen for all approval requests.

    This screen handles both query analysis and tool execution approvals,
    with built-in strategy selection and session memory options.
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

                # Section 2: Execution Mode Selection (Query Analysis only)
                if self.request.type == ApprovalType.QUERY_ANALYSIS:
                    mode = self.request.details.get("mode")

                    if mode == "execution_choice":
                        # Simple two-button choice
                        with Vertical(classes="section"):
                            yield Static(
                                "[bold yellow]Execution Mode[/]",
                                classes="section-title",
                            )

                            with Horizontal(id="execution-choice-buttons"):
                                yield Button(
                                    "Execute Directly",
                                    id="btn-execute-direct",
                                    classes="btn-approve",
                                )
                                yield Button(
                                    "Analyze & Use Reasoning",
                                    id="btn-use-reasoning",
                                    classes="btn-approve",
                                )

                # Section 3: Options (Tool Execution only)
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
        """Compose action buttons based on request type."""
        if self.request.type == ApprovalType.QUERY_ANALYSIS:
            # For query analysis, button is in the strategy section, only show cancel here
            yield Button("Cancel", id="btn-cancel", variant="error")

        elif self.request.type == ApprovalType.TOOL_EXECUTION:
            yield Button("Approve", id="btn-approve", classes="btn-approve")
            yield Button("Deny", id="btn-deny", classes="btn-deny")
            yield Button("Approve All", id="btn-approve-all", classes="btn-approve-all")
            yield Button("Deny All", id="btn-deny-all", classes="btn-deny-all")

    def _format_details(self) -> str:
        """Format request details for display."""
        details = self.request.details

        if self.request.type == ApprovalType.QUERY_ANALYSIS:
            return self._format_query_analysis(details)
        elif self.request.type == ApprovalType.TOOL_EXECUTION:
            return self._format_tool_execution(details)
        else:
            return f"[yellow]Details:[/]\n{json.dumps(details, indent=2)}"

    def _format_query_analysis(self, details: dict) -> str:
        """Format query analysis details."""
        lines = []

        # Check if this is a simple execution mode choice
        mode = details.get("mode")
        if mode == "execution_choice":
            # Include the query text so user knows what they're approving
            query = details.get("query", "")
            if query:
                lines.append(f"[bold cyan]Query:[/] {query}\n")
            
            lines.append(
                "[bold]How would you like to execute this query?[/]\n\n"
                "[dim]• [cyan]Execute Directly[/]: Fast, immediate execution (no analysis)[/]\n"
                "[dim]• [yellow]Analyze & Use Reasoning[/]: Automatic complexity analysis, "
                "system picks best strategy (LIGHT or DEEP reasoning)[/]"
            )
        else:
            # Old strategy selection (fallback, shouldn't be used)
            lines.append(
                "[dim]Choose your execution strategy:[/]\n"
                "[dim]• [cyan]DIRECT[/]: Fast execution without planning[/]\n"
                "[dim]• [yellow]LIGHT_PLANNING[/]: 1-2 iterations with minimal planning[/]\n"
                "[dim]• [magenta]DEEP_REASONING[/]: Full reasoning with multiple iterations[/]"
            )

        return "\n".join(lines)

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

        if button_id == "btn-execute-direct":
            self._handle_execute_direct()
        elif button_id == "btn-use-reasoning":
            self._handle_use_reasoning()
        elif button_id == "btn-approve" or button_id == "strategy-accept-button":
            self._handle_approve()
        elif button_id == "btn-deny":
            self._handle_deny()
        elif button_id == "btn-approve-all":
            self._handle_approve_all()
        elif button_id == "btn-deny-all":
            self._handle_deny_all()
        elif button_id == "btn-cancel":
            self.action_cancel()

    def _handle_execute_direct(self) -> None:
        """Handle execute directly choice."""
        logger.info("User clicked Execute Directly")

        # Auto-remember query analysis decisions to prevent repeated prompts
        response = ApprovalResponse(
            request_id=self.request.id,
            approved=True,
            selected_option="Execute Directly",
            metadata={"use_reasoning": False, "remember_for_session": True},
        )

        logger.info(f"Dismissing with response: use_reasoning=False, remember_for_session=True")
        self.dismiss(response)

    def _handle_use_reasoning(self) -> None:
        """Handle use reasoning choice."""
        logger.info("User clicked Analyze & Use Reasoning")

        # Auto-remember query analysis decisions to prevent repeated prompts
        response = ApprovalResponse(
            request_id=self.request.id,
            approved=True,
            selected_option="Analyze & Use Reasoning",
            metadata={"use_reasoning": True, "remember_for_session": True},
        )

        logger.info(f"Dismissing with response: use_reasoning=True, remember_for_session=True")
        self.dismiss(response)

    def _handle_approve(self) -> None:
        """Handle approve action."""
        logger.info("User clicked Approve")

        # Get remember checkbox state (different ID for query analysis vs tool execution)
        remember = False
        if self.request.type == ApprovalType.QUERY_ANALYSIS:
            try:
                checkbox = self.query_one("#strategy-remember-checkbox", Checkbox)
                remember = checkbox.value
            except Exception:
                remember = False
        else:
            try:
                checkbox = self.query_one("#remember-checkbox", Checkbox)
                remember = checkbox.value
            except Exception:
                remember = False

        metadata: dict[str, Any] = {"remember_for_session": remember}

        # For query analysis, always pass the selected strategy
        if self.request.type == ApprovalType.QUERY_ANALYSIS:
            selected_strategy = self._get_selected_strategy()
            logger.info(f"Selected strategy: {selected_strategy}")

            # Always pass the selected strategy (even if it's the default)
            metadata["selected_strategy"] = selected_strategy

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

    def _get_selected_strategy(self) -> str:
        """Get the currently selected strategy from radio buttons.

        Returns:
            The selected strategy name
        """
        try:
            radio_set = self.query_one("#strategy-selector", RadioSet)
            pressed_button = radio_set.pressed_button

            if pressed_button and pressed_button.id:
                # Extract strategy from id like "strategy-direct"
                strategy = pressed_button.id.replace("strategy-", "")
                # Remove "(default)" suffix if present
                strategy = strategy.replace(" (default)", "")
                return strategy
        except Exception as e:
            logger.error(f"Error getting selected strategy: {e}", exc_info=True)

        # Fallback to recommended
        fallback = self.request.details.get("recommended_strategy", "")
        return fallback

    def action_approve(self) -> None:
        """Keyboard shortcut: Approve (Ctrl+A)."""
        self._handle_approve()

    def action_deny(self) -> None:
        """Keyboard shortcut: Deny (Ctrl+D)."""
        if self.request.type == ApprovalType.TOOL_EXECUTION:
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
