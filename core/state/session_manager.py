import json
import os
from datetime import datetime
from typing import List, Dict, Any

class SessionManager:
    def __init__(self, session_id: str, output_dir: str = "data/sessions"):
        self.session_id = session_id
        self.output_dir = output_dir
        self.state_path = os.path.join(output_dir, f"{session_id}.json")
        os.makedirs(output_dir, exist_ok=True)
        
        self.data = {
            "session_id": session_id,
            "created_at": datetime.now().isoformat(),
            "script_path": "",
            "lore_paths": [],
            "shots": {},
            "autonomy_score": 0.0,
            "total_fixes_by_hermes": 0,
            "total_kimi_escalations": 0
        }
        self.load()

    def create_session(self, script_path: str, lore_paths: List[str]) -> Dict[str, Any]:
        self.data["script_path"] = script_path
        self.data["lore_paths"] = lore_paths
        self.save()
        return self.data

    def update_shot_status(self, shot_id: str, status: str, data: Dict[str, Any] = None):
        if shot_id not in self.data["shots"]:
            self.data["shots"][shot_id] = {}
        
        self.data["shots"][shot_id]["status"] = status
        if data:
            self.data["shots"][shot_id].update(data)
        self.save()

    def get_session_summary(self) -> Dict[str, Any]:
        return self.data

    def save(self):
        with open(self.state_path, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, indent=2)

    def load(self, session_id: str = None):
        if session_id:
            self.session_id = session_id
            self.state_path = os.path.join(self.output_dir, f"{session_id}.json")
            
        if os.path.exists(self.state_path):
            with open(self.state_path, 'r', encoding='utf-8') as f:
                loaded_data = json.load(f)
                self.data.update(loaded_data)
