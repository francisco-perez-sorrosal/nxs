"""
Event handlers for NexusApp.

This package contains handlers for different types of events:
- QueryHandler: Handles query processing and agent loop callbacks

Note: Connection and refresh event handling has been moved directly into
RefreshService to eliminate unnecessary indirection layers.
"""

from .query_handler import QueryHandler

__all__ = ["QueryHandler"]
