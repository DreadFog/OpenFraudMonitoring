"""
Utility functions for the backend
"""

from typing import Dict, Any


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
    }
