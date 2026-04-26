from services.database import db


class SessionURL(db.Model):
    __tablename__ = "session_urls"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id"), nullable=False, index=True)
    url = db.Column(db.String(2048), nullable=False)

    session = db.relationship("Session", back_populates="urls")

    __table_args__ = (
        db.UniqueConstraint("session_id", "url", name="uq_session_url"),
    )


class BrowserSession(db.Model):
    __tablename__ = "browser_sessions"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id"), nullable=False, index=True)
    browser_session_id = db.Column(db.String(512), unique=True, nullable=False, index=True)

    session = db.relationship("Session", back_populates="browser_sessions")
