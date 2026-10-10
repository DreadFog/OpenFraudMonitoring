import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from flask import Flask, g

from models import (
    Session, Device, DeviceCookie, Fingerprint, Heartbeat, SessionURL,
    BrowserSession, Rule, RuleMatch, TYPED_EVENT_MODELS, User,
    StixIPv4Addr, StixIPv6Addr, StixUserAgent, StixAutonomousSystem,
    StixRelationship,
)
from routes.settings import settings_bp, update_globals
from services.database import db
from services.retention import purge_inactive_data, retention_cutoff
from services.settings import DATA_RETENTION_MONTHS_KEY, INDICATOR_REVOCATION_DAYS_KEY, GLOBAL_DEFAULTS, validate_retention_months


class RetentionSettingTests(unittest.TestCase):
    def test_revocation_setting_defaults_and_validates_positive_whole_days(self):
        app = Flask(__name__)
        self.assertEqual(GLOBAL_DEFAULTS[INDICATOR_REVOCATION_DAYS_KEY], 7)
        with app.test_request_context(json={INDICATOR_REVOCATION_DAYS_KEY: 14}), \
             patch("routes.settings.set_global_setting") as save, \
             patch("routes.settings.get_global_settings", return_value={}), \
             patch("services.indicator_revocation.refresh_indicator_revocation") as refresh:
            g.current_user = type("Admin", (), {"role": "admin"})()
            _, status = update_globals.__wrapped__()
            self.assertEqual(status, 200)
            save.assert_called_once_with(INDICATOR_REVOCATION_DAYS_KEY, 14)
            refresh.assert_called_once()

        for value in (True, False, 0, -1, 1.5, "7", None):
            with app.test_request_context(json={INDICATOR_REVOCATION_DAYS_KEY: value}), \
                 patch("routes.settings.set_global_setting") as save:
                g.current_user = type("Admin", (), {"role": "admin"})()
                _, status = update_globals.__wrapped__()
                self.assertEqual(status, 400, value)
                save.assert_not_called()

    def test_revocation_setting_requires_admin(self):
        app = Flask(__name__)
        with app.test_request_context(json={INDICATOR_REVOCATION_DAYS_KEY: 14}), \
             patch("routes.settings.set_global_setting") as save:
            g.current_user = type("User", (), {"role": "user"})()
            _, status = update_globals.__wrapped__()
            self.assertEqual(status, 403)
            save.assert_not_called()

    def test_requires_positive_integer(self):
        self.assertEqual(validate_retention_months(6), 6)
        for value in (True, False, 0, -1, 1.5, "6", None, {}):
            self.assertIsNone(validate_retention_months(value))

    def test_calendar_month_cutoff(self):
        self.assertEqual(
            retention_cutoff(datetime(2024, 8, 31, tzinfo=timezone.utc), 6),
            datetime(2024, 2, 29, tzinfo=timezone.utc),
        )
        self.assertEqual(
            retention_cutoff(datetime(2025, 3, 31, tzinfo=timezone.utc), 1),
            datetime(2025, 2, 28, tzinfo=timezone.utc),
        )


