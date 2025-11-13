"""Human-in-the-Loop Approval System.

This module provides a mechanism for requesting user approval during agent execution,
inspired by ADK's long-running operations pattern. It supports two main use cases:
1. Query analysis approval - validate complexity assessment before execution
2. Tool execution approval - confirm tool execution before running

The system uses async/await to block execution until user responds via the TUI.
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Optional, Union


class ApprovalType(Enum):
    """Type of approval request."""

    QUERY_ANALYSIS = "query_analysis"
    TOOL_EXECUTION = "tool_execution"


@dataclass
class ApprovalRequest:
    """Request for user approval.

    Attributes:
        id: Unique identifier for this request
        type: Type of approval (query analysis or tool execution)
        title: Short description shown in UI
        details: Type-specific details (complexity analysis or tool info)
        options: Available actions user can take
        default_option: Default selection (typically first option)
    """

    id: str
    type: ApprovalType
    title: str
    details: dict[str, Any]
    options: list[str]
    default_option: str = field(default="")

    def __post_init__(self):
        """Set default option if not provided."""
        if not self.default_option and self.options:
            self.default_option = self.options[0]


@dataclass
class ApprovalResponse:
    """Response to an approval request.

    Attributes:
        request_id: ID of the request this responds to
        approved: Primary approval decision
        selected_option: Which option the user selected
        metadata: Additional data (e.g., override strategy, "approve all" flag)
    """

    request_id: str
    approved: bool
    selected_option: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ApprovalConfig:
    """Configuration for approval system.

    Attributes:
        enabled: Global enable/disable for all approvals
        require_query_analysis_approval: Request approval for query complexity analysis
        require_tool_approval: Request approval for tool execution
        tool_whitelist: Set of tool names that never require approval
        auto_approve_simple_queries: Auto-approve SIMPLE complexity queries
    """

    enabled: bool = True
    require_query_analysis_approval: bool = False
    require_tool_approval: bool = False
    tool_whitelist: set[str] = field(default_factory=set)
    auto_approve_simple_queries: bool = True


class ApprovalManager:
    """Manages the approval request/response lifecycle.

    This class coordinates approval requests from the agent loop with user responses
    from the TUI. It uses asyncio.Future to block execution until a response is received.

    Usage:
        manager = ApprovalManager()
        manager.set_callback(ui_handler)

        # In agent code:
        request = ApprovalRequest(...)
        response = await manager.request_approval(request)

        # In UI code (triggered by callback):
        manager.submit_response(response)
    """

    def __init__(self, config: Optional[ApprovalConfig] = None):
        """Initialize the approval manager.

        Args:
            config: Approval configuration. If None, uses default config.
        """
        self.config = config or ApprovalConfig()
        self._pending_requests: dict[str, tuple[asyncio.Future, ApprovalRequest]] = {}
        self._callback: Optional[
            Union[
                Callable[[ApprovalRequest], None],
                Callable[[ApprovalRequest], Awaitable[None]],
            ]
        ] = None

        # Session-level memory for remembered decisions
        self._remembered_tools: dict[str, bool] = {}  # tool_name -> approved
        self._remembered_query_analysis: Optional[bool] = None

    def set_callback(
        self,
        callback: Union[
            Callable[[ApprovalRequest], None],
            Callable[[ApprovalRequest], Awaitable[None]],
        ],
    ) -> None:
        """Set the callback to invoke when approval is requested.

        Args:
            callback: Function (sync or async) to call with ApprovalRequest.
                     Should display UI and eventually call submit_response().
        """
        self._callback = callback

    async def request_approval(self, request: ApprovalRequest) -> ApprovalResponse:
        """Request user approval and block until response received.

        This is the main entry point for agent code that needs approval.
        It blocks execution until the user responds via submit_response().

        Args:
            request: The approval request with details for the user

        Returns:
            ApprovalResponse with user's decision

        Raises:
            RuntimeError: If no callback is set
        """
        if not self.config.enabled:
            # Approval disabled - auto-approve everything
            return ApprovalResponse(
                request_id=request.id,
                approved=True,
                selected_option=request.default_option,
                metadata={"auto_approved": True},
            )

        # Check for remembered decisions
        if request.type == ApprovalType.QUERY_ANALYSIS:
            if self._remembered_query_analysis is not None:
                return ApprovalResponse(
                    request_id=request.id,
                    approved=self._remembered_query_analysis,
                    selected_option="Approve" if self._remembered_query_analysis else "Cancel",
                    metadata={"remembered": True},
                )
        elif request.type == ApprovalType.TOOL_EXECUTION:
            tool_name = request.details.get("tool_name")
            if tool_name and tool_name in self._remembered_tools:
                approved = self._remembered_tools[tool_name]
                return ApprovalResponse(
                    request_id=request.id,
                    approved=approved,
                    selected_option="Approve" if approved else "Deny",
                    metadata={"remembered": True},
                )

        if not self._callback:
            raise RuntimeError(
                "No approval callback set. Call set_callback() before requesting approval."
            )

        # Create a Future that will be resolved when user responds
        future: asyncio.Future[ApprovalResponse] = asyncio.Future()
        self._pending_requests[request.id] = (future, request)

        # Trigger UI callback (non-blocking)
        if asyncio.iscoroutinefunction(self._callback):
            asyncio.create_task(self._callback(request))
        else:
            self._callback(request)

        # Block here until user responds
        response = await future

        # Clean up
        del self._pending_requests[request.id]

        return response

    def submit_response(self, response: ApprovalResponse) -> None:
        """Submit a response to a pending approval request.

        This is called by the UI when the user makes a decision.

        Args:
            response: The user's response

        Raises:
            KeyError: If no pending request with this ID exists
        """
        if response.request_id not in self._pending_requests:
            raise KeyError(
                f"No pending approval request with ID: {response.request_id}"
            )

        future, request = self._pending_requests[response.request_id]

        # Store remembered decisions if requested
        if response.metadata.get("remember_for_session"):
            if request.type == ApprovalType.QUERY_ANALYSIS:
                self._remembered_query_analysis = response.approved
            elif request.type == ApprovalType.TOOL_EXECUTION:
                tool_name = request.details.get("tool_name")
                if tool_name:
                    self._remembered_tools[tool_name] = response.approved

        future.set_result(response)

    def cancel_request(self, request_id: str, reason: str = "Cancelled") -> None:
        """Cancel a pending approval request.

        Args:
            request_id: ID of the request to cancel
            reason: Reason for cancellation
        """
        if request_id in self._pending_requests:
            future, _ = self._pending_requests[request_id]
            if not future.done():
                response = ApprovalResponse(
                    request_id=request_id,
                    approved=False,
                    selected_option="Cancel",
                    metadata={"cancelled": True, "reason": reason},
                )
                future.set_result(response)

    def has_pending_requests(self) -> bool:
        """Check if there are any pending approval requests.

        Returns:
            True if there are pending requests
        """
        return bool(self._pending_requests)

    def cancel_all(self, reason: str = "Cancelled all") -> None:
        """Cancel all pending approval requests.

        Args:
            reason: Reason for cancellation
        """
        for request_id in list(self._pending_requests.keys()):
            self.cancel_request(request_id, reason)

    def clear_session_memory(self) -> None:
        """Clear all remembered decisions for this session.

        This resets the session-level memory, useful when starting a new query.
        """
        self._remembered_tools.clear()
        self._remembered_query_analysis = None

    def get_remembered_tools(self) -> dict[str, bool]:
        """Get all remembered tool decisions.

        Returns:
            Dictionary mapping tool names to approval status
        """
        return self._remembered_tools.copy()

    def is_tool_remembered(self, tool_name: str) -> Optional[bool]:
        """Check if a tool has a remembered decision.

        Args:
            tool_name: Name of the tool

        Returns:
            True if approved, False if denied, None if not remembered
        """
        return self._remembered_tools.get(tool_name)


def create_approval_request(
    approval_type: ApprovalType,
    title: str,
    details: dict[str, Any],
    options: Optional[list[str]] = None,
) -> ApprovalRequest:
    """Helper function to create an approval request with a unique ID.

    Args:
        approval_type: Type of approval request
        title: Short description
        details: Request-specific details
        options: Available options. If None, uses defaults based on type.

    Returns:
        ApprovalRequest with unique ID
    """
    if options is None:
        if approval_type == ApprovalType.QUERY_ANALYSIS:
            options = ["Approve", "Override Strategy", "Cancel"]
        elif approval_type == ApprovalType.TOOL_EXECUTION:
            options = ["Approve", "Deny", "Approve All", "Deny All"]
        else:
            options = ["Approve", "Cancel"]

    return ApprovalRequest(
        id=str(uuid.uuid4()),
        type=approval_type,
        title=title,
        details=details,
        options=options,
    )
