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
from nxs.application.session_manager import SessionManager
from nxs.application.conversation import Conversation
from nxs.application.tool_registry import ToolRegistry
from nxs.application.mcp_tool_provider import MCPToolProvider
from nxs.application.reasoning_loop import AdaptiveReasoningLoop
from nxs.application.reasoning.config import ReasoningConfig
from nxs.application.reasoning.analyzer import QueryComplexityAnalyzer
from nxs.application.reasoning.planner import Planner
from nxs.application.reasoning.evaluator import Evaluator
from nxs.application.reasoning.synthesizer import Synthesizer
from nxs.presentation.tui import NexusApp
from nxs.application.summarization import SummarizationService

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
    summarization_service = SummarizationService(llm=claude_service)

    # Create reasoning configuration (can be customized via env vars)
    reasoning_config = ReasoningConfig()
    
    logger.info(f"Reasoning config: max_iterations={reasoning_config.max_iterations}, "
                f"direct_threshold={reasoning_config.min_quality_direct}")

    # Create agent factory that produces CommandControlAgent instances
    # This uses composition: CommandControlAgent -> AdaptiveReasoningLoop -> AgentLoop
    def create_command_control_agent(conversation):
        """Factory to create CommandControlAgent with session-managed conversation.
        
        Uses composition architecture:
        - CommandControlAgent: High-level command/resource processing
        - AdaptiveReasoningLoop: Adaptive reasoning with quality guarantees
        - AgentLoop: Core conversation loop with tools
        
        Args:
            conversation: The Conversation instance managed by SessionManager
            
        Returns:
            CommandControlAgent instance that uses AdaptiveReasoningLoop
        """
        # Create ToolRegistry and register MCP tools
        tool_registry = ToolRegistry()
        mcp_provider = MCPToolProvider(artifact_manager.clients)
        tool_registry.register_provider(mcp_provider)
        
        logger.debug(f"ToolRegistry initialized with {len(artifact_manager.clients)} MCP clients")
        
        # Create reasoning components
        analyzer = QueryComplexityAnalyzer(claude_service, reasoning_config)
        planner = Planner(claude_service, reasoning_config)
        evaluator = Evaluator(claude_service, reasoning_config)
        synthesizer = Synthesizer(claude_service, reasoning_config)
        
        logger.debug("Reasoning components initialized (Analyzer, Planner, Evaluator, Synthesizer)")
        
        # Create AdaptiveReasoningLoop with reasoning components
        reasoning_loop = AdaptiveReasoningLoop(
            llm=claude_service,
            conversation=conversation,  # Session-managed conversation
            tool_registry=tool_registry,
            analyzer=analyzer,
            planner=planner,
            evaluator=evaluator,
            synthesizer=synthesizer,
            config=reasoning_config,
        )
        
        logger.debug("AdaptiveReasoningLoop initialized with session-managed conversation")
        
        # Create CommandControlAgent with composition (no inheritance!)
        agent = CommandControlAgent(
            artifact_manager=artifact_manager,
            reasoning_loop=reasoning_loop,
        )
        
        logger.debug("CommandControlAgent created with AdaptiveReasoningLoop composition")
        return agent

    # Create SessionManager with custom agent factory
    session_manager = SessionManager(
        llm=claude_service,
        storage_dir=Path.home() / ".nxs" / "sessions",
        system_message="You are a helpful AI assistant.",
        enable_caching=True,
        agent_factory=create_command_control_agent,
        summarizer=summarization_service,
    )

    logger.info("SessionManager initialized with CommandControlAgent factory")

    # Get or restore the default session
    # This will either restore from ~/.nxs/sessions/session.json or create new
    session = await session_manager.get_or_create_default_session()
    
    logger.info(
        f"Session ready: {session.session_id} "
        f"({session.get_message_count()} messages in history)"
    )

    # Launch Textual TUI with session's agent_loop
    # The agent_loop is CommandControlAgent with session-managed conversation
    # CommandControlAgent uses AdaptiveReasoningLoop via composition
    # Session saves on exit (not after every query - too frequent)
    app = NexusApp(
        agent_loop=session.agent_loop,
        artifact_manager=artifact_manager,
        session_name=session.session_id,
        session=session,
        session_manager=session_manager,
    )
    
    logger.info(f"NexusApp initialized with session '{session.session_id}' (using AdaptiveReasoningLoop)")
    
    try:
        await app.run_async()
    finally:
        # Ensure conversation summary is synced before saving session state
        await app.ensure_summary_synced()

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
