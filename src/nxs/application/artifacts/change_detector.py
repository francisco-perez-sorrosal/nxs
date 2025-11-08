"""Utilities for detecting artifact changes."""

from __future__ import annotations

from .cache import ArtifactCache, ArtifactCollection


class ArtifactChangeDetector:
    """Determine whether artifacts for a server have changed."""

    def __init__(self, cache: ArtifactCache) -> None:
        self._cache = cache

    def has_changed(self, server_name: str, artifacts: ArtifactCollection) -> bool:
        """Check whether the provided artifacts differ from the cached value."""
        return self._cache.has_changed(server_name, artifacts)
