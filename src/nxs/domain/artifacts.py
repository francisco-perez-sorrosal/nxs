"""Domain models for artifacts (tools, resources, prompts).

These Pydantic models ensure consistent representation of artifacts
from different sources (MCP servers, local tools, etc.).
"""

from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class ArtifactSource(str, Enum):
    """Source of an artifact."""
    MCP = "mcp"
    LOCAL = "local"


class Tool(BaseModel):
    """Represents a tool that can be executed by the agent.

    Tools can come from MCP servers or local Python functions.
    """
    name: str = Field(..., description="Unique name of the tool")
    description: str | None = Field(None, description="Description of what the tool does")
    source: ArtifactSource = Field(..., description="Source of the tool (MCP or local)")
    source_id: str = Field(..., description="ID of the source (server name or 'local')")
    enabled: bool = Field(default=True, description="Whether the tool is enabled")
    input_schema: dict[str, Any] | None = Field(None, description="JSON Schema for tool inputs")

    def to_display_dict(self) -> dict[str, str | None | bool]:
        """Convert to dictionary for display in UI.

        Returns:
            Dictionary with name, description, and enabled fields
        """
        return {
            "name": self.name,
            "description": self.description,
            "enabled": self.enabled,
        }


class Resource(BaseModel):
    """Represents a resource (document, file, etc.) from MCP servers.

    Resources are referenced with @ in chat and provide context to the agent.
    """
    uri: str = Field(..., description="Unique URI of the resource")
    name: str = Field(..., description="Display name of the resource")
    description: str | None = Field(None, description="Description of the resource")
    mime_type: str | None = Field(None, description="MIME type of the resource")
    source_id: str = Field(..., description="ID of the MCP server providing this resource")

    def to_display_dict(self) -> dict[str, str | None]:
        """Convert to dictionary for display in UI.

        Returns:
            Dictionary with name and description fields
        """
        return {
            "name": self.name,
            "description": self.description,
        }


class Prompt(BaseModel):
    """Represents a prompt/command from MCP servers.

    Prompts are referenced with / in chat and provide pre-defined workflows.
    """
    name: str = Field(..., description="Unique name of the prompt")
    description: str | None = Field(None, description="Description of what the prompt does")
    source_id: str = Field(..., description="ID of the MCP server providing this prompt")
    arguments: list[dict[str, Any]] | None = Field(None, description="Argument schema for the prompt")

    def to_display_dict(self) -> dict[str, str | None]:
        """Convert to dictionary for display in UI.

        Returns:
            Dictionary with name and description fields
        """
        return {
            "name": self.name,
            "description": self.description,
        }


class ArtifactCollection(BaseModel):
    """Collection of all artifacts from a single source (MCP server or local)."""
    source_id: str = Field(..., description="ID of the source (server name or 'local')")
    source: ArtifactSource = Field(..., description="Type of source")
    tools: list[Tool] = Field(default_factory=list, description="Tools from this source")
    resources: list[Resource] = Field(default_factory=list, description="Resources from this source")
    prompts: list[Prompt] = Field(default_factory=list, description="Prompts from this source")

    def to_display_dict(self) -> dict[str, list[dict[str, str | None | bool]]]:
        """Convert to dictionary for display in UI.

        Returns:
            Dictionary with tools, resources, and prompts lists
        """
        return {
            "tools": [tool.to_display_dict() for tool in self.tools],
            "resources": [resource.to_display_dict() for resource in self.resources],
            "prompts": [prompt.to_display_dict() for prompt in self.prompts],
        }
