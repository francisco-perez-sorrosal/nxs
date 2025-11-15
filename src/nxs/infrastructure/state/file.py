"""File-based state provider implementation.

This module provides persistent state storage using JSON files on the local
filesystem. Each state key is stored as a separate JSON file.
"""

import json
import os
from pathlib import Path
from typing import Any

from nxs.logger import get_logger

logger = get_logger(__name__)


class FileStateProvider:
    """File-based state provider for local persistence.

    Stores state as JSON files in a specified directory. Each key corresponds
    to a separate file, with characters like ':' replaced with '__' for
    filesystem compatibility.

    Features:
    - Automatic directory creation
    - Safe file operations with error handling
    - Pretty-printed JSON for readability
    - Atomic writes (write to temp, then rename)

    Example:
        >>> provider = FileStateProvider(base_dir="~/.nexus/sessions")
        >>> await provider.save("session:123", {"data": "value"})
        >>> # Creates: ~/.nexus/sessions/session__123.json
        >>>
        >>> data = await provider.load("session:123")
        >>> print(data)
        {'data': 'value'}
    """

    def __init__(self, base_dir: str | Path = "~/.nexus/sessions"):
        """Initialize file-based state provider.

        Args:
            base_dir: Base directory for storing state files.
                     Supports ~ expansion and relative paths.
                     Created if it doesn't exist.

        Example:
            >>> # Use default directory
            >>> provider = FileStateProvider()
            >>>
            >>> # Use custom directory
            >>> provider = FileStateProvider("/var/lib/nexus/sessions")
        """
        self.base_dir = Path(base_dir).expanduser().resolve()
        self._ensure_directory_exists()
        logger.info(f"FileStateProvider initialized: base_dir={self.base_dir}")

    def _ensure_directory_exists(self) -> None:
        """Create base directory if it doesn't exist."""
        try:
            self.base_dir.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Ensured directory exists: {self.base_dir}")
        except OSError as e:
            logger.error(f"Failed to create directory {self.base_dir}: {e}")
            raise IOError(f"Cannot create state directory: {e}") from e

    def _key_to_filename(self, key: str) -> Path:
        """Convert a state key to a filesystem-safe filename.

        Args:
            key: State key (e.g., "session:abc123")

        Returns:
            Path to the JSON file

        Example:
            >>> provider._key_to_filename("session:123")
            PosixPath('/home/user/.nexus/sessions/session__123.json')
        """
        # Replace filesystem-unsafe characters
        safe_name = key.replace(":", "__").replace("/", "_")
        return self.base_dir / f"{safe_name}.json"

    def _filename_to_key(self, filepath: Path) -> str:
        """Convert a filename back to a state key.

        Args:
            filepath: Path to JSON file

        Returns:
            Original state key

        Example:
            >>> path = Path("session__123.json")
            >>> provider._filename_to_key(path)
            'session:123'
        """
        # Remove .json extension and reverse character replacements
        name = filepath.stem
        return name.replace("__", ":")

    async def save(self, key: str, data: dict[str, Any]) -> None:
        """Save state data to a JSON file.

        Args:
            key: Unique key for the state
            data: State data as a JSON-serializable dictionary

        Raises:
            IOError: If file write fails
            ValueError: If data is not JSON-serializable

        Note:
            Uses atomic write (write to temp file, then rename)
            to prevent corruption if interrupted.
        """
        filepath = self._key_to_filename(key)
        temp_filepath = filepath.with_suffix(".json.tmp")

        try:
            # Write to temporary file first (atomic write pattern)
            with open(temp_filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            # Atomic rename
            temp_filepath.rename(filepath)

            logger.debug(
                f"Saved state to file: key='{key}', "
                f"path={filepath}, size={filepath.stat().st_size} bytes"
            )

        except (TypeError, ValueError) as e:
            logger.error(f"Data not JSON-serializable for key '{key}': {e}")
            # Clean up temp file if it exists
            if temp_filepath.exists():
                temp_filepath.unlink()
            raise ValueError(f"Cannot serialize data: {e}") from e

        except OSError as e:
            logger.error(f"Failed to write state file for key '{key}': {e}")
            # Clean up temp file if it exists
            if temp_filepath.exists():
                temp_filepath.unlink()
            raise IOError(f"Cannot write state file: {e}") from e

    async def load(self, key: str) -> dict[str, Any] | None:
        """Load state data from a JSON file.

        Args:
            key: The state key to load

        Returns:
            State data dictionary if found, None if file doesn't exist

        Raises:
            IOError: If file read fails
            ValueError: If JSON is invalid or corrupted
        """
        filepath = self._key_to_filename(key)

        if not filepath.exists():
            logger.debug(f"State file not found: key='{key}', path={filepath}")
            return None

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            logger.debug(
                f"Loaded state from file: key='{key}', "
                f"path={filepath}, size={len(data)} fields"
            )
            return data

        except json.JSONDecodeError as e:
            logger.error(
                f"Corrupted JSON in state file '{filepath}': {e}"
            )
            raise ValueError(f"Corrupted state file: {e}") from e

        except OSError as e:
            logger.error(f"Failed to read state file '{filepath}': {e}")
            raise IOError(f"Cannot read state file: {e}") from e

    async def exists(self, key: str) -> bool:
        """Check if state file exists.

        Args:
            key: The state key to check

        Returns:
            True if file exists, False otherwise
        """
        filepath = self._key_to_filename(key)
        exists = filepath.exists()
        logger.debug(f"State file exists check: key='{key}', exists={exists}")
        return exists

    async def delete(self, key: str) -> None:
        """Delete state file.

        Args:
            key: The state key to delete

        Note:
            Silently succeeds if file doesn't exist (idempotent)
        """
        filepath = self._key_to_filename(key)

        if filepath.exists():
            try:
                filepath.unlink()
                logger.debug(f"Deleted state file: key='{key}', path={filepath}")
            except OSError as e:
                logger.error(f"Failed to delete state file '{filepath}': {e}")
                raise IOError(f"Cannot delete state file: {e}") from e
        else:
            logger.debug(f"Delete called on non-existent file: key='{key}' (no-op)")

    async def list_keys(self, prefix: str | None = None) -> list[str]:
        """List all state files in the directory.

        Args:
            prefix: Optional prefix filter (e.g., "session:")

        Returns:
            List of keys, optionally filtered by prefix
        """
        try:
            # Get all .json files (excluding .tmp files)
            json_files = [
                f for f in self.base_dir.glob("*.json")
                if not f.name.endswith(".tmp")
            ]

            # Convert filenames to keys
            keys = [self._filename_to_key(f) for f in json_files]

            # Apply prefix filter if specified
            if prefix is not None:
                keys = [k for k in keys if k.startswith(prefix)]

            logger.debug(
                f"Listed state files: prefix='{prefix}', count={len(keys)}"
            )
            return sorted(keys)

        except OSError as e:
            logger.error(f"Failed to list state files in {self.base_dir}: {e}")
            raise IOError(f"Cannot list state files: {e}") from e

    def get_file_path(self, key: str) -> Path:
        """Get the file path for a given key.

        Utility method for debugging and testing.

        Args:
            key: State key

        Returns:
            Path to the JSON file
        """
        return self._key_to_filename(key)
