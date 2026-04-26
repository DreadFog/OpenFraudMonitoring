"""
Risk analysis — leverages FPScanner's built-in bot detection.

FPScanner already runs 21 detection rules client-side and provides severity levels.
This module translates those into a cumulative risk score for the session.
"""

from typing import Dict, List, Tuple, Any

# Severity → score points mapping
SEVERITY_SCORES = {
    "high": 15,
    "medium": 8,
    "low": 3,
}


class RiskAnalyzer:
    """Translates FPScanner detection results into risk scores."""

    @staticmethod
    def analyze(fingerprint: Dict[str, Any]) -> Tuple[int, List[str]]:
        """
        Analyze a decrypted FPScanner fingerprint and return (score, flags).

        Uses fastBotDetection (quick boolean) and fastBotDetectionDetails
        (per-rule severity) to build the score.

        Args:
            fingerprint: Decrypted FPScanner fingerprint dict

        Returns:
            Tuple of (risk_score: 0-100, flags: list of triggered detection names)
        """
        flags = []
        score = 0

        details = fingerprint.get("fastBotDetectionDetails", {})

        for rule_name, result in details.items():
            if not isinstance(result, dict):
                continue
            if result.get("detected"):
                severity = result.get("severity", "medium")
                score += SEVERITY_SCORES.get(severity, 5)
                flags.append(rule_name)

        return min(score, 100), flags
