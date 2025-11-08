"""Artifact-specific cache utilities."""

from __future__ import annotations

from copy import deepcopy
from typing import Dict, List

from nxs.infrastructure.cache import Cache, MemoryCache

ArtifactRecord = Dict[str, str | None]
ArtifactCollection = Dict[str, List[ArtifactRecord]]


class ArtifactCache:
    """Typed wrapper around the generic cache protocol for artifacts."""

    def __init__(
        self,
        cache: Cache[str, ArtifactCollection] | None = None,
    ) -> None:
        self._cache: Cache[str, ArtifactCollection] = cache or MemoryCache()

    def get(self, server_name: str) -> ArtifactCollection | None:
        """Retrieve cached artifacts for a server (deep copy)."""
        cached = self._cache.get(server_name)
        if cached is None:
            return None
        return deepcopy(cached)

    def set(self, server_name: str, artifacts: ArtifactCollection) -> None:
        """Store artifacts for a server using a defensive copy."""
        self._cache.set(server_name, deepcopy(artifacts))

    def clear(self, server_name: str | None = None) -> None:
        """Clear cache for a server or all servers."""
        self._cache.clear(server_name)

    def has_changed(self, server_name: str, artifacts: ArtifactCollection) -> bool:
        """Check if artifacts have changed compared to cache."""
        return self._cache.has_changed(server_name, artifacts)
