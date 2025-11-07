"""Interactive Typer-based CLI for the MCP client."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Awaitable, Callable, Dict, Optional

import typer
from mcp import types

from nxs.logger import get_logger
from nxs.mcp_client.client import MCPAuthClient

logger = get_logger("mcp_client.cli")
app = typer.Typer()

CommandHandler = Callable[[MCPAuthClient, str], Awaitable[None]]


async def _handle_list(client: MCPAuthClient, _: str) -> None:
    tools = await client.list_tools()
    if not tools:
        typer.echo("No tools available.")
        return
    typer.echo("Available tools:")
    for tool in tools:
        typer.echo(f"  - {tool.name}")


async def _handle_call(client: MCPAuthClient, payload: str) -> None:
    parts = payload.split(maxsplit=1)
    tool_name = parts[0] if parts else ""
    if not tool_name:
        typer.echo("❌ Please specify a tool name.")
        return

    arguments: Optional[dict[str, object]] = None
    if len(parts) > 1:
        try:
            arguments = json.loads(parts[1])
        except json.JSONDecodeError:
            typer.echo("❌ Invalid JSON arguments.")
            return

    result = await client.call_tool(tool_name, arguments)
    if result is None:
        typer.echo("Tool execution failed or returned no result.")
        return

    typer.echo("Tool result:")
    _render_tool_result(result)


async def _handle_prompts(client: MCPAuthClient, _: str) -> None:
    prompts = await client.list_prompts()
    if not prompts:
        typer.echo("No prompts available.")
        return
    typer.echo("Available prompts:")
    for prompt in prompts:
        typer.echo(f"  - {prompt.name}")


async def _handle_prompt(client: MCPAuthClient, payload: str) -> None:
    parts = payload.split(maxsplit=1)
    prompt_name = parts[0] if parts else ""
    if not prompt_name:
        typer.echo("❌ Please specify a prompt name.")
        return

    args: dict[str, object] = {}
    if len(parts) > 1:
        try:
            args = json.loads(parts[1])
        except json.JSONDecodeError:
            typer.echo("❌ Invalid JSON arguments.")
            return

    messages = await client.get_prompt(prompt_name, args)
    if not messages:
        typer.echo("Prompt returned no messages.")
        return

    typer.echo("Prompt messages:")
    for message in messages:
        typer.echo(f"[{message.role}] {message.content}")


async def _handle_resources(client: MCPAuthClient, _: str) -> None:
    resources = await client.list_resources()
    if not resources:
        typer.echo("No resources available.")
        return
    typer.echo("Available resources:")
    for resource in resources:
        typer.echo(f"  - {resource.uri}")


async def _handle_read(client: MCPAuthClient, payload: str) -> None:
    uri = payload.strip()
    if not uri:
        typer.echo("❌ Please specify a resource URI.")
        return

    data = await client.read_resource(uri)
    if data is None:
        typer.echo("Failed to read resource or resource empty.")
        return

    typer.echo(json.dumps(data, indent=2) if isinstance(data, (dict, list)) else str(data))


COMMANDS: Dict[str, CommandHandler] = {
    "list": _handle_list,
    "call": _handle_call,
    "prompts": _handle_prompts,
    "prompt": _handle_prompt,
    "resources": _handle_resources,
    "read": _handle_read,
}


def _sanitize_command(text: str) -> str:
    """Normalize command text by removing carriage returns and trimming whitespace."""
    return text.replace("\r", "").strip()


def _read_command(prompt: str) -> str:
    """Read a command from stdin, ensuring carriage returns are stripped."""
    typer.echo(prompt, nl=False)
    sys.stdout.flush()

    line = sys.stdin.readline()
    if line == "":
        raise EOFError
    return _sanitize_command(line)


async def _dispatch_command(client: MCPAuthClient, command: str) -> bool:
    command = _sanitize_command(command)

    if not command:
        return True

    if command == "quit":
        return False

    parts = command.split(maxsplit=1)
    name = parts[0]
    handler = COMMANDS.get(name)
    if handler is None:
        typer.echo("❌ Unknown command. Try 'list', 'call <tool>', or 'quit'.")
        return True

    payload = _sanitize_command(parts[1]) if len(parts) > 1 else ""
    await handler(client, payload)
    return True


async def _interactive_loop(client: MCPAuthClient) -> None:
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
            command = _read_command("mcp> ")
        except (KeyboardInterrupt, EOFError):
            typer.echo("\n👋 Goodbye!")
            break

        should_continue = await _dispatch_command(client, command)
        if not should_continue:
            break


def _render_tool_result(result: types.CallToolResult) -> None:
    if not getattr(result, "content", None):
        typer.echo(result)
        return

    for content in result.content:
        if content.type == "text":
            typer.echo(content.text)
        else:
            typer.echo(repr(content))


def run_cli(
    server_url: str,
    transport_type: str,
    use_auth: bool,
) -> None:
    resolved_url = f"{server_url}/mcp" if transport_type == "streamable_http" else server_url

    async def runner() -> None:
        client = MCPAuthClient(resolved_url, transport_type)
        try:
            await client.connect(use_auth=use_auth)
            await _interactive_loop(client)
        except Exception as exc:
            typer.echo(f"❌ Error: {exc}")
            logger.exception("Fatal error in CLI")
        finally:
            await client.disconnect()

    asyncio.run(runner())


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
    run_cli(server_url, transport_type, use_auth)


if __name__ == "__main__":
    app()

