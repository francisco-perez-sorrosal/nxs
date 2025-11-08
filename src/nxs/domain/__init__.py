"""Domain layer - pure business rules and abstractions with zero external dependencies.

This layer contains:
- protocols: Interfaces for all implementations
- types: Shared domain types (ConnectionStatus, ArtifactCollection, etc.)
- events: Domain events and event bus
- exceptions: Domain-specific exceptions

The domain layer has NO dependencies on application, infrastructure, or presentation layers.
All other layers depend on the domain layer.
"""
