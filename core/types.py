import enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional

class AuditStatus(str, enum.Enum):
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"

@dataclass
class RemediationPayload:
    status: AuditStatus
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)

@dataclass
class AuditPayload:
    audit_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: AuditStatus
    details: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)