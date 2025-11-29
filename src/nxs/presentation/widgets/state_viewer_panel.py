"""State Viewer Panel - UI for visualizing accumulated session knowledge.

This widget displays the accumulated semantic knowledge from SessionState:
- User Profile (name, occupation, expertise, etc.)
- Knowledge Base (facts learned during session)
- Interaction Context (current topic, intent)
- Session Statistics (message count, cost, etc.)

Design: Clean, scannable, with visual hierarchy. Shows the "memory" of the session.
"""

from typing import Optional, TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import Container, Vertical, ScrollableContainer
from textual.widgets import Static, Label
from textual.widget import Widget
from textual.reactive import reactive
from rich.text import Text
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown

from nxs.logger import get_logger

if TYPE_CHECKING:
    from nxs.application.session_state import SessionState

logger = get_logger("state_viewer")


class StateViewerPanel(Widget):
    """Panel for visualizing session state (user profile, knowledge base, stats).

    Displays accumulated knowledge extracted and managed by SessionState:
    1. User Profile - Who the user is (name, expertise, project)
    2. Knowledge Base - Facts learned (configuration, decisions, findings)
    3. Interaction Context - Current conversation context
    4. Session Statistics - Message count, cost, tool usage

    Essential UI for understanding what the session "knows".
    """

    DEFAULT_CSS = """
    StateViewerPanel {
        width: 100%;
        height: 100%;
        background: $panel;
        border: solid $primary;
    }

    StateViewerPanel > Container {
        width: 100%;
        height: 100%;
    }

    StateViewerPanel #state-header {
        height: 3;
        content-align: center middle;
        background: $primary;
        color: $text;
        text-style: bold;
    }

    StateViewerPanel #state-content {
        height: 1fr;
        overflow-y: auto;
        padding: 1;
    }

    StateViewerPanel .section-title {
        text-style: bold;
        color: $accent;
        margin: 1 0 0 0;
    }

    StateViewerPanel .section-content {
        padding: 0 0 1 1;
        color: $text;
    }

    StateViewerPanel .empty-state {
        color: $text-muted;
        text-style: italic;
        padding: 0 0 1 1;
    }
    """

    has_state = reactive(False)

    def compose(self) -> ComposeResult:
        """Compose the state viewer layout."""
        with Container():
            yield Static("🧠 Session Knowledge", id="state-header")

            with ScrollableContainer(id="state-content"):
                yield Static("Loading session state...", id="loading")

    def update_state(self, session_state: Optional["SessionState"]) -> None:
        """Update the state visualization.

        Args:
            session_state: SessionState instance to visualize
        """
        if session_state is None:
            self._show_empty_state()
            return

        self.has_state = True

        # Clear current content
        content = self.query_one("#state-content", ScrollableContainer)
        content.remove_children()

        # 1. User Profile Section
        profile_widget = self._render_user_profile(session_state)
        if profile_widget:
            content.mount(profile_widget)

        # 2. Knowledge Base Section
        kb_widget = self._render_knowledge_base(session_state)
        if kb_widget:
            content.mount(kb_widget)

        # 3. Interaction Context Section
        ctx_widget = self._render_interaction_context(session_state)
        if ctx_widget:
            content.mount(ctx_widget)

        # 4. Session Statistics Section
        stats_widget = self._render_statistics(session_state)
        if stats_widget:
            content.mount(stats_widget)

        logger.debug("Updated state viewer")

    def _show_empty_state(self) -> None:
        """Show empty state message."""
        content = self.query_one("#state-content", ScrollableContainer)
        content.remove_children()

        content.mount(Static(
            "No session state available.\n"
            "Start chatting to accumulate knowledge!",
            classes="empty-state"
        ))

    def _render_user_profile(self, state: "SessionState") -> Optional[Static]:
        """Render user profile section.

        Returns:
            Static widget with profile info, or None if profile is empty
        """
        profile = state.user_profile

        if not profile.has_information():
            return None

        text = Text()
        text.append("👤 User Profile\n", style="bold cyan")

        # Add profile fields
        if profile.name:
            text.append(f"  Name: {profile.name}\n", style="white")

        if profile.occupation:
            text.append(f"  Occupation: {profile.occupation}\n", style="white")

        if profile.expertise_level:
            text.append(f"  Expertise: {profile.expertise_level}\n", style="white")

        if profile.programming_languages:
            langs = ", ".join(profile.programming_languages[:5])
            text.append(f"  Languages: {langs}\n", style="white")

        if profile.frameworks:
            frameworks = ", ".join(profile.frameworks[:5])
            text.append(f"  Frameworks: {frameworks}\n", style="white")

        if profile.current_project:
            text.append(f"  Project: {profile.current_project}\n", style="white")

        if profile.communication_style:
            text.append(f"  Style: {profile.communication_style}\n", style="white")

        text.append("")  # Spacing

        return Static(text)

    def _render_knowledge_base(self, state: "SessionState") -> Optional[Static]:
        """Render knowledge base section.

        Returns:
            Static widget with facts, or None if no facts
        """
        kb = state.knowledge_base

        if not kb.facts:
            return None

        text = Text()
        text.append("📚 Knowledge Base\n", style="bold cyan")

        # Show up to 10 most recent facts
        recent_facts = kb.facts[-10:]

        for fact in reversed(recent_facts):  # Most recent first
            # Truncate long facts
            content = fact.content
            if len(content) > 80:
                content = content[:77] + "..."

            # Show source and confidence
            confidence_indicator = "●" if fact.confidence > 0.8 else "○"
            source_color = {
                "conversation": "green",
                "research": "blue",
                "tool": "yellow",
                "file": "magenta",
            }.get(fact.source, "white")

            text.append(f"  {confidence_indicator} ", style=f"{source_color}")
            text.append(f"{content}\n", style="white")

        if len(kb.facts) > 10:
            text.append(f"\n  ... and {len(kb.facts) - 10} more facts", style="dim")

        text.append("")  # Spacing

        return Static(text)

    def _render_interaction_context(self, state: "SessionState") -> Optional[Static]:
        """Render interaction context section.

        Returns:
            Static widget with context info, or None if no context
        """
        ctx = state.interaction_context

        if not ctx.current_topic and not ctx.current_intent:
            return None

        text = Text()
        text.append("💬 Current Context\n", style="bold cyan")

        if ctx.current_topic:
            text.append(f"  Topic: {ctx.current_topic}\n", style="white")

        if ctx.current_intent:
            intent_emoji = {
                "question": "❓",
                "command": "⚡",
                "research": "🔍",
                "chat": "💭",
                "clarification": "🤔",
            }.get(ctx.current_intent.type, "💬")

            confidence = int(ctx.current_intent.confidence * 100)
            text.append(
                f"  Intent: {intent_emoji} {ctx.current_intent.type} ({confidence}%)\n",
                style="white"
            )

        # Interaction stats
        if ctx.question_count > 0 or ctx.command_count > 0:
            text.append(f"\n  Interaction Stats:\n", style="dim")
            if ctx.question_count > 0:
                text.append(f"    Questions: {ctx.question_count}\n", style="dim")
            if ctx.command_count > 0:
                text.append(f"    Commands: {ctx.command_count}\n", style="dim")
            if ctx.research_count > 0:
                text.append(f"    Research: {ctx.research_count}\n", style="dim")

        text.append("")  # Spacing

        return Static(text)

    def _render_statistics(self, state: "SessionState") -> Optional[Static]:
        """Render session statistics section.

        Returns:
            Static widget with stats
        """
        meta = state.state_metadata

        text = Text()
        text.append("📊 Session Statistics\n", style="bold cyan")

        text.append(f"  Messages: {meta.message_count}\n", style="white")
        text.append(f"  Tool Calls: {meta.tool_call_count}\n", style="white")

        # Tokens
        total_tokens = meta.total_input_tokens + meta.total_output_tokens
        if total_tokens > 0:
            text.append(f"  Tokens: {total_tokens:,}\n", style="white")

            # Cache efficiency
            cache_eff = meta._calculate_cache_efficiency()
            if cache_eff > 0:
                cache_pct = int(cache_eff * 100)
                text.append(f"  Cache Hit: {cache_pct}%\n", style="green")

        # Cost
        if meta.total_cost > 0:
            text.append(f"  Cost: ${meta.total_cost:.4f}\n", style="yellow")

        # Average response time
        if meta.average_response_time > 0:
            text.append(f"  Avg Response: {meta.average_response_time:.2f}s\n", style="white")

        text.append("")  # Spacing

        return Static(text)
