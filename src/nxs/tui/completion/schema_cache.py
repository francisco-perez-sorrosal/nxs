"""
Adapters exposing prompt schemas through a mapping interface.

The argument suggestion generator expects a dict-like cache, while the
PromptService exposes accessor methods.  This module bridges that gap
without copying data.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Iterator, Optional

from nxs.tui.services.prompt_service import PromptService


class SchemaCacheMapping(Mapping[str, tuple[Any, str]]):
    """
    Lazy mapping wrapper around ``PromptService.get_cached_schema``.

    Providing a mapping view keeps the generator decoupled from the
    concrete cache implementation and avoids materialising copies of the
    underlying cache.
    """

    def __init__(self, prompt_service: PromptService) -> None:
        self._prompt_service = prompt_service

    def __getitem__(self, key: str) -> tuple[Any, str]:
        cached = self._prompt_service.get_cached_schema(key)
        if cached is None:
            raise KeyError(key)
        return cached

    def __iter__(self) -> Iterator[str]:
        # The prompt service cache does not currently expose keys.  The
        # generator only relies on membership and ``__getitem__`` so we
        # surface an empty iterator to satisfy ``Mapping``.
        return iter(())

    def __len__(self) -> int:
        # PromptService caches do not support len(); return 0 to satisfy
        # the ``Mapping`` contract.  Consumers never rely on the value.
        return 0

    def get(self, key: str, default: Optional[tuple[Any, str]] = None) -> Optional[tuple[Any, str]]:
        cached = self._prompt_service.get_cached_schema(key)
        if cached is None:
            return default
        return cached

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, str):
            return False
        return self._prompt_service.get_cached_schema(key) is not None

