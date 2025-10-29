"""
Entry point for running the MCP client as a module.

This allows the package to be executed with: python -m nxs.mcp_client
"""

from nxs.mcp_client.client import app

if __name__ == "__main__":
    app()
