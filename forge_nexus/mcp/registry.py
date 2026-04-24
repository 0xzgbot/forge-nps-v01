import json
from pathlib import Path
from typing import List, Dict, Any, Optional

class MCPToolRegistry:
    """Manages the registration and serialization of MCP tools."""
    def __init__(self):
        self.tools: Dict[str, Any] = {}

    def register(self, tool_def: Any):
        """Registers a tool definition (expects MCPToolDefinition)."""
        self.tools[tool_def.name] = tool_def.to_dict()

    def get_all_definitions(self) -> List[Dict[str, Any]]:
        """Returns all registered tools as a list of dictionaries."""
        return list(self.tools.values())

    def get_tool(self, name: str) -> Optional[Dict[str, Any]]:
        """Retrieves a specific tool definition."""
        return self.tools.get(name)

from typing import Optional
