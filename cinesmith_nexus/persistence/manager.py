import sqlite3
from pathlib import Path
import json
from datetime import datetime
from typing import Dict, List, Any

class PersistenceManager:
    def __init__(self, project_path: Path):
        self.project_path = project_path
        self.db_dir = self.project_path / ".cinesmith-nexus"
        self.db_path = self.db_dir / "cinesmith.db"
        self.manifest_dir = self.db_dir / "manifests"
        
        # Ensure directory exists
        self.db_dir.mkdir(parents=True, exist_ok=True)
        
        self._init_db()

    def _init_db(self):
        """Initialize the SQLite schema for Cinesmith Nexus."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # 1. Registry Table (Project Metadata)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS project_registry (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 2. Workflows Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS workflows (
                    id TEXT PRIMARY KEY,
                    source_file TEXT,
                    content_hash TEXT,
                    node_count INTEGER,
                    edge_count INTEGER,
                    referenced_prompts TEXT, -- JSON array
                    referenced_models TEXT,  -- JSON array
                    referenced_characters TEXT, -- JSON array
                    raw_manifest TEXT,       -- Full JSON blob
                    indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 3. Characters Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS characters (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    source_file TEXT,
                    content_hash TEXT,
                    attributes TEXT,       -- JSON blob
                    consistency_rules TEXT, -- JSON blob
                    referenced_by_workflows TEXT, -- JSON array
                    raw_manifest TEXT,
                    indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 4. Prompts Table (Optimized for search)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS prompts (
                    id TEXT PRIMARY KEY,
                    prompt_type TEXT,
                    content TEXT,          -- The actual text content
                    source_file TEXT,
                    content_hash TEXT,
                    semantic_tags TEXT,    -- JSON array
                    inheritance_chain TEXT, -- JSON array
                    raw_manifest TEXT,
                    indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Indices for performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_wf_prompts ON workflows(referenced_prompts)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_prompt_type ON prompts(prompt_type)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_char_name ON characters(name)")

            conn.commit()

    def ingest_manifests(self, registry: Dict[str, Any]):
        """Ingest the entire manifest registry into SQLite."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # A. Update Project Registry
            proj = registry["project"]
            cursor.execute("INSERT OR REPLACE INTO project_registry (key, value) VALUES (?, ?)", 
                           ("name", proj["name"]))
            cursor.execute("INSERT OR REPLACE INTO project_registry (key, value) VALUES (?, ?)", 
                           ("path", proj["path"]))
            cursor.execute("INSERT OR REPLACE INTO project_registry (key, value) VALUES (?, ?)", 
                           ("version", proj["manifest_version"]))

            # B. Ingest Workflows
            for wf in registry["manifests"]["workflows"]:
                wf_path = self.manifest_dir / wf["manifest"]
                if wf_path.exists():
                    data = json.loads(wf_path.read_text())
                    cursor.execute("""
                        INSERT OR REPLACE INTO workflows 
                        (id, source_file, content_hash, node_count, edge_count, referenced_prompts, referenced_models, referenced_characters, raw_manifest)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        data["id"],
                        data["source_file"],
                        data["content_hash"],
                        data.get("metadata", {}).get("node_count", 0),
                        data.get("metadata", {}).get("total_edges", 0),
                        json.dumps(data.get("referenced_prompts", [])),
                        json.dumps(data.get("referenced_models", [])),
                        json.dumps(data.get("referenced_characters", [])),
                        json.dumps(data)
                    ))

            # C. Ingest Characters
            for char in registry["manifests"]["characters"]:
                char_path = self.manifest_dir / char["manifest"]
                if char_path.exists():
                    data = json.loads(char_path.read_text())
                    cursor.execute("""
                        INSERT OR REPLACE INTO characters 
                        (id, name, source_file, content_hash, attributes, consistency_rules, referenced_by_workflows, raw_manifest)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        data["id"],
                        data.get("name", ""),
                        data["source_file"],
                        data["content_hash"],
                        json.dumps(data.get("attributes", {})),
                        json.dumps(data.get("consistency_rules", {})),
                        json.dumps(data.get("referenced_by", {}).get("workflows", [])),
                        json.dumps(data)
                    ))

            # D. Ingest Prompts
            for pr in registry["manifests"]["prompts"]:
                pr_path = self.manifest_dir / pr["manifest"]
                if pr_path.exists():
                    data = json.loads(pr_path.read_text())
                    cursor.execute("""
                        INSERT OR REPLACE INTO prompts 
                        (id, prompt_type, content, source_file, content_hash, semantic_tags, inheritance_chain, raw_manifest)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        data["id"],
                        data.get("prompt_type", "positive"),
                        data.get("content", ""),
                        data["source_file"],
                        data["content_hash"],
                        json.dumps(data.get("semantic_tags", [])),
                        json.dumps(data.get("inheritance_chain", [])),
                        json.dumps(data)
                    ))

            conn.commit()
        print(f"Ingestion complete: {len(registry['manifests']['workflows'])} workflows, "
              f"{len(registry['manifests']['characters'])} characters, "
              f"{len(registry['manifests']['prompts'])} prompts.")

    def query_workflow_by_prompt(self, prompt_id: str) -> List[Dict]:
        """Find all workflows that reference a specific prompt ID."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            # Since referenced_prompts is stored as a JSON string, we use SQLite's json_each
            query = """
                SELECT id, source_file FROM workflows, json_each(workflows.referenced_prompts) 
                WHERE json_each.value = ?
            """
            cursor.execute(query, (prompt_id,))
            return [dict(row) for row in cursor.fetchall()]

    def get_project_metadata(self) -> Dict[str, Any]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT key, value FROM project_registry")
            return {row["key"]: row["value"] for row in cursor.fetchall()}

if __name__ == "__main__":
    # Quick Test
    import sys
    test_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    pm = PersistenceManager(test_path)
    print("Persistence Manager initialized and schema verified.")
