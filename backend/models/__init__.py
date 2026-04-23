"""
Session data models
"""

from datetime import datetime
from typing import Dict, List, Set, Any


class Session:
    """Represents a session tracked by device ID"""

    def __init__(self, device_id: str):
        self.device_id = device_id
        self.fingerprints: List[Dict[str, Any]] = []
        self.heartbeats: List[Dict[str, Any]] = []
        self.urls: Set[str] = set()
        self.session_ids: Set[str] = set()
        self.risk_score: int = 0
        self.flags: List[str] = []
        self.first_seen: float = 0
        self.last_seen: float = 0
        self.client_ip: str = ""

    def add_fingerprint(self, fingerprint: Dict[str, Any]) -> None:
        """Add a fingerprint to this session"""
        self.fingerprints.append(fingerprint)

    def add_heartbeat(self, heartbeat: Dict[str, Any]) -> None:
        """Add a heartbeat to this session"""
        self.heartbeats.append(heartbeat)

    def to_dict(self) -> Dict[str, Any]:
        """Convert session to dictionary"""
        return {
            "device_id": self.device_id,
            "fingerprints": self.fingerprints,
            "heartbeats": self.heartbeats,
            "urls": list(self.urls),
            "session_ids": list(self.session_ids),
            "risk_score": self.risk_score,
            "flags": self.flags,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "client_ip": self.client_ip,
        }
