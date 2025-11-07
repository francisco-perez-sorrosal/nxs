"""Allow running the MCP client as a module via ``python -m nxs.mcp_client``."""

from .cli import app

if __name__ == "__main__":
    app()
