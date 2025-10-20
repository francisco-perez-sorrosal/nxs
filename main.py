import asyncio
import sys
import os
from dotenv import load_dotenv
from contextlib import AsyncExitStack

# Import logger setup first to ensure logging is configured
from core.logger import get_logger, setup_logger
from mcp_client import MCPClient
from core.claude import Claude
from core.command_control import CommandControlAgent
from tui.app import NexusApp

# Ensure logging is set up
logger = get_logger("main")

load_dotenv()

# Anthropic Config
claude_model = os.getenv("CLAUDE_MODEL", "")
anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "")


assert claude_model, "Error: CLAUDE_MODEL cannot be empty. Update .env"
assert anthropic_api_key, "Error: ANTHROPIC_API_KEY cannot be empty. Update .env"


async def main():
    claude_service = Claude(model=claude_model)

    server_scripts = sys.argv[1:]
    clients = {}

    command, args = (
        ("uv", ["run", "mcp_server.py"]) if os.getenv("USE_UV", "0") == "1" else ("python", ["mcp_server.py"])
    )

    async with AsyncExitStack() as stack:
        doc_client = await stack.enter_async_context(MCPClient(command=command, args=args))
        clients["doc_client"] = doc_client

        for i, server_script in enumerate(server_scripts):
            client_id = f"client_{i}_{server_script}"
            client = await stack.enter_async_context(MCPClient(command="uv", args=["run", server_script]))
            clients[client_id] = client

        command_control = CommandControlAgent(
            doc_client=doc_client,
            clients=clients,
            claude_service=claude_service,
        )

        # Get resources and commands for auto-completion
        resources = await command_control.list_docs_ids()
        prompts = await command_control.list_prompts()
        commands = [p.name for p in prompts]
        
        # Debug: Log resources and commands
        logger.info(f"Loaded {len(resources)} resources: {resources}")
        logger.info(f"Loaded {len(commands)} commands: {commands}")

        # Launch Textual TUI
        app = NexusApp(
            agent_loop=command_control,
            resources=resources,
            commands=commands
        )
        await app.run_async()


if __name__ == "__main__":
    asyncio.run(main())
