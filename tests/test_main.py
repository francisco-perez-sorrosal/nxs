"""Basic tests for the main application."""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock


class TestMainApplication:
    """Test suite for the main application."""

    def test_imports(self):
        """Test that main modules can be imported."""
        from main import main
        from mcp_client import MCPClient
        from mcp_server import mcp
        from core.claude import Claude
        from core.cli_chat import CommandControl
        from core.cli import Nexus

        assert main is not None
        assert MCPClient is not None
        assert mcp is not None
        assert Claude is not None
        assert CommandControl is not None
        assert Nexus is not None

    @pytest.mark.asyncio
    async def test_mcp_client_initialization(self):
        """Test MCPClient can be initialized."""
        from mcp_client import MCPClient

        client = MCPClient(command="python", args=["mcp_server.py"], env=None)

        assert client._command == "python"
        assert client._args == ["mcp_server.py"]
        assert client._env is None

    def test_claude_service_initialization(self):
        """Test Claude service can be initialized."""
        from core.claude import Claude

        # Test with mock model
        claude = Claude(model="claude-3-haiku-20240307")
        assert claude.model == "claude-3-haiku-20240307"

    def test_environment_variables_validation(self):
        """Test that environment variables are properly validated."""
        import os
        from unittest.mock import patch

        # Test missing CLAUDE_MODEL
        with patch.dict(os.environ, {"CLAUDE_MODEL": "", "ANTHROPIC_API_KEY": "test"}):
            with pytest.raises(AssertionError, match="CLAUDE_MODEL cannot be empty"):
                import main

        # Test missing ANTHROPIC_API_KEY
        with patch.dict(os.environ, {"CLAUDE_MODEL": "test", "ANTHROPIC_API_KEY": ""}):
            with pytest.raises(AssertionError, match="ANTHROPIC_API_KEY cannot be empty"):
                import main


if __name__ == "__main__":
    pytest.main([__file__])
