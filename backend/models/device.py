from services.database import db
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import func

# Maximum number of recent client IPs retained for proximity scoring.
MAX_RECENT_IPS = 20


class Device(db.Model):
    """A device identity cluster resolved via conservative hardware matching.

    New identities merge only when three hardware groups agree with exactly
    one immutable creation profile. Canonical fields retain that reading.
    """
    __tablename__ = "devices"

    id = db.Column(db.Integer, primary_key=True)

    # ── Identity signals ──
    cookie_id = db.Column(db.String(64), unique=True, nullable=True, index=True)
    device_bucket = db.Column(db.String(64), index=True)

    # ── Tier A — hardware-bound canonical fields ──
    platform = db.Column(db.String(512), default="")
    screen_width = db.Column(db.Float, default=0)
    screen_height = db.Column(db.Float, default=0)
    pixel_depth = db.Column(db.Float, default=0)
    color_depth = db.Column(db.Float, default=0)
    cpu_count = db.Column(db.Float, default=0)
    memory = db.Column(db.Float, default=0)
    speakers = db.Column(db.Float, default=0)
    microphones = db.Column(db.Float, default=0)
    webcams = db.Column(db.Float, default=0)
    webgl_vendor = db.Column(db.String(512), default="")
    webgl_renderer = db.Column(db.String(512), default="")
    hev_architecture = db.Column(db.String(512), default="")
    hev_bitness = db.Column(db.String(512), default="")
    hev_model = db.Column(db.String(512), default="")

    # ── Tier B — OS/browser-bound canonical fields (tie-breakers) ──
    hev_platform = db.Column(db.String(512), default="")
    hev_platform_version = db.Column(db.String(512), default="")
    timezone = db.Column(db.String(512), default="")
    language = db.Column(db.String(512), default="")
    audio_codec_hash = db.Column(db.String(512), default="")
    video_codec_hash = db.Column(db.String(512), default="")

    # ── Derived classification (recomputed on each resolution) ──
    is_mobile = db.Column(db.Boolean, default=False)
    device_type = db.Column(db.String(16), default="unknown")  # 'mobile' | 'workstation' | 'unknown'

    # ── Matching bookkeeping ──
    recent_ips = db.Column(JSONB, default=list)
    confidence = db.Column(db.Float, default=1.0)
    match_profile = db.Column(JSONB, default=dict)

    first_seen = db.Column(db.Float, default=0)
    last_seen = db.Column(db.Float, default=0)
    created_at = db.Column(db.DateTime, server_default=func.now())
    updated_at = db.Column(db.DateTime, server_default=func.now(), onupdate=func.now())

    sessions = db.relationship("Session", back_populates="device", lazy="dynamic")
    cookies = db.relationship("DeviceCookie", back_populates="device", lazy="dynamic", cascade="all, delete-orphan")


class DeviceCookie(db.Model):
    __tablename__ = "device_cookies"

    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.Integer, db.ForeignKey("devices.id"), nullable=False, index=True)
    cookie_id = db.Column(db.String(64), unique=True, nullable=False, index=True)
    match_method = db.Column(db.String(16), nullable=False, default="legacy")
    match_confidence = db.Column(db.Float, nullable=True)
    match_evidence = db.Column(JSONB, default=dict)
    first_seen = db.Column(db.Float, default=0)
    last_seen = db.Column(db.Float, default=0)
    created_at = db.Column(db.DateTime, server_default=func.now())
    updated_at = db.Column(db.DateTime, server_default=func.now(), onupdate=func.now())

    device = db.relationship("Device", back_populates="cookies")
