import sys
from pathlib import Path

# Add project root to path for local execution and testing
project_root = "/Users/zgbot/Desktop/forge_nps_v01"
if project_root not in sys.path:
    sys.path.append(project_root)

from forge_nexus.mcp.base import MCPToolDefinition
from forge_nexus.mcp.registry import MCPToolRegistry
from forge_nexus.mcp.handlers import ForgeMCPHandlers

class ForgeMCPServer:
    """The primary entry point for the Forge Nexus MCP Server."""
    def __init__(self, project_path: Path):
        self.project_path = project_path
        self.registry = MCPToolRegistry()
        self.handlers = ForgeMCPHandlers(project_path)
        self._register_tools()

    def _register_tools(self):
        """Defines the interface for all available tools."""
        
        # 1. forge_query
        self.registry.register(MCPToolDefinition(
            name="forge_query",
            description="Performs a semantic keyword search across workflows, characters, and prompts.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The keywords to search for (e.g., 'cyberpunk neon')"}
                },
                "required": ["query"]
            }
        ))

        # 2. forge_context
        self.registry.register(MCPToolDefinition(
            name="forge_context",
            description="Retrieves the full structured metadata (manifest) for a specific asset ID.",
            input_schema={
                "type": "object",
                "properties": {
                    "asset_id": {"type": "string", "description": "The unique identifier of the asset (e.g., 'char_elena')"}
                },
                "required": ["asset_id"]
            }
        ))

        # 3. forge_impact
        self.registry.register(MCPToolDefinition(
            name="forge_impact",
            description="Identifies all downstream assets that depend on a specific asset (e.g., 'What breaks if I change this prompt?').",
            input_schema={
                "type": "object",
                "properties": {
                    "asset_id": {"type": "string", "description": "The ID of the asset being changed."}
                },
                "required": ["asset_id"]
            }
        ))

        # 4. forge_trace
        self.registry.register(MCPToolDefinition(
            name="forge_trace",
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
            "forge_query": self.handlers.handle_forge_query,
            "forge_context": self.handlers.handle_forge_context,
            "forge_impact": self.handlers.handle_forge_impact,
            "forge_trace": self.handlers.handle_forge_trace,
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
            "serverName": "ForgeNexus-Intelligence",
            "tools": self.registry.get_all_definitions()
        }

if __name__ == "__main__":
    # Integration Test
    test_path = Path("/Users/zgbot/Desktop/forge_nps_v01")
    server = ForgeMCPServer(test_path)
    
    print("--- MCP Server Discovery Test ---")
    manifesto = server.get_manifesto()
    print(f"Registered tools: {[t['name'] for t in manifesto['tools']]}")

    print("\n--- Testing forge_query ---")
    # Note: This requires a DB with data to work properly
    print(server.call_tool("forge_query", {"query": "cyberpunk"}))

    print("\n--- Testing forge_impact (Empty Case) ---")
    print(server.call_tool("forge_impact", {"asset_id": "nonexistent_id"}))
