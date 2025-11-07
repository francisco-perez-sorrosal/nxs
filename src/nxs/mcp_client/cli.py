"""Command-line entry point for the MCP client."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Optional

import typer

from mcp import types

from nxs.logger import get_logger

from .client import MCPAuthClient

app = typer.Typer()
logger = get_logger("mcp_client.cli")


async def _interactive_loop(client: MCPAuthClient) -> None:
    """Simple interactive shell for exploring MCP server capabilities."""
    typer.echo("")
    typer.echo("🎯 Interactive MCP Client")
    typer.echo("Commands:")
    typer.echo("  list                    List available tools")
    typer.echo("  call <tool> [json]      Call a tool with optional JSON args")
    typer.echo("  prompts                 List prompts")
    typer.echo("  prompt <name> <json>    Fetch a prompt with arguments")
    typer.echo("  resources               List resources")
    typer.echo("  read <uri>              Read a resource by URI")
    typer.echo("  quit                    Exit the client")
    typer.echo("")

    while True:
        try:
            command = input("mcp> ").strip()
        except (KeyboardInterrupt, EOFError):
            typer.echo("\n👋 Goodbye!")
            break

        if not command:
            continue

        if command == "quit":
            break

        if command == "list":
            tools = await client.list_tools()
            if not tools:
                typer.echo("No tools available.")
            else:
                typer.echo("Available tools:")
                for tool in tools:
                    typer.echo(f"  - {tool.name}")
            continue

        if command.startswith("call "):
            parts = command.split(maxsplit=2)
            tool_name = parts[1] if len(parts) > 1 else ""
            if not tool_name:
                typer.echo("❌ Please specify a tool name.")
                continue

            arguments: Optional[dict[str, object]] = None
            if len(parts) > 2:
                try:
                    arguments = json.loads(parts[2])
                except json.JSONDecodeError:
                    typer.echo("❌ Invalid JSON arguments.")
                    continue

            result = await client.call_tool(tool_name, arguments)
            if result is None:
                typer.echo("Tool execution failed or returned no result.")
                continue

            typer.echo("Tool result:")
            _render_tool_result(result)
            continue

        if command == "prompts":
            prompts = await client.list_prompts()
            if not prompts:
                typer.echo("No prompts available.")
            else:
                typer.echo("Available prompts:")
                for prompt in prompts:
                    typer.echo(f"  - {prompt.name}")
            continue

        if command.startswith("prompt "):
            parts = command.split(maxsplit=2)
            prompt_name = parts[1] if len(parts) > 1 else ""
            if not prompt_name:
                typer.echo("❌ Please specify a prompt name.")
                continue

            args: dict[str, object] = {}
            if len(parts) > 2:
                try:
                    args = json.loads(parts[2])
                except json.JSONDecodeError:
                    typer.echo("❌ Invalid JSON arguments.")
                    continue

            messages = await client.get_prompt(prompt_name, args)
            if not messages:
                typer.echo("Prompt returned no messages.")
            else:
                typer.echo("Prompt messages:")
                for message in messages:
                    typer.echo(f"[{message.role}] {message.content}")
            continue

        if command == "resources":
            resources = await client.list_resources()
            if not resources:
                typer.echo("No resources available.")
            else:
                typer.echo("Available resources:")
                for resource in resources:
                    typer.echo(f"  - {resource.uri}")
            continue

        if command.startswith("read "):
            parts = command.split(maxsplit=1)
            uri = parts[1] if len(parts) > 1 else ""
            if not uri:
                typer.echo("❌ Please specify a resource URI.")
                continue

            data = await client.read_resource(uri)
            if data is None:
                typer.echo("Failed to read resource or resource empty.")
            else:
                typer.echo(json.dumps(data, indent=2) if isinstance(data, (dict, list)) else str(data))
            continue

        typer.echo("❌ Unknown command. Try 'list', 'call <tool>', or 'quit'.")


def _render_tool_result(result: types.CallToolResult) -> None:
    """Pretty-print tool results for the interactive CLI."""
    if not getattr(result, "content", None):
        typer.echo(result)
        return

    for content in result.content:
        if content.type == "text":
            typer.echo(content.text)
        else:
            typer.echo(repr(content))


@app.command()
def main(
    server_url: str = typer.Option(
        os.getenv("MCP_SERVER_URL", "http://localhost:8000"),
        "--server-url",
        help="Base URL of the MCP server",
    ),
    transport_type: str = typer.Option(
        os.getenv("MCP_TRANSPORT_TYPE", "streamable_http"),
        "--transport-type",
        help="Transport type to use (only streamable_http supported)",
    ),
    use_auth: bool = typer.Option(
        os.getenv("MCP_USE_AUTH", "false").lower() == "true",
        "--use-auth",
        help="Enable OAuth authentication",
    ),
) -> None:
    """Connect to an MCP server and launch the interactive CLI."""
    resolved_url = f"{server_url}/mcp" if transport_type == "streamable_http" else server_url

    async def run() -> None:
        client = MCPAuthClient(resolved_url, transport_type)

        try:
            await client.connect(use_auth=use_auth)
            await _interactive_loop(client)
        except Exception as exc:
            typer.echo(f"❌ Error: {exc}")
            logger.error("Fatal error in CLI: %s", exc)
        finally:
            await client.disconnect()

    asyncio.run(run())


if __name__ == "__main__":
    app()

