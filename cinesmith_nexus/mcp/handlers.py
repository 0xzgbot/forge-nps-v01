import json
from pathlib import Path
from typing import Any, Dict

# Local imports assuming standard package structure
try:
    from cinesmith_nexus.persistence.engine import SearchEngine
    from cinesmith_nexus.graph.engine import GraphEngine
except ImportError:
    from persistence.engine import SearchEngine
    from graph.engine import GraphEngine

class CinesmithMCPHandlers:
    """
    The implementation layer that connects MCP tool calls to 
    the actual logic in the Cinesmith Nexus core.
    """
    def __init__(self, project_path: Path):
        self.project_path = project_path
        self.search_engine = SearchEngine(project_path)
        self.graph_engine = GraphEngine(project_path)
        # Note: We don't instantiate PersistenceManager here to avoid unnecessary DB writes,
        # but we use the existing DB for reads via engines.

    def handle_cinesmith_query(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Tool: cinesmith_query - Semantic keyword search."""
        query = arguments.get("query")
        if not query:
            return {"error": "Missing required argument: 'query'"}
        
        results = self.search_engine.query(query)
        return {
            "results": results,
            "count": len(results)
        }

    def handle_cinesmith_context(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Tool: cinesmith_context - Retrieve full metadata for an asset."""
        asset_id = arguments.get("asset_id")
        if not asset_id:
            return {"error": "Missing required argument: 'asset_id'"}

        # We use sqlite directly to query the raw manifest from DB
        import sqlite3
        with sqlite3.connect(self.project_path / ".cinesmith-nexus" / "cinesmith.db") as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Search all tables for the ID (Workflows, Characters, Prompts)
            found_data = None
            for table in ["workflows", "characters", "prompts"]:
                cursor.execute(f"SELECT raw_manifest FROM {table} WHERE id = ?", (asset_id,))
                row = cursor.fetchone()
                if row:
                    found_data = json.loads(row["raw_manifest"])
                    break
            
        if not found_data:
            return {"error": f"Asset with ID '{asset_id}' not found."}
            
        return {
            "asset_id": asset_id,
            "data": found_data
        }

    def handle_cinesmith_impact(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Tool: cinesmith_impact - Find all entities affected by a change."""
        asset_id = arguments.get("asset_id")
        if not asset_id:
            return {"error": "Missing required argument: 'asset_id'"}

        # Ensure graph is built for traversal
        self.graph_engine.build_graph()
        impacted = self.graph_engine.get_impact(asset_id)
        
        return {
            "asset_id": asset_id,
            "affected_entities": list(impacted)
        }

    def handle_cinesmith_trace(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Tool: cinesmith_trace - Discover the connection chain between assets."""
        start_id = arguments.get("start_id")
        end_id = arguments.get("end_id")
        
        if not start_id or not end_id:
            return {"error": "Missing required arguments: 'start_id' and 'end_id'"}

        self.graph_engine.build_graph()
        path = self.graph_engine.find_path(start_id, end_id)
        
        if not path:
            return {"error": f"No connection found between {start_id} and {end_id}"}

        return {
            "path": path,
            "length": len(path) - 1
        }
