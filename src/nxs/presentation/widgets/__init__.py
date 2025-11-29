"""
Nexus TUI Widgets - Custom Textual widgets for the Nexus interface.
"""

from .chat_panel import ChatPanel
from .thinking_panel import ThinkingPanel
from .input_field import NexusInput
from .autocomplete import NexusAutoComplete
from .artifact_panel import ArtifactPanel

# Legacy exports for backward compatibility
from .status_panel import StatusPanel
from .reasoning_trace_panel import ReasoningTracePanel

__all__ = [
    "ChatPanel",
    "ThinkingPanel",
    "NexusInput",
    "NexusAutoComplete",
    "ArtifactPanel",
    # Legacy - deprecated, use ThinkingPanel
    "StatusPanel",
    "ReasoningTracePanel",
]