@unittest.skipUnless(os.environ.get("RETENTION_TEST_DATABASE_URL"), "Requires isolated PostgreSQL")
class RetentionDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Flask(__name__)
        cls.app.config["SQLALCHEMY_DATABASE_URI"] = os.environ["RETENTION_TEST_DATABASE_URL"]
        cls.app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "connect_args": {"options": "-c statement_timeout=15000 -c lock_timeout=5000"},
        }
        db.init_app(cls.app)
        cls.app.register_blueprint(settings_bp)
        cls.context = cls.app.app_context()
        cls.context.push()

    @classmethod
    def tearDownClass(cls):
        db.session.remove()
        db.drop_all()
        cls.context.pop()

    def setUp(self):
        db.session.remove()
        db.drop_all()
        db.create_all()
        self.now = datetime(2026, 10, 5, tzinfo=timezone.utc)
        self.cutoff = datetime(2026, 4, 5, tzinfo=timezone.utc)
        self.cutoff_ms = self.cutoff.timestamp() * 1000

    def tearDown(self):
        db.session.remove()

    def visit(self, seen, **kwargs):
        session = Session(fsid="fingerprint", last_seen=seen, **kwargs)
        db.session.add(session)
        db.session.flush()
        return session

    def entity(self, model, name, old=True):
        entity = model(stix_id=f"{model.__tablename__}--{name}", value=name, raw={},
                       created_at_platform=datetime(2020, 1, 1) if old else self.now)
        db.session.add(entity)
        db.session.flush()
        return entity

    def relationship(self, source, target):
        db.session.add(StixRelationship(
            stix_id=f"relationship--{source.stix_id}-{target.stix_id}",
            source_ref=source.stix_id, target_ref=target.stix_id,
            relationship_type="belongs-to", raw={},
        ))

    def test_deletes_all_children_and_device_aliases(self):
        device = Device(cookie_id="old", last_seen=self.now.timestamp() * 1000)
        db.session.add(device)
        db.session.flush()
        db.session.add(DeviceCookie(device_id=device.id, cookie_id="alias"))
        session = self.visit(self.cutoff_ms - 1, device_id=device.id)
        db.session.add(Fingerprint(session_id=session.id, data={}))
        db.session.add(Heartbeat(session_id=session.id))
        db.session.add(SessionURL(session_id=session.id, url="https://example.test"))
        db.session.add(BrowserSession(session_id=session.id, browser_session_id="browser"))
        for model in TYPED_EVENT_MODELS.values():
            db.session.add(model(session_id=session.id))
        rule = Rule(name="retention-test", conditions=[])
        db.session.add(rule)
        db.session.flush()
        db.session.add(RuleMatch(rule_id=rule.id, session_id=session.id))
        db.session.commit()

        counts = purge_inactive_data(self.now, batch_size=1)

        self.assertEqual(counts["sessions"], 1)
        self.assertEqual(counts["devices"], 1)
        for model in (Session, Device, DeviceCookie, Fingerprint, Heartbeat, SessionURL,
                      BrowserSession, RuleMatch, *TYPED_EVENT_MODELS.values()):
            self.assertEqual(model.query.count(), 0, model.__name__)
        self.assertEqual(Rule.query.count(), 1)

    def test_shared_device_and_observables_follow_sessions_not_creation(self):
        device = Device(last_seen=1, recent_ips=["expired", "active"])
        db.session.add(device)
        db.session.flush()
        ip = self.entity(StixIPv4Addr, "192.0.2.1")
        ua = self.entity(StixUserAgent, "browser")
        for seen, client_ip in ((self.cutoff_ms - 1, "expired"), (self.cutoff_ms, "active")):
            self.visit(seen, device_id=device.id, client_ip=client_ip,
                       ip_observable_type="ipv4-addr", ip_observable_id=ip.id,
                       user_agent_observable_id=ua.id)
        db.session.commit()

        purge_inactive_data(self.now)

        self.assertEqual(Session.query.count(), 1)
        self.assertEqual(Device.query.first().last_seen, self.cutoff_ms)
        self.assertEqual(Device.query.first().recent_ips, ["active"])
        self.assertEqual(StixIPv4Addr.query.count(), 1)
        self.assertEqual(StixUserAgent.query.count(), 1)
        Session.query.first().last_seen -= 1
        db.session.commit()
        purge_inactive_data(self.now)
        self.assertEqual(Device.query.count(), 0)
        self.assertEqual(StixIPv4Addr.query.count(), 0)
        self.assertEqual(StixUserAgent.query.count(), 0)

    def test_shared_enrichment_does_not_keep_expired_ip(self):
        old_ip = self.entity(StixIPv4Addr, "old", old=False)
        active_ip = self.entity(StixIPv6Addr, "active")
        shared_system = self.entity(StixAutonomousSystem, "AS1")
        private_system = self.entity(StixAutonomousSystem, "AS2", old=False)
        self.relationship(old_ip, shared_system)
        self.relationship(active_ip, shared_system)
        self.relationship(old_ip, private_system)
        self.visit(self.cutoff_ms - 1, ip_observable_type="ipv4-addr", ip_observable_id=old_ip.id)
        self.visit(self.cutoff_ms, ip_observable_type="ipv6-addr", ip_observable_id=active_ip.id)
        db.session.commit()

        purge_inactive_data(self.now)

        self.assertEqual(StixIPv4Addr.query.count(), 0)
        self.assertEqual(StixIPv6Addr.query.count(), 1)
        self.assertEqual([entity.value for entity in StixAutonomousSystem.query.all()], ["AS1"])
        self.assertEqual(StixRelationship.query.count(), 1)

    def test_standalone_intelligence_uses_refresh_or_creation(self):
        self.entity(StixUserAgent, "stale")
        self.entity(StixUserAgent, "new", old=False)
        refreshed = self.entity(StixIPv4Addr, "refreshed")
        refreshed.last_refreshed_at = self.now
        db.session.commit()
        purge_inactive_data(self.now)
        self.assertEqual([entity.value for entity in StixUserAgent.query.all()], ["new"])
        self.assertEqual(StixIPv4Addr.query.count(), 1)

    def test_admin_setting_changes_next_sweep(self):
        user = User(username="admin", role="admin", is_active=True)
        db.session.add(user)
        self.visit(datetime(2026, 6, 1, tzinfo=timezone.utc).timestamp() * 1000)
        db.session.commit()
        purge_inactive_data(self.now)
        self.assertEqual(Session.query.count(), 1)
        with patch("services.auth.decode_jwt", return_value={"sub": user.id}):
            response = self.app.test_client().put("/api/settings/global",
                headers={"Authorization": "Bearer test"}, json={DATA_RETENTION_MONTHS_KEY: 3})
        self.assertEqual(response.status_code, 200)
        purge_inactive_data(self.now)
        self.assertEqual(Session.query.count(), 0)

    def test_non_admin_cannot_change_retention(self):
        user = User(username="user", role="user", is_active=True)
        db.session.add(user)
        db.session.commit()
        with patch("services.auth.decode_jwt", return_value={"sub": user.id}):
            response = self.app.test_client().put("/api/settings/global",
                headers={"Authorization": "Bearer test"}, json={DATA_RETENTION_MONTHS_KEY: 3})
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()