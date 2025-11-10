import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv

import typer

# Import logger setup first to ensure logging is configured
from nxs.logger import get_logger, setup_logger
from nxs.application.claude import Claude
from nxs.application.command_control import CommandControlAgent
from nxs.application.artifact_manager import ArtifactManager
from nxs.application.session_manager_new import SessionManager
from nxs.presentation.tui import NexusApp

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
    """Main application entry point with SessionManager integration."""
    
    # Ensure logging is set up
    setup_logger(log_level="DEBUG" if debug else "INFO")
    logger = get_logger("main")

    logger.info("🚀 Starting Nexus with SessionManager integration")

    # Create core services
    claude_service = Claude(model=claude_model)
    artifact_manager = ArtifactManager()

    # Create agent factory that produces CommandControlAgent instances
    # This preserves command parsing (/cmd) and resource extraction (@resource)
    def create_command_control_agent(conversation):
        """Factory to create CommandControlAgent with session-managed conversation.
        
        Args:
            conversation: The Conversation instance managed by SessionManager
            
        Returns:
            CommandControlAgent instance that uses the provided conversation
        """
        # Create CommandControlAgent with artifact_manager
        # It will use backward compatibility mode and create its own conversation,
        # but we'll replace it with the session-managed one
        agent = CommandControlAgent(
            artifact_manager=artifact_manager,
            claude_service=claude_service,
        )
        
        # Replace the internally-created conversation with session-managed one
        # This ensures session persistence works while keeping command/resource features
        agent.conversation = conversation
        
        logger.debug("Created CommandControlAgent with session-managed conversation")
        return agent

    # Create SessionManager with custom agent factory
    session_manager = SessionManager(
        llm=claude_service,
        storage_dir=Path.home() / ".nxs" / "sessions",
        system_message="You are a helpful AI assistant.",
        enable_caching=True,
        agent_factory=create_command_control_agent,
    )

    logger.info("SessionManager initialized with CommandControlAgent factory")

    # Get or restore the default session
    # This will either restore from ~/.nxs/sessions/session.json or create new
    session = await session_manager.get_or_create_default_session()
    
    logger.info(
        f"Session ready: {session.session_id} "
        f"({session.get_message_count()} messages in history)"
    )

    # Create auto-save callback for session persistence
    def auto_save_session():
        """Auto-save session after each query completes."""
        try:
            session_manager.save_active_session()
            logger.debug("Session auto-saved after query completion")
        except Exception as e:
            logger.error(f"Failed to auto-save session: {e}", exc_info=True)

    # Launch Textual TUI with session's agent_loop and auto-save callback
    # The agent_loop is CommandControlAgent with session-managed conversation
    app = NexusApp(
        agent_loop=session.agent_loop,
        artifact_manager=artifact_manager,
        on_query_complete=auto_save_session,
    )
    
    try:
        await app.run_async()
    finally:
        # Save session before exit
        logger.info("Saving session before exit...")
        session_manager.save_active_session()
        logger.info("Session saved successfully")
        
        # Clean up ArtifactManager connections
        await artifact_manager.cleanup()


def run():
    """Entry point for the Nexus application."""
    asyncio.run(main())


if __name__ == "__main__":
    run()
