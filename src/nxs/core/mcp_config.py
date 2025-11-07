"""MCP server configuration parser.

Parses JSON configuration files containing MCP server definitions.
"""

import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, ValidationError

from nxs.logger import get_logger

logger = get_logger("mcp_config")


class MCPServerConfig(BaseModel):
    """Configuration for a single MCP server."""

    command: str = Field(..., description="Command to execute the MCP server")
    args: list[str] = Field(default_factory=list, description="Arguments for the command")

    def is_remote(self) -> bool:
        """
        Check if this is a remote MCP server.

        A server is considered remote if the first argument is "mcp-remote".

        Returns:
            True if this is a remote server, False otherwise
        """
        return len(self.args) > 0 and self.args[0] == "mcp-remote"

    def remote_url(self) -> Optional[str]:
        """
        Get the remote URL for this server if it's a remote server.

        Returns:
            The URL (second argument) if this is a remote server, None otherwise
        """
        if self.is_remote() and len(self.args) > 1:
            return self.args[1]
        return None

    class Config:
        """Pydantic configuration."""

        frozen = True


class MCPServersConfig(BaseModel):
    """Configuration containing multiple MCP servers."""

    mcpServers: dict[str, MCPServerConfig] = Field(
        default_factory=dict, description="Dictionary of MCP server configurations"
    )

    class Config:
        """Pydantic configuration."""

        frozen = True


def load_mcp_config(config_path: Optional[str | Path] = None) -> MCPServersConfig:
    """
    Load MCP server configuration from JSON file.

    Args:
        config_path: Path to the JSON configuration file. If None, looks for
            'nxs_mcp_config.json' in the config directory relative to the
            package root.

    Returns:
        MCPServersConfig: Parsed configuration object

    Raises:
        FileNotFoundError: If the configuration file doesn't exist
        json.JSONDecodeError: If the JSON file is invalid
        ValidationError: If the configuration structure is invalid
    """
    if config_path is None:
        # Default to config/nxs_mcp_config.json relative to package root
        # mcp_config.py is in src/nxs/core/, so parent.parent is src/nxs/
        package_root = Path(__file__).parent.parent
        config_path = package_root / "config" / "nxs_mcp_config.json"
    else:
        config_path = Path(config_path)

    if not config_path.exists():
        error_msg = f"MCP configuration file not found: {config_path}"
        logger.error(error_msg)
        raise FileNotFoundError(error_msg)

    logger.info(f"Loading MCP configuration from: {config_path}")

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        error_msg = f"Invalid JSON in configuration file {config_path}: {e}"
        logger.error(error_msg)
        raise

    try:
        config = MCPServersConfig(**data)
        logger.info(f"Loaded {len(config.mcpServers)} MCP server(s)")
        for server_name in config.mcpServers:
            logger.debug(f"  - {server_name}: {config.mcpServers[server_name].command}")
        return config
    except ValidationError as e:
        error_msg = f"Invalid configuration structure in {config_path}: {e}"
        logger.error(error_msg)
        raise


def get_server_config(
    server_name: str, config: Optional[MCPServersConfig] = None
) -> Optional[MCPServerConfig]:
    """
    Get configuration for a specific MCP server.

    Args:
        server_name: Name of the MCP server
        config: Configuration object. If None, loads from default location.

    Returns:
        MCPServerConfig if found, None otherwise
    """
    if config is None:
        config = load_mcp_config()

    return config.mcpServers.get(server_name)


def get_all_server_names(config: Optional[MCPServersConfig] = None) -> list[str]:
    """
    Get names of all configured MCP servers.

    Args:
        config: Configuration object. If None, loads from default location.

    Returns:
        List of server names
    """
    if config is None:
        config = load_mcp_config()

    return list(config.mcpServers.keys())

