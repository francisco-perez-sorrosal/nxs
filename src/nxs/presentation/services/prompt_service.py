"""
PromptService for managing prompt caching and preloading.

This service handles:
- Caching prompt information and schemas
- Preloading prompt data for all commands
- Formatting prompt arguments for display
- Providing cached prompt data to other components
"""

from typing import TYPE_CHECKING

from nxs.application.artifact_manager import ArtifactManager
from nxs.domain.protocols import Cache
from nxs.infrastructure.cache import MemoryCache
from nxs.logger import get_logger

if TYPE_CHECKING:
    from mcp.types import Prompt

logger = get_logger("prompt_service")


class PromptService:
    """
    Handles prompt caching and preloading.
    
    This service manages the caching of prompt information and schemas,
    preloads prompt data for all commands, and provides cached data
    to other components like the autocomplete widget.
    """

    def __init__(
        self,
        artifact_manager: ArtifactManager,
        prompt_info_cache: Cache[str, str | None] | None = None,
        prompt_schema_cache: Cache[str, tuple] | None = None,
    ):
        """
        Initialize the PromptService.

        Args:
            artifact_manager: The ArtifactManager instance
            prompt_info_cache: Optional Cache instance for prompt argument info strings.
                             If None, a MemoryCache will be created.
            prompt_schema_cache: Optional Cache instance for prompt schema tuples.
                                If None, a MemoryCache will be created.
        """
        self.artifact_manager = artifact_manager
        self._prompt_info_cache: Cache[str, str | None] = (
            prompt_info_cache or MemoryCache[str, str | None]()
        )
        self._prompt_schema_cache: Cache[str, tuple] = (
            prompt_schema_cache or MemoryCache[str, tuple]()
        )

    async def preload_all(self, commands: list[str]) -> None:
        """
        Preload prompt information for all commands.

        This method fetches prompt information for all commands and
        caches both the formatted argument info strings and the full
        prompt schemas.

        Args:
            commands: List of command names to preload
        """
        try:
            logger.info(f"Preloading prompt information for {len(commands)} commands...")
            loaded_count = 0

            for command in commands:
                prompt_info = await self.artifact_manager.find_prompt(command)
                if prompt_info:
                    prompt, server_name = prompt_info
                    # Store full prompt object for argument expansion
                    self._prompt_schema_cache.set(command, (prompt, server_name))
                    # Extract argument info string for display
                    arg_info = self._format_prompt_arguments(prompt)
                    self._prompt_info_cache.set(command, arg_info)
                    loaded_count += 1
                    logger.debug(f"Preloaded info for '{command}': {arg_info}")

            logger.info(
                f"Successfully preloaded prompt information for {loaded_count} commands"
            )
        except Exception as e:
            logger.error(f"Failed to preload prompt info: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def get_cached_info(self, command: str) -> str | None:
        """
        Get cached prompt argument info for a command.

        Args:
            command: Command name

        Returns:
            Formatted argument info string or None if not cached
        """
        return self._prompt_info_cache.get(command)

    def get_cached_schema(self, command: str) -> tuple | None:
        """
        Get cached prompt schema for a command.

        Args:
            command: Command name

        Returns:
            Tuple of (Prompt, server_name) or None if not cached
        """
        return self._prompt_schema_cache.get(command)

    def _format_prompt_arguments(self, prompt: "Prompt") -> str | None:
        """
        Format prompt arguments into a readable string.

        Args:
            prompt: Prompt object

        Returns:
            Formatted argument string or None if no arguments
        """
        if not hasattr(prompt, "arguments") or not prompt.arguments:
            return None

        schema = prompt.arguments
        arg_names: list[str] = []
        required_args: list[str] = []

        # Handle different schema formats
        if isinstance(schema, list):
            for arg in schema:
                if hasattr(arg, "name"):
                    arg_names.append(arg.name)
                    if hasattr(arg, "required") and arg.required:
                        required_args.append(arg.name)
                elif isinstance(arg, dict):
                    arg_name = arg.get("name", "")
                    if arg_name:
                        arg_names.append(arg_name)
                        if arg.get("required", False):
                            required_args.append(arg_name)
        elif isinstance(schema, dict):
            properties = schema.get("properties", {})
            arg_names = list(properties.keys())
            required_args = schema.get("required", [])
        else:
            if hasattr(schema, "properties"):
                properties = getattr(schema, "properties", {})
                if isinstance(properties, dict):
                    arg_names = list(properties.keys())
            if hasattr(schema, "required"):
                required_args = getattr(schema, "required", [])

        if not arg_names:
            return None

        arg_str = ", ".join(arg_names)
        if required_args:
            req_str = ", ".join(required_args)
            return f"{arg_str} | Required: {req_str}"

        return arg_str

