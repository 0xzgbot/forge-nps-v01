import sqlite3
from pathlib import Path
from typing import List, Dict, Any
from cinesmith_nexus.persistence.search import BM25Searcher

class SearchEngine:
    """
    Orchestrates the integration between SQLite and BM25 for 
    high-speed semantic retrieval of Cinesmith assets.
    """
    def __init__(self, project_path: Path):
        self.project_path = project_path
        self.db_path = self.project_path / ".cinesmith-nexus" / "cinesmith.db"
        self.searcher = BM25Searcher()
        self._is_indexed = False

    def build_index(self):
        """Loads text from SQLite and builds the in-memory BM25 index."""
        print("Building search index...")
        docs_to_index = []

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # 1. Index Prompts (Highest Priority for Search)
            cursor.execute("SELECT id, content FROM prompts")
            for row in cursor.fetchall():
                docs_to_index.append({
                    "id": row["id"],
                    "type": "prompt",
                    "content": row["content"]
                })

            # 2. Index Characters (Attributes & Names)
            cursor.execute("SELECT id, name, attributes FROM characters")
            for row in cursor.fetchall():
                import json
                attr_text = f"{row['name']} {row['attributes']}"
                docs_to_index.append({
                    "id": row["id"],
                    "type": "character",
                    "content": attr_text
                })

            # 3. Index Workflows (Metadata & Node types)
            cursor.execute("SELECT id, raw_manifest FROM workflows")
            for row in cursor.fetchall():
                import json
                data = json.loads(row["raw_manifest"])
                node_types = " ".join([n.get("class_type", "") for n in data.get("nodes", [])])
                docs_to_index.append({
                    "id": row["id"],
                    "type": "workflow",
                    "content": f"{row['id']} {node_types}"
                })

        if docs_to_index:
            self.searcher.add_documents(docs_to_index)
            self._is_indexed = True
            print(f"Index built with {len(docs_to_index)} documents.")
        else:
            print("No documents found to index.")

    def query(self, text: str, top_n: int = 5) -> List[Dict[str, Any]]:
        """Performs a keyword search and returns matched IDs."""
        if not self._is_indexed:
            # Auto-build if user tries to search without indexing first
            self.build_index()

        results = self.searcher.search(text, top_n=top_n)
        return results

if __name__ == "__main__":
    import sys
    test_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    engine = SearchEngine(test_path)
    engine.build_index()
    
    print("\n--- Test Query: 'cyberpunk neon' ---")
    res = engine.query("cyberpunk neon")
    for r in res:
        print(f"ID: {r['id']} (Score: {r['score']:.4f})")

    print("\n--- Test Query: 'elena character' ---")
    res = engine.query("elena character")
    for r in res:
        print(f"ID: {r['id']} (Score: {r['score']:.4f})")
