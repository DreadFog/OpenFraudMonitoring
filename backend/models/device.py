from services.database import db
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import func

# Maximum number of recent client IPs retained for proximity scoring.
MAX_RECENT_IPS = 20


class Device(db.Model):
    """A device identity cluster, resolved via fuzzy matching across sessions.

    Unlike `Session.fsid` (exact, volatile — see fpscanner canvas noise), a
    Device groups sessions whose hardware/OS signals score above a match
    threshold. Canonical fields are updated most-recent-write-wins.
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

    first_seen = db.Column(db.Float, default=0)
    last_seen = db.Column(db.Float, default=0)
    created_at = db.Column(db.DateTime, server_default=func.now())
    updated_at = db.Column(db.DateTime, server_default=func.now(), onupdate=func.now())

    sessions = db.relationship("Session", back_populates="device", lazy="dynamic")
