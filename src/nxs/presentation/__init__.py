"""
Nexus Presentation Layer - UI components for the Nexus application.

This package contains all presentation layer components including:
- TUI (Terminal User Interface) using Textual and Rich
- Widgets, handlers, services, formatters
- Completely separated from application and domain logic
"""

from .tui import NexusApp

__all__ = ["NexusApp"]
