from services.database import db
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import func


class Fingerprint(db.Model):
    __tablename__ = "fingerprints"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id"), nullable=False, index=True)
    timestamp = db.Column(db.Float, default=0)
    data = db.Column(JSONB, nullable=False)

    # ── Denormalized columns for efficient filtering / indexing ──
    user_agent = db.Column(db.String(512), default="")
    platform = db.Column(db.String(64), default="")
    language = db.Column(db.String(32), default="")
    operating_system = db.Column(db.String(64), default="")
    hardware_concurrency = db.Column(db.Integer, default=0)
    device_memory = db.Column(db.Float, default=0)
    is_mobile = db.Column(db.Boolean, default=False)
    is_workstation = db.Column(db.Boolean, default=False)
    screen_width = db.Column(db.Integer, default=0)
    screen_height = db.Column(db.Integer, default=0)
    color_depth = db.Column(db.Integer, default=0)
    timezone = db.Column(db.String(64), default="")
    webgl_vendor = db.Column(db.String(256), default="")
    webgl_renderer = db.Column(db.String(256), default="")
    public_ip = db.Column(db.String(45), default="")
    has_webdriver = db.Column(db.Boolean, default=False)
    has_phantom = db.Column(db.Boolean, default=False)
    has_nightmare = db.Column(db.Boolean, default=False)
    has_puppeteer = db.Column(db.Boolean, default=False)
    has_selenium = db.Column(db.Boolean, default=False)
    has_chromedriver = db.Column(db.Boolean, default=False)
    has_empty_languages = db.Column(db.Boolean, default=False)
    has_no_plugins = db.Column(db.Boolean, default=False)
    has_native_spoofed = db.Column(db.Boolean, default=False)
    has_canvas = db.Column(db.Boolean, default=False)
    has_audio = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, server_default=func.now())

    session = db.relationship("Session", back_populates="fingerprints")

    @staticmethod
    def extract_fields(fp_data):
        """Extract denormalized fields from raw fingerprint JSON."""
        nav = fp_data.get("navigator", {})
        scr = fp_data.get("screen", {})
        gl = fp_data.get("webgl", {})
        tz = fp_data.get("timezone", {})
        bot = fp_data.get("botSignals", {})
        pub = fp_data.get("publicIP", {})
        return {
            "user_agent": (nav.get("userAgent") or "")[:512],
            "platform": (nav.get("platform") or "")[:64],
            "language": (nav.get("language") or "")[:32],
            "operating_system": (fp_data.get("operatingSystem") or "")[:64],
            "hardware_concurrency": nav.get("hardwareConcurrency") or 0,
            "device_memory": nav.get("deviceMemory") or 0,
            "is_mobile": bool(nav.get("isMobile")),
            "is_workstation": bool(nav.get("isWorkstation")),
            "screen_width": scr.get("width") or 0,
            "screen_height": scr.get("height") or 0,
            "color_depth": scr.get("colorDepth") or 0,
            "timezone": (tz.get("timezone") or "")[:64],
            "webgl_vendor": (gl.get("vendor") or "")[:256],
            "webgl_renderer": (gl.get("renderer") or "")[:256],
            "public_ip": (pub.get("ip") or "")[:45],
            "has_webdriver": bool(bot.get("webdriver")),
            "has_phantom": bool(bot.get("phantom")),
            "has_nightmare": bool(bot.get("nightmare")),
            "has_puppeteer": bool(bot.get("puppeteer")),
            "has_selenium": bool(bot.get("selenium")),
            "has_chromedriver": bool(bot.get("cdcProps")),
            "has_empty_languages": bool(bot.get("languages_empty")),
            "has_no_plugins": bool(bot.get("noPlugins")),
            "has_native_spoofed": bot.get("nativeCheckPassed") is False,
            "has_canvas": bool(fp_data.get("canvas", {}).get("dataURL")),
            "has_audio": bool(fp_data.get("audio")),
        }
