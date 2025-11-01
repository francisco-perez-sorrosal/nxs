import asyncio
import os
from dotenv import load_dotenv

import typer

# Import logger setup first to ensure logging is configured
from nxs.logger import get_logger, setup_logger
from nxs.core.claude import Claude
from nxs.core.command_control import CommandControlAgent
from nxs.core.artifact_manager import ArtifactManager
from nxs.tui.app import NexusApp

load_dotenv()

# Anthropic Config
claude_model = os.getenv("CLAUDE_MODEL", "")
anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "")


assert claude_model, "Error: CLAUDE_MODEL cannot be empty. Update .env"
assert anthropic_api_key, "Error: ANTHROPIC_API_KEY cannot be empty. Update .env"

cli = typer.Typer(
    name="nxs",
    help="Nexus command control with Claude integration and MCP-based CLI",
    epilog="""
    Examples:
    $ nxs --server-url https://fps-cv.onrender.com/mcp --transport-type streamable_http --use-auth
    """,
    add_completion=False,
)


@cli.command()
async def main(
    debug: bool = typer.Option(os.getenv("DEBUG", "false").lower() == "true", "--debug", help="Enable debug mode"),
):

    # Ensure logging is set up
    setup_logger(log_level="DEBUG" if debug else "INFO")
    logger = get_logger("main")

    claude_service = Claude(model=claude_model)

    # Initialize ArtifactManager to load MCP servers and artifacts
    artifact_manager = ArtifactManager()
    try:
        await artifact_manager.initialize()

        # Create CommandControlAgent with ArtifactManager
        command_control = CommandControlAgent(
            artifact_manager=artifact_manager,
            claude_service=claude_service,
        )

        # Launch Textual TUI with ArtifactManager
        app = NexusApp(
            agent_loop=command_control,
            artifact_manager=artifact_manager,
        )
        await app.run_async()
    finally:
        # Clean up ArtifactManager connections
        await artifact_manager.cleanup()


def run():
    """Entry point for the Nexus application."""
    asyncio.run(main())


if __name__ == "__main__":
    run()
