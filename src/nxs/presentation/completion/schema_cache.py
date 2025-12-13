"""Schema cache for prompt argument completion."""

from typing import Any, Mapping, TYPE_CHECKING

if TYPE_CHECKING:
    from nxs.presentation.services.prompt_service import PromptService


class PromptSchemaCache(Mapping[str, tuple[Any, str]]):
    """Lightweight mapping wrapper over PromptService for schema access."""

    def __init__(self, service: "PromptService"):
        self._service = service

    def __getitem__(self, key: str) -> tuple[Any, str]:
        cached = self._service.get_cached_schema(key)
        if cached is None:
            raise KeyError(key)
        return cached

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, str):
            return False
        return self._service.get_cached_schema(key) is not None

    def __iter__(self):
        raise NotImplementedError("Iteration not supported")

    def __len__(self) -> int:
        raise NotImplementedError("Length not supported")
