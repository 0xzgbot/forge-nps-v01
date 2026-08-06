import sys
from pathlib import Path

# Add project root to path for local execution and testing
project_root = Path(__file__).resolve().parents[2]
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from cinesmith_nexus.mcp.base import MCPToolDefinition
from cinesmith_nexus.mcp.registry import MCPToolRegistry
from cinesmith_nexus.mcp.handlers import CinesmithMCPHandlers

class CinesmithMCPServer:
    """The primary entry point for the Cinesmith Nexus MCP Server."""
    def __init__(self, project_path: Path):
        self.project_path = project_path
        self.registry = MCPToolRegistry()
        self.handlers = CinesmithMCPHandlers(project_path)
        self._register_tools()

    def _register_tools(self):
        """Defines the interface for all available tools."""
        
        # 1. cinesmith_query
        self.registry.register(MCPToolDefinition(
            name="cinesmith_query",
            description="Performs a semantic keyword search across workflows, characters, and prompts.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The keywords to search for (e.g., 'cyberpunk neon')"}
                },
                "required": ["query"]
            }
        ))

        # 2. cinesmith_context
        self.registry.register(MCPToolDefinition(
            name="cinesmith_context",
            description="Retrieves the full structured metadata (manifest) for a specific asset ID.",
            input_schema={
                "type": "object",
                "properties": {
                    "asset_id": {"type": "string", "description": "The unique identifier of the asset (e.g., 'char_elena')"}
                },
                "required": ["asset_id"]
            }
        ))

        # 3. cinesmith_impact
        self.registry.register(MCPToolDefinition(
            name="cinesmith_impact",
            description="Identifies all downstream assets that depend on a specific asset (e.g., 'What breaks if I change this prompt?').",
            input_schema={
                "type": "object",
                "properties": {
                    "asset_id": {"type": "string", "description": "The ID of the asset being changed."}
                },
                "required": ["asset_id"]
            }
        ))

        # 4. cinesmith_trace
        self.registry.register(MCPToolDefinition(
            name="cinesmith_trace",
            description="Finds the logical connection path between two assets (e.g., how a workflow connects to a character).",
            input_schema={
                "type": "object",
                "properties": {
                    "start_id": {"type": "string", "description": "The starting asset ID."},
                    "end_id": {"type": "string", "description": "The target asset ID."}
                },
                "required": ["start_id", "end_id"]
            }
        ))

    def call_tool(self, name: str, arguments: dict) -> dict:
        """Dispatches a tool call to the appropriate handler."""
        handler_map = {
            "cinesmith_query": self.handlers.handle_cinesmith_query,
            "cinesmith_context": self.handlers.handle_cinesmith_context,
            "cinesmith_impact": self.handlers.handle_cinesmith_impact,
            "cinesmith_trace": self.handlers.handle_cinesmith_trace,
        }

        handler = handler_map.get(name)
        if not handler:
            return {"error": f"Tool '{name}' is not registered."}

        try:
            return handler(arguments)
        except Exception as e:
            return {"error": f"Execution failed: {str(e)}"}

    def get_manifesto(self) -> dict:
        """Returns the full MCP tool definition manifest for client discovery."""
        return {
            "mcpVersion": "1.0",
            "serverName": "CinesmithNexus-Intelligence",
            "tools": self.registry.get_all_definitions()
        }

if __name__ == "__main__":
    # Integration Test
    test_path = project_root
    server = CinesmithMCPServer(test_path)
    
    print("--- MCP Server Discovery Test ---")
    manifesto = server.get_manifesto()
    print(f"Registered tools: {[t['name'] for t in manifesto['tools']]}")

    print("\n--- Testing cinesmith_query ---")
    # Note: This requires a DB with data to work properly
    print(server.call_tool("cinesmith_query", {"query": "cyberpunk"}))

    print("\n--- Testing cinesmith_impact (Empty Case) ---")
    print(server.call_tool("cinesmith_impact", {"asset_id": "nonexistent_id"}))
