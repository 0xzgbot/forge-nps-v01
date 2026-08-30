---
name: shot-plan-schema
description: Use when compiling a structured shot plan for Cinesmith. JSON schema for
  campaign shots the Hermes agent writes.
version: 1.0.0
author: Cinesmith
license: MIT
metadata:
  hermes:
    tags:
    - shot-plan
    - schema
    category: cinesmith
---

class ShotPlan(BaseModel):
    campaign_id: str = Field(..., description="Unique identifier for the campaign")
    shot_id: str = Field(..., description="Unique identifier for the shot within the campaign")
    sequence: int = Field(..., description="Sequential number of the shot in the scene")
    narrative_intent: str = Field(..., description="Brief description of what is happening in this shot")
    visual_brief: str = Field(..., description="Short visual description for the shot generation")
    characters: List[str] = Field(..., description="List of character names appearing in this shot")
    environment: str = Field(..., description="Setting or environment description")
    camera_direction: str = Field(..., description="Camera movement and angle direction")
    lighting_direction: str = Field(..., description="Lighting setup direction and quality")
    rationale: str = Field(..., description="Reasoning behind this shot selection and continuity")
    constraints: List[str] = Field(..., description="Specific constraints that must be met for generation")