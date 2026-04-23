"""
Utility functions for the backend
"""

from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Any


# Time window for grouping sessions (5 minutes in milliseconds)
SESSION_TIME_WINDOW_MS = 5 * 60 * 1000


def clean_old_url_entries(url_sessions: Dict[str, List[Dict]], device_id: str) -> None:
    """
    Remove old URL entries from a device that are outside the time window
    
    Args:
        url_sessions: Dictionary mapping device_id to list of URL entries
        device_id: Device ID to clean
    """
    current_time = datetime.now().timestamp() * 1000
    if device_id in url_sessions:
        url_sessions[device_id] = [
            entry for entry in url_sessions[device_id]
            if current_time - entry["timestamp"] < SESSION_TIME_WINDOW_MS
        ]


def get_time_ago_string(timestamp: float) -> str:
    """
    Convert timestamp to human-readable 'time ago' string
    
    Args:
        timestamp: Milliseconds since epoch
        
    Returns:
        String like "5s ago" or "2m ago"
    """
    current_time = datetime.now().timestamp() * 1000
    seconds_ago = int((current_time - timestamp) / 1000)
    
    if seconds_ago < 60:
        return f"{seconds_ago}s ago"
    elif seconds_ago < 3600:
        return f"{seconds_ago // 60}m ago"
    else:
        return f"{seconds_ago // 3600}h ago"


def format_fingerprint_summary(fingerprint: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a summary of key fingerprint data
    
    Args:
        fingerprint: Full fingerprint data
        
    Returns:
        Dictionary with summary info
    """
    nav = fingerprint.get("navigator", {})
    return {
        "device_id": fingerprint.get("deviceID", "unknown"),
        "user_agent": nav.get("userAgent", "unknown")[:100],
        "platform": nav.get("platform", "unknown"),
        "language": nav.get("language", "unknown"),
        "is_mobile": nav.get("isMobile", False),
        "is_workstation": nav.get("isWorkstation", False),
        "os": fingerprint.get("operatingSystem", "unknown"),
        "public_ip": fingerprint.get("publicIP", {}).get("ip", "unknown"),
        "timestamp": fingerprint.get("timestamp", 0),
    }


def extract_behavior_summary(behavior: Dict[str, Any]) -> Dict[str, int]:
    """
    Extract summary counts from behavior data
    
    Args:
        behavior: Behavior dictionary from heartbeat
        
    Returns:
        Dictionary with event counts
    """
    return {
        "mouseMoves": len(behavior.get("mouseMoves", [])),
        "clicks": len(behavior.get("clicks", [])),
        "keydowns": len(behavior.get("keydowns", [])),
        "touches": len(behavior.get("touches", [])),
        "scrolls": len(behavior.get("scrolls", [])),
        "copyPastes": len(behavior.get("copyPastes", [])),
        "navigationEvents": len(behavior.get("navigationEvents", [])),
    }
