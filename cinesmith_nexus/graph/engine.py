import networkx as nx
from pathlib import Path
import sqlite3
import json
from typing import Dict, List, Any, Set

class GraphEngine:
    """
    The Intelligence Brain of Cinesmith Nexus.
    Converts relational SQLite data into a directed multi-graph (NetworkX)
    to enable complex dependency analysis and impact tracing.
    """
    def __init__(self, project_path: Path):
        self.project_path = project_path
        self.db_path = self.project_path / ".cinesmith-nexus" / "cinesmith.db"
        self.graph = nx.MultiDiGraph()
        self._is_built = False

    def build_graph(self):
        """Builds the MultiDiGraph by traversing SQLite tables."""
        print("Building Knowledge Graph...")
        new_graph = nx.MultiDiGraph()

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # 1. Load Nodes (Entities)
            # Workflows
            cursor.execute("SELECT id, source_file FROM workflows")
            for row in cursor.fetchall():
                new_graph.add_node(row["id"], type="workflow", source=row["source_file"])

            # Characters
            cursor.execute("SELECT id, name, source_file FROM characters")
            for row in cursor.fetchall():
                new_graph.add_node(row["id"], type="character", name=row["name"], source=row["source_file"])

            # Prompts
            cursor.execute("SELECT id, content, source_file FROM prompts")
            for row in cursor.fetchall():
                new_graph.add_node(row["id"], type="prompt", content=row["content"], source=row["source_file"])

            # 2. Load Edges (Relationships)
            # Workflows -> Prompts
            cursor.execute("SELECT id, referenced_prompts FROM workflows")
            for row in cursor.fetchall():
                wf_id = row["id"]
                refs = json.loads(row["referenced_prompts"])
                for p_id in refs:
                    new_graph.add_edge(wf_id, p_id, relation="uses_prompt")

            # Workflows -> Characters
            cursor.execute("SELECT id, referenced_characters FROM workflows")
            for row in cursor.fetchall():
                wf_id = row["id"]
                refs = json.loads(row["referenced_characters"])
                for c_id in refs:
                    new_graph.add_edge(wf_id, c_id, relation="uses_character")

            # Characters -> Prompts (extracted from raw_manifest JSON blob)
            cursor.execute("SELECT id, raw_manifest FROM characters")
            for row in cursor.fetchall():
                char_id = row["id"]
                data = json.loads(row["raw_manifest"])
                for p_id in data.get("linked_prompts", []):
                    new_graph.add_edge(char_id, p_id, relation="defines_prompt")

        self.graph = new_graph
        self._is_built = True
        print(f"Graph built: {self.graph.number_of_nodes()} nodes, {self.graph.number_of_edges()} edges.")

    def get_impact(self, entity_id: str) -> Set[str]:
        """Finds all entities that depend on the given entity (Reverse Traversal)."""
        if not self._is_built:
            raise RuntimeError("Graph must be built before querying.")
        
        # We want to find things that point TO this entity
        try:
            return set(nx.ancestors(self.graph, entity_id))
        except nx.NetworkXError:
            return set()

    def get_dependencies(self, entity_id: str) -> Set[str]:
        """Finds all entities the given entity depends on (Forward Traversal)."""
        if not self._is_built:
            raise RuntimeError("Graph must be built before querying.")
        
        try:
            return set(nx.descendants(self.graph, entity_id))
        except nx.NetworkXError:
            return set()

    def find_path(self, start_node: str, end_node: str) -> List[str]:
        """Finds the connection chain between two entities."""
        if not self._is_built:
            raise RuntimeError("Graph must be built before querying.")
        try:
            return nx.shortest_path(self.graph, source=start_node, target=end_node)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []

if __name__ == "__main__":
    # Quick local test logic would go here
    pass
