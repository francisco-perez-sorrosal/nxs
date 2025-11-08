"""Artifact-related domain types."""

from typing import Dict, List

__all__ = [
    "ArtifactRecord",
    "ArtifactCollection",
]

# Type aliases for artifact data structures
ArtifactRecord = Dict[str, str | None]
ArtifactCollection = Dict[str, List[ArtifactRecord]]
