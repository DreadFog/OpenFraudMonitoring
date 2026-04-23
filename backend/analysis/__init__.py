"""
Risk analysis and fraud detection engine
"""

from typing import Dict, List, Tuple, Any


class RiskAnalyzer:
    """Analyzes fingerprints for fraud signals and calculates risk scores"""

    @staticmethod
    def analyze(fingerprint: Dict[str, Any]) -> Tuple[int, List[str]]:
        """
        Analyze a fingerprint and return (score, flags)
        
        Args:
            fingerprint: Complete fingerprint data
            
        Returns:
            Tuple of (risk_score: 0-100, flags: list of detected issues)
        """
        flags = []
        score = 0

        bot = fingerprint.get("botSignals", {})
        nav = fingerprint.get("navigator", {})
        gl = fingerprint.get("webgl", {})

        # Bot/automation signals
        if bot.get("webdriver"):
            flags.append("WEBDRIVER_DETECTED")
            score += 40
        if bot.get("phantom"):
            flags.append("PHANTOMJS_DETECTED")
            score += 40
        if bot.get("nightmare"):
            flags.append("NIGHTMARE_DETECTED")
            score += 35
        if bot.get("puppeteer"):
            flags.append("PUPPETEER_DETECTED")
            score += 35
        if bot.get("selenium"):
            flags.append("SELENIUM_DETECTED")
            score += 35
        if bot.get("cdcProps"):
            flags.append(f"CHROMEDRIVER_PROPS:{','.join(bot.get('cdcProps', []))}")
            score += 45
        if bot.get("languages_empty"):
            flags.append("EMPTY_LANGUAGES")
            score += 20
        if bot.get("noPlugins"):
            flags.append("NO_PLUGINS_NO_LANGUAGES")
            score += 15
        if bot.get("nativeCheckPassed") is False:
            flags.append("NATIVE_SPOOFED")
            score += 30

        # Hardware inconsistencies
        if nav.get("hardwareConcurrency") == 0:
            flags.append("ZERO_CPU_CORES")
            score += 20
        if nav.get("deviceMemory") == 0:
            flags.append("ZERO_DEVICE_MEMORY")
            score += 15
        if not gl:
            flags.append("NO_WEBGL")
            score += 10

        # Screen signals
        scr = fingerprint.get("screen", {})
        if scr.get("width") == 0 or scr.get("height") == 0:
            flags.append("ZERO_SCREEN")
            score += 25
        if scr.get("colorDepth") == 0:
            flags.append("ZERO_COLOR_DEPTH")
            score += 15

        # Canvas/audio availability
        if not fingerprint.get("canvas") or not fingerprint.get("canvas", {}).get("dataURL"):
            flags.append("NO_CANVAS")
            score += 10
        if not fingerprint.get("audio"):
            flags.append("NO_AUDIO")
            score += 5

        # Timezone check
        if not fingerprint.get("timezone") or not fingerprint.get("timezone", {}).get("timezone"):
            flags.append("NO_TIMEZONE")
            score += 5

        # WebRTC IPs
        rtc_ips = fingerprint.get("webrtcIPs", [])
        if rtc_ips:
            local = [ip for ip in rtc_ips if ip.startswith(("10.", "172.", "192.168.", "::1", "fd"))]
            public = [ip for ip in rtc_ips if ip not in local]
            if public:
                flags.append(f"WEBRTC_PUBLIC_IP:{','.join(public)}")
            if local:
                flags.append(f"WEBRTC_LOCAL_IP:{','.join(local)}")

        # Public IP check
        public_ip = fingerprint.get("publicIP", {})
        if public_ip.get("ip"):
            flags.append(f"PUBLIC_IP:{public_ip.get('ip')}")

        score = min(score, 100)
        return score, flags
