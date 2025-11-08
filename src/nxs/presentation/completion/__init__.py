"""
Completion strategy utilities for the Nexus autocomplete widget.

This package provides a strategy-based decomposition for the different
completion flows (resources, commands, arguments) used by
`NexusAutoComplete`.
"""

from .strategy import CompletionStrategy
from .orchestrator import CompletionOrchestrator
from .resource_completion import ResourceCompletionStrategy
from .command_completion import CommandCompletionStrategy
from .argument_completion import ArgumentCompletionStrategy
from .schema_cache import SchemaCacheMapping
from .applier import CompletionApplier, compute_search_string, should_show_dropdown

__all__ = [
    "CompletionStrategy",
    "CompletionOrchestrator",
    "ResourceCompletionStrategy",
    "CommandCompletionStrategy",
    "ArgumentCompletionStrategy",
    "SchemaCacheMapping",
    "CompletionApplier",
    "compute_search_string",
    "should_show_dropdown",
]

