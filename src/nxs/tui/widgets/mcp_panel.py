"""
MCPPanel - A scrollable panel displaying MCP servers and their artifacts.
"""

from textual.widgets import RichLog


class MCPPanel(RichLog):
    """
    A panel that displays MCP servers and their artifacts.

    Features:
    - Displays each connected MCP server
    - Shows tools (T), prompts (P), and resources (R) for each server
    - Auto-scrolling
    - Compact, efficient display
    """

    BORDER_TITLE = "MCP Servers"

    def __init__(self, **kwargs):
        """Initialize the MCP panel with Rich markup enabled."""
        super().__init__(
            markup=True,
            highlight=False,
            auto_scroll=True,
            wrap=True,
            **kwargs
        )
        self.write("[bold cyan]MCP Servers & Artifacts[/]\n")
        self.add_divider()

    def update_servers(
        self,
        servers_data: dict[str, dict[str, list[str]]]
    ):
        """
        Update the panel with server data.

        Args:
            servers_data: Dictionary mapping server names to their artifacts.
                         Format: {
                             "server_name": {
                                 "tools": ["tool1", "tool2"],
                                 "prompts": ["prompt1", "prompt2"],
                                 "resources": ["resource1", "resource2"]
                             }
                         }
        """
        # Clear existing content
        self.clear()
        self.write("[bold cyan]MCP Servers & Artifacts[/]\n")
        self.add_divider()

        if not servers_data:
            self.write("[dim]No MCP servers connected[/]\n")
            return

        for server_name, artifacts in servers_data.items():
            # Server header
            self.write(f"\n[bold yellow]📡 {server_name}[/]\n")
            
            # Tools
            tools = artifacts.get("tools", [])
            if tools:
                for tool in tools:
                    self.write(f"  [cyan](T)[/] {tool}\n")
            
            # Prompts
            prompts = artifacts.get("prompts", [])
            if prompts:
                for prompt in prompts:
                    self.write(f"  [green](P)[/] {prompt}\n")
            
            # Resources
            resources = artifacts.get("resources", [])
            if resources:
                for resource in resources:
                    # Extract resource name from URI if it's a full URI
                    resource_display = resource
                    if "://" in resource:
                        parts = resource.split("/")
                        resource_display = parts[-1] if parts else resource
                    self.write(f"  [magenta](R)[/] {resource_display}\n")
            
            # Show counts if any artifacts exist
            total = len(tools) + len(prompts) + len(resources)
            if total == 0:
                self.write("  [dim]No artifacts[/]\n")
            else:
                self.write(f"  [dim]({len(tools)} tools, {len(prompts)} prompts, {len(resources)} resources)[/]\n")
            
            self.add_divider()

    def add_divider(self):
        """Add a visual divider between sections."""
        self.write("[dim]" + "─" * 30 + "[/]\n")
