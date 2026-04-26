from services.database import db
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import func
from _generated_schema import SIGNAL_FIELDS, DETECTION_FIELDS, TOP_LEVEL_FIELDS


# ── Special signal values from FPScanner (non-data sentinels) ──
_SENTINEL_VALUES = {"ERROR", "INIT", "NA", "SKIPPED"}


def _is_valid(value):
    """Return True if the value is actual data (not an FPScanner sentinel)."""
    return value not in _SENTINEL_VALUES and value is not None


class Fingerprint(db.Model):
    __tablename__ = "fingerprints"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id"), nullable=False, index=True)
    timestamp = db.Column(db.Float, default=0)
    data = db.Column(JSONB, nullable=False)

    # ── Top-level fields ──
    fsid = db.Column(db.String(512), default="", index=True)
    fast_bot_detection = db.Column(db.Boolean, default=False)
    url = db.Column(db.String(2048), default="")

    created_at = db.Column(db.DateTime, server_default=func.now())

    session = db.relationship("Session", back_populates="fingerprints")

    @staticmethod
    def extract_fields(fp_data):
        """Extract denormalized fields from a decrypted FPScanner fingerprint."""
        result = {}

        # Top-level fields
        result["fsid"] = str(fp_data.get("fsid", "") or "")[:512]
        result["fast_bot_detection"] = bool(fp_data.get("fastBotDetection"))
        result["url"] = str(fp_data.get("url", "") or "")[:2048]

        # Signal fields — walk the nested signals dict
        signals = fp_data.get("signals", {})
        for field in SIGNAL_FIELDS:
            path = field["path"]
            col = field["column"]
            ftype = field["type"]

            # Walk nested path (e.g. "device.screenResolution.width")
            val = signals
            for key in path.split("."):
                if isinstance(val, dict):
                    val = val.get(key)
                else:
                    val = None
                    break

            if not _is_valid(val):
                val = field["default"]

            if ftype == "boolean":
                result[col] = bool(val) if val is not None else False
            elif ftype == "number":
                try:
                    result[col] = float(val) if val is not None else 0
                except (ValueError, TypeError):
                    result[col] = 0
            else:
                # string / string[]
                if isinstance(val, list):
                    result[col] = val
                else:
                    result[col] = str(val or "")[:512]

        # Detection fields
        details = fp_data.get("fastBotDetectionDetails", {})
        for field in DETECTION_FIELDS:
            name = field["name"]
            col = field["column"]
            det = details.get(name, {})
            result[col] = bool(det.get("detected")) if isinstance(det, dict) else False

        return result


# ── Dynamically add denormalized columns from the generated schema ──
# This runs at import time, adding columns to the Fingerprint model.

_SA_TYPE_MAP = {
    "db.Boolean": db.Boolean,
    "db.Float": db.Float,
    "db.String(512)": db.String(512),
    "JSONB": JSONB,
}

for _field in SIGNAL_FIELDS:
    _col_name = _field["column"]
    _sa_type_str = _field["sa_type"]
    _sa_type = _SA_TYPE_MAP.get(_sa_type_str, db.String(512))
    _default = _field["default"]
    setattr(Fingerprint, _col_name, db.Column(_sa_type, default=_default))

for _field in DETECTION_FIELDS:
    _col_name = _field["column"]
    setattr(Fingerprint, _col_name, db.Column(db.Boolean, default=False))
