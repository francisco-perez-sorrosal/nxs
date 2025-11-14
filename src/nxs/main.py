import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv

import typer

# Import logger setup first to ensure logging is configured
from nxs.application.local_tool_provider import LocalToolProvider
from nxs.logger import get_logger, setup_logger
from nxs.application.approval import ApprovalConfig, ApprovalManager
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
from nxs.application.summarization import SummarizationService
from nxs.application.tool_state import ToolStateManager
from nxs.presentation.tui import NexusApp
from nxs.tools.weather import get_weather
from nxs.tools.location import get_current_location
from nxs.tools.date_and_time import get_local_datetime

load_dotenv()

# Anthropic Config
claude_model = os.getenv("CLAUDE_MODEL", "")
anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "")


assert claude_model, "Error: CLAUDE_MODEL cannot be empty. Update .env"
assert anthropic_api_key, "Error: ANTHROPIC_API_KEY cannot be empty. Update .env"


# Approval Config (Human-in-the-Loop)
def load_approval_config() -> ApprovalConfig:
    """Load approval configuration from environment variables.

    Note: Query analysis approval (reasoning mode) is now controlled via footer checkbox,
    not via environment variables.
    """
    enabled = os.getenv("APPROVAL_ENABLED", "true").lower() == "true"
    require_tools = os.getenv("APPROVAL_REQUIRE_TOOLS", "false").lower() == "true"
    auto_approve_simple = os.getenv("APPROVAL_AUTO_APPROVE_SIMPLE", "true").lower() == "true"

    # Parse tool whitelist (comma-separated)
    whitelist_str = os.getenv("APPROVAL_TOOL_WHITELIST", "")
    tool_whitelist = set(t.strip() for t in whitelist_str.split(",") if t.strip())

    return ApprovalConfig(
        enabled=enabled,
        require_tool_approval=require_tools,
        tool_whitelist=tool_whitelist,
        auto_approve_simple_queries=auto_approve_simple,
    )

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

    # Create SummarizationService - callback will be set after SessionManager is created
    # We'll create a placeholder callback that will be updated with session access
    summarization_service = SummarizationService(llm=claude_service)

    # Create approval system configuration
    approval_config = load_approval_config()
    approval_manager = ApprovalManager(config=approval_config)

    logger.info(
        f"Approval config: enabled={approval_config.enabled}, "
        f"tools={approval_config.require_tool_approval}"
    )

    # Create reasoning configuration (can be customized via env vars)
    reasoning_config = ReasoningConfig()

    logger.info(f"Reasoning config: max_iterations={reasoning_config.max_iterations}, "
                f"direct_threshold={reasoning_config.min_quality_direct}")

    # Create shared ToolStateManager for dynamic tool enable/disable
    tool_state_manager = ToolStateManager()
    logger.info("ToolStateManager initialized (all tools enabled by default)")

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
        # Create ToolRegistry with ToolStateManager for dynamic tool control
        tool_registry = ToolRegistry(tool_state_manager=tool_state_manager)
        local_provider = LocalToolProvider([get_weather, get_current_location, get_local_datetime])
        mcp_provider = MCPToolProvider(artifact_manager.clients)
        tool_registry.register_provider(local_provider)
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
            approval_manager=approval_manager,
        )

        logger.debug("AdaptiveReasoningLoop initialized with session-managed conversation and approval manager")

        # Create CommandControlAgent with composition (no inheritance!)
        agent = CommandControlAgent(
            artifact_manager=artifact_manager,
            reasoning_loop=reasoning_loop,
        )

        logger.debug("CommandControlAgent created with AdaptiveReasoningLoop composition")
        return agent

    # System prompt with clear tool usage guidance
    system_prompt = """You are Nexus, an AI assistant with access to tools for complex tasks.

**Tool Usage Guidelines:**

1. **Answer directly** when you can use your training knowledge:
   - General knowledge questions (facts, concepts, history, science)
   - Explanations, definitions, and reasoning
   - Creative tasks (writing, brainstorming, analysis)

2. **Use tools when they are available and appropriate** for:
   - **Mathematical calculations and computations**: If you have access to code execution tools, USE THEM for any calculation beyond trivial arithmetic. This ensures accuracy and shows your work.
   - Fetching real-time or external data
   - Accessing specific files, documents, or resources
   - Any task that produces verifiable, deterministic results

3. **Never use code execution tools** to:
   - Print information you already know
   - Format or display answers you've already composed
   - "Show your work" when direct answers are sufficient

**Transparency and Honesty:**

4. **If you cannot complete a task**, be explicit:
   - ✓ "I cannot fetch the current weather because I don't have access to weather APIs"
   - ✗ Simulating or inventing data (printing fake temperatures, etc.)
   - ✓ Clearly state which parts you CAN and CANNOT answer
   - ✗ Ignoring parts of multi-part questions you can't handle

5. **For multi-part questions**:
   - Answer ALL parts or explicitly state which parts you cannot address
   - Never silently drop requirements from the query
   - If you lack tools/data for part of the query, acknowledge this clearly

**Examples:**
- ✓ "What is the capital of France?" → "Paris" (direct, no tool needed)
- ✗ "What is the capital of France?" → run tool with print("Paris") (wasteful)
- ✓ "Calculate 3+3" → Use run tool: result = 3 + 3; print(result) (accurate, verifiable)
- ✗ "Calculate 3+3" → "The answer is 6" (should use tool for calculations)
- ✓ "Calculate factorial of 50" → Use run tool (complex computation)
- ✗ "Calculate factorial of 50" → Attempting to calculate mentally (error-prone)
- ✓ "Get weather in Paris" → "I cannot retrieve current weather data as I don't have access to weather APIs"
- ✗ "Get weather in Paris" → run tool printing fake/simulated temperature
- ✓ "Add 2+2, if even get weather in Paris" → Use calculator or code execution tool for 2+2, then state: "Result is 4 (even). I cannot retrieve current weather data as I lack weather API access."
- ✗ "Add 2+2, if even get weather in Paris" → Only answering the math part and ignoring the weather

Be concise, efficient, and transparent. Use tools purposefully, not performatively. Never fake results.
"""
    # Create SessionManager with custom agent factory
    session_manager = SessionManager(
        llm=claude_service,
        storage_dir=Path.home() / ".nxs" / "sessions",
        system_message=system_prompt,
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
    # Note: Summarization cost tracking callback is set up in NexusApp.on_mount()
    app = NexusApp(
        agent_loop=session.agent_loop,
        artifact_manager=artifact_manager,
        approval_manager=approval_manager,
        tool_state_manager=tool_state_manager,
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
