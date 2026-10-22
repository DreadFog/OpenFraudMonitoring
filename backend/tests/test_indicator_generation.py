import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from uuid import uuid4
from unittest.mock import patch

from flask import Flask
from sqlalchemy import create_engine, text

from models import Session, StixIPv4Addr, StixIPv6Addr, StixIndicator, StixRelationship, User
from routes.intel import intel_bp
from routes.settings import settings_bp
from routes.taxii_feeds import csv_feeds_bp
from services.database import db
from services.indicator_generation import ensure_ip_indicators, generate_session_indicators, parse_timestamp
from services.settings import (
    GLOBAL_DEFAULTS, INDICATOR_AUTOMATION_KEY, validate_indicator_automation,
)


class IndicatorPolicyTests(unittest.TestCase):
    def test_default_policy_and_strict_validation(self):
        policy = GLOBAL_DEFAULTS[INDICATOR_AUTOMATION_KEY]
        self.assertEqual(policy, {
            "enabled": True, "risk_threshold": 100,
            "lookback_minutes": 60, "validity_hours": 24,
        })
        self.assertEqual(validate_indicator_automation(policy), policy)
        for changes in (
            {"enabled": "true"}, {"risk_threshold": True}, {"risk_threshold": -1},
            {"risk_threshold": 101}, {"risk_threshold": 99.5},
            {"lookback_minutes": 0}, {"lookback_minutes": 10081},
            {"validity_hours": 0}, {"validity_hours": 8761}, {"extra": 1},
        ):
            with self.subTest(changes=changes):
                self.assertIsNone(validate_indicator_automation({**policy, **changes}))
        self.assertIsNone(validate_indicator_automation({}))


@unittest.skipUnless(os.environ.get("INDICATOR_TEST_DATABASE_URL"), "Requires isolated PostgreSQL")
class IndicatorGenerationDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = "indicator_test_" + uuid4().hex
        cls.engine = create_engine(os.environ["INDICATOR_TEST_DATABASE_URL"])
        with cls.engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{cls.schema}"'))
        cls.app = Flask(__name__)
        cls.app.config["SQLALCHEMY_DATABASE_URI"] = os.environ["INDICATOR_TEST_DATABASE_URL"]
        cls.app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "connect_args": {"options": f"-c search_path={cls.schema} -c statement_timeout=15000 -c lock_timeout=5000"},
        }
        db.init_app(cls.app)
        cls.app.register_blueprint(intel_bp)
        cls.app.register_blueprint(settings_bp)
        cls.app.register_blueprint(csv_feeds_bp)
        cls.context = cls.app.app_context()
        cls.context.push()
        db.create_all()

    @classmethod
    def tearDownClass(cls):
        db.session.remove()
        db.engine.dispose()
        cls.context.pop()
        with cls.engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{cls.schema}" CASCADE'))
        cls.engine.dispose()

    def setUp(self):
        db.session.remove()
        for table in reversed(db.metadata.sorted_tables):
            db.session.execute(table.delete())
        self.now = datetime(2026, 10, 22, 19, tzinfo=timezone.utc)
        self.policy = dict(GLOBAL_DEFAULTS[INDICATOR_AUTOMATION_KEY])
        self.client = self.app.test_client()
        self.admin = User(username="indicator-admin", role="admin", is_active=True)
        db.session.add(self.admin)
        db.session.flush()
        self.auth_user_id = self.admin.id
        db.session.commit()
        auth = patch("services.auth.decode_jwt", side_effect=lambda token: {"sub": self.auth_user_id})
        auth.start()
        self.addCleanup(auth.stop)
        self.headers = {"Authorization": "Bearer test-jwt"}

    def tearDown(self):
        db.session.rollback()

    def observable(self, version=4, value=None):
        value = value or ("192.0.2.1" if version == 4 else "2001:db8::1")
        sid = f"ipv{version}-addr--{uuid4()}"
        model = StixIPv4Addr if version == 4 else StixIPv6Addr
        row = model(stix_id=sid, value=value, raw={
            "type": f"ipv{version}-addr", "id": sid, "value": value,
        })
        db.session.add(row)
        db.session.flush()
        return row

    def visit(self, observable, score=100, ago=0, version=4):
        db.session.add(Session(
            fsid=str(uuid4()), risk_score=score,
            last_seen=(self.now - timedelta(minutes=ago)).timestamp() * 1000,
            ip_observable_type=f"ipv{version}-addr", ip_observable_id=observable.id,
        ))
        db.session.commit()

    def scan(self, now=None):
        with patch("services.indicator_generation.get_global_setting", return_value=self.policy):
            return generate_session_indicators(now=now or self.now)

    def test_creates_ipv4_ipv6_and_based_on_relationships_without_duplicates(self):
        for version in (4, 6):
            row = self.observable(version)
            self.visit(row, version=version)
        self.assertEqual(self.scan(), 2)
        self.assertEqual(StixIndicator.query.count(), 2)
        self.assertEqual(StixRelationship.query.filter_by(relationship_type="based-on").count(), 2)
        for row in StixIndicator.query.all():
            self.assertIn(row.name, ("192.0.2.1", "2001:db8::1"))
            self.assertEqual(row.raw["name"], row.name)
            self.assertEqual(parse_timestamp(row.raw["valid_until"]), self.now + timedelta(hours=24))
            self.assertEqual(row.value, row.raw["pattern"])
        self.assertEqual(self.scan(now=self.now + timedelta(minutes=1)), 0)
        self.assertEqual(StixIndicator.query.count(), 2)

    def test_threshold_and_recent_window_boundaries(self):
        for score, ago in ((100, 60), (99, 0), (100, 61), (100, -1)):
            row = self.observable(value=f"192.0.2.{StixIPv4Addr.query.count() + 1}")
            self.visit(row, score=score, ago=ago)
        self.assertEqual(self.scan(), 1)
        self.assertEqual(StixIndicator.query.one().name, "192.0.2.1")

    def test_disabled_and_custom_threshold(self):
        row = self.observable()
        self.visit(row, score=80)
        self.policy["enabled"] = False
        self.assertEqual(self.scan(), 0)
        self.policy.update(enabled=True, risk_threshold=80)
        self.assertEqual(self.scan(), 1)

    def test_new_activity_extends_without_shortening_or_rescan_accumulation(self):
        row = self.observable()
        self.visit(row)
        self.scan()
        indicator = StixIndicator.query.one()
        first_expiry = parse_timestamp(indicator.raw["valid_until"])
        self.assertEqual(self.scan(now=self.now + timedelta(minutes=30)), 0)
        self.assertEqual(parse_timestamp(indicator.raw["valid_until"]), first_expiry)
        later = self.now + timedelta(hours=1)
        Session.query.one().last_seen = later.timestamp() * 1000
        db.session.commit()
        self.assertEqual(self.scan(now=later), 1)
        self.assertEqual(parse_timestamp(indicator.raw["valid_until"]), later + timedelta(hours=24))
        self.policy["validity_hours"] = 12
        self.scan(now=later)
        self.assertEqual(parse_timestamp(indicator.raw["valid_until"]), later + timedelta(hours=24))

    def test_submillisecond_activity_does_not_trigger_repeated_updates(self):
        self.now = self.now.replace(microsecond=123456)
        row = self.observable()
        self.visit(row)
        self.assertEqual(self.scan(), 1)
        self.assertEqual(self.scan(now=self.now + timedelta(minutes=1)), 0)

    def test_renews_all_related_imported_indicators_and_reactivates_revoked(self):
        row = self.observable()
        self.visit(row)
        for index in range(2):
            sid = f"indicator--{uuid4()}"
            db.session.add(StixIndicator(
                stix_id=sid, value=f"imported-pattern-{index}", name=f"Imported {index}",
                source_connector_id=self.admin.id, revoked=True,
                raw={"type": "indicator", "id": sid, "revoked": True,
                     "valid_from": "2026-10-01T00:00:00Z", "valid_until": "2026-10-02T00:00:00Z"},
            ))
            db.session.add(StixRelationship(
                stix_id=f"relationship--{uuid4()}", relationship_type="based-on",
                source_ref=sid, target_ref=row.stix_id, raw={},
            ))
        db.session.commit()
        self.assertEqual(self.scan(), 2)
        self.assertEqual(StixIndicator.query.count(), 2)
        for indicator in StixIndicator.query.all():
            self.assertFalse(indicator.revoked)
            self.assertFalse(indicator.raw["revoked"])
            self.assertEqual(indicator.source_connector_id, self.admin.id)
            self.assertTrue(indicator.name.startswith("Imported"))
            self.assertEqual(parse_timestamp(indicator.raw["valid_until"]), self.now + timedelta(hours=24))

    def test_expiry_and_renewal_are_reflected_in_csv_exports(self):
        from models import TaxiiFeed
        row = self.observable()
        self.visit(row)
        self.scan()
        feed = TaxiiFeed(
            name="Blocklist", export_format="csv", is_public=True, is_active=True,
            auto_update=False, export_fields=["name"], include_headers=False,
            object_types=["indicator"], filters=[{"field": "revoked", "op": "eq", "value": "false"}],
        )
        db.session.add(feed)
        db.session.commit()
        with patch("services.indicator_revocation.datetime") as clock:
            clock.now.return_value = self.now
            response = self.client.get(f"/api/csv/{feed.uuid}/")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data.decode(), "192.0.2.1\r\n")
            clock.now.return_value = self.now + timedelta(hours=24)
            self.assertEqual(self.client.get(f"/api/csv/{feed.uuid}/").data, b"")
        self.visit(row)
        self.scan()
        self.assertFalse(StixIndicator.query.one().revoked)

    def test_manual_endpoint_auth_validation_and_idempotence(self):
        row = self.observable()
        db.session.commit()
        payload = {"type": "ipv4-addr", "stix_id": row.stix_id}
        self.assertEqual(self.client.post("/api/intel/indicators", json=payload).status_code, 401)
        user = User(username="reader", role="user", is_active=True)
        db.session.add(user)
        db.session.commit()
        self.auth_user_id = user.id
        self.assertEqual(self.client.post("/api/intel/indicators", headers=self.headers, json=payload).status_code, 403)
        self.auth_user_id = self.admin.id
        first = self.client.post("/api/intel/indicators", headers=self.headers, json=payload)
        self.assertEqual(first.status_code, 201, first.json)
        second = self.client.post("/api/intel/indicators", headers=self.headers, json=payload)
        self.assertEqual(second.status_code, 200, second.json)
        self.assertEqual(StixIndicator.query.count(), 1)
        self.assertEqual(first.json["indicators"][0]["stix_id"], second.json["indicators"][0]["stix_id"])
        for invalid in ([], {"type": "user-agent", "stix_id": row.stix_id}, {"type": "ipv4-addr"}):
            self.assertEqual(self.client.post("/api/intel/indicators", headers=self.headers, json=invalid).status_code, 400)
        self.assertEqual(self.client.post("/api/intel/indicators", headers=self.headers, json={
            "type": "ipv4-addr", "stix_id": "ipv4-addr--missing",
        }).status_code, 404)

    def test_invalid_observable_aborts_transaction(self):
        row = self.observable(value="not-an-ip")
        db.session.commit()
        with self.assertRaises(ValueError):
            ensure_ip_indicators("ipv4-addr", row.id, self.now, now=self.now)
        db.session.rollback()
        self.assertEqual(StixIndicator.query.count(), 0)

    def test_scan_failure_rolls_back_all_indicator_changes(self):
        good = self.observable()
        self.visit(good)
        bad = self.observable(value="not-an-ip")
        self.visit(bad)
        with self.assertRaises(ValueError):
            self.scan()
        self.assertEqual(StixIndicator.query.count(), 0)
        self.assertEqual(StixRelationship.query.count(), 0)

    def test_concurrent_creators_reuse_one_indicator(self):
        row = self.observable()
        row_id = row.id
        db.session.commit()
        barrier = Barrier(2)

        def create():
            with self.app.app_context():
                try:
                    barrier.wait(timeout=5)
                    rows, created, _ = ensure_ip_indicators("ipv4-addr", row_id, self.now, now=self.now)
                    sid = rows[0].stix_id
                    db.session.commit()
                    return sid, created
                finally:
                    db.session.remove()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: create(), range(2)))
        self.assertEqual(results[0][0], results[1][0])
        self.assertEqual(sum(created for _, created in results), 1)
        self.assertEqual(StixIndicator.query.count(), 1)
        self.assertEqual(StixRelationship.query.count(), 1)

    def test_expired_old_activity_does_not_reactivate_or_create(self):
        row = self.observable()
        self.visit(row, ago=120)
        self.policy.update(lookback_minutes=180, validity_hours=1)
        self.assertEqual(self.scan(), 0)
        self.assertEqual(StixIndicator.query.count(), 0)

    def as_reader(self):
        reader = User(username=f"reader-{uuid4().hex[:6]}", role="user", is_active=True)
        db.session.add(reader)
        db.session.commit()
        self.auth_user_id = reader.id

    def test_revoke_endpoint_auth_idempotence_and_feed_exclusion(self):
        row = self.observable()
        self.visit(row)
        self.scan()
        indicator = StixIndicator.query.one()
        url = f"/api/intel/indicators/{indicator.stix_id}/revoke"
        self.as_reader()
        self.assertEqual(self.client.post(url, headers=self.headers).status_code, 403)
        self.auth_user_id = self.admin.id
        first = self.client.post(url, headers=self.headers)
        self.assertEqual(first.status_code, 200, first.json)
        self.assertTrue(first.json["changed"])
        self.assertTrue(first.json["entity"]["revoked"])
        self.assertTrue(first.json["entity"]["platform"]["revoked_explicitly"])
        db.session.expire_all()
        indicator = StixIndicator.query.one()
        self.assertTrue(indicator.revoked)
        self.assertIs(indicator.raw["revoked"], True)
        revoked_at = parse_timestamp(indicator.raw["valid_until"])
        self.assertEqual(indicator.raw["valid_until"], indicator.raw["modified"])
        self.assertLessEqual(revoked_at, datetime.now(timezone.utc))
        self.assertGreater(revoked_at, datetime.now(timezone.utc) - timedelta(minutes=1))
        self.assertFalse(self.client.post(url, headers=self.headers).json["changed"])
        self.assertEqual(self.client.post("/api/intel/indicators/indicator--missing/revoke", headers=self.headers).status_code, 404)
        self.assertEqual(self.client.post(f"/api/intel/indicators/{row.stix_id}/revoke", headers=self.headers).status_code, 400)

    def test_revoke_sets_valid_until_to_revocation_time(self):
        from services.stix_editing import revoke_indicator
        row = self.observable()
        self.visit(row)
        self.scan()
        indicator = StixIndicator.query.one()
        revoked_at = self.now + timedelta(hours=2, microseconds=123456)
        self.assertTrue(revoke_indicator(indicator, now=revoked_at))
        self.assertEqual(indicator.raw["valid_until"], "2026-10-22T21:00:00.123Z")
        self.assertEqual(indicator.raw["valid_from"], "2026-10-22T19:00:00.000Z")
        self.assertFalse(revoke_indicator(indicator, now=revoked_at + timedelta(minutes=1)))
        # Explicitly revoked but still valid (e.g. via Edit): revoke ends validity.
        indicator.raw = {**indicator.raw, "valid_until": "2099-01-01T00:00:00.000Z"}
        self.assertTrue(revoke_indicator(indicator, now=revoked_at))
        self.assertEqual(indicator.raw["valid_until"], "2026-10-22T21:00:00.123Z")
        # A future valid_from is moved before valid_until to keep the object valid STIX.
        indicator.raw = {**indicator.raw, "revoked": False, "valid_from": "2030-01-01T00:00:00.000Z"}
        indicator.revoked = False
        self.assertTrue(revoke_indicator(indicator, now=revoked_at))
        self.assertEqual(indicator.raw["valid_from"], "2026-10-22T21:00:00.122Z")
        db.session.commit()

    def test_automation_only_reactivates_on_activity_after_revocation(self):
        from services.stix_editing import revoke_indicator
        row = self.observable()
        self.visit(row)
        self.scan()
        indicator = StixIndicator.query.one()
        revoke_indicator(indicator, now=self.now + timedelta(minutes=5))
        db.session.commit()
        self.assertEqual(self.scan(now=self.now + timedelta(minutes=10)), 0)
        self.assertTrue(StixIndicator.query.one().revoked)
        later = self.now + timedelta(minutes=20)
        Session.query.one().last_seen = later.timestamp() * 1000
        db.session.commit()
        self.assertEqual(self.scan(now=later), 1)
        indicator = StixIndicator.query.one()
        self.assertFalse(indicator.revoked)
        self.assertEqual(parse_timestamp(indicator.raw["valid_until"]), later + timedelta(hours=24))

    def test_manual_creation_overrides_recent_revocation(self):
        from services.stix_editing import revoke_indicator
        row = self.observable()
        db.session.commit()
        payload = {"type": "ipv4-addr", "stix_id": row.stix_id}
        self.client.post("/api/intel/indicators", headers=self.headers, json=payload)
        indicator = StixIndicator.query.one()
        revoke_indicator(indicator, now=datetime.now(timezone.utc) + timedelta(seconds=30))
        db.session.commit()
        response = self.client.post("/api/intel/indicators", headers=self.headers, json=payload)
        self.assertEqual(response.status_code, 200, response.json)
        db.session.expire_all()
        self.assertFalse(StixIndicator.query.one().revoked)

    def test_entity_edit_endpoint_updates_indicator_and_validates(self):
        row = self.observable()
        self.visit(row)
        self.scan()
        indicator = StixIndicator.query.one()
        url = f"/api/intel/entities/{indicator.stix_id}"
        original = dict(indicator.raw)
        edited = {**original, "name": "Renamed", "description": "Edited", "valid_until": "2099-01-01T00:00:00Z"}
        response = self.client.put(url, headers=self.headers, json={"stix_object": edited})
        self.assertEqual(response.status_code, 200, response.json)
        db.session.expire_all()
        indicator = StixIndicator.query.one()
        self.assertEqual((indicator.name, indicator.description), ("Renamed", "Edited"))
        self.assertEqual(indicator.raw["created"], original["created"])
        self.assertNotEqual(indicator.raw["modified"], original["modified"])
        self.assertFalse(indicator.revoked)
        expired = {**indicator.raw, "valid_until": "2026-10-01T00:00:00Z", "valid_from": "2026-09-01T00:00:00Z"}
        self.assertEqual(self.client.put(url, headers=self.headers, json={"stix_object": expired}).status_code, 200)
        db.session.expire_all()
        indicator = StixIndicator.query.one()
        self.assertTrue(indicator.revoked)
        self.assertIs(indicator.raw["revoked"], False)
        self.assertEqual(self.client.put(url, headers=self.headers, json={
            "stix_object": {**indicator.raw, "revoked": True}}).status_code, 200)
        db.session.expire_all()
        self.assertTrue(StixIndicator.query.one().raw["revoked"])
        for invalid in (
            {**indicator.raw, "id": f"indicator--{uuid4()}"},
            {**indicator.raw, "type": "malware"},
            {**indicator.raw, "valid_until": "not-a-date"},
            {**indicator.raw, "valid_until": indicator.raw["valid_from"]},
            {**indicator.raw, "revoked": "yes"},
            {k: v for k, v in indicator.raw.items() if k != "pattern"},
            [],
        ):
            with self.subTest(invalid=str(invalid)[:60]):
                self.assertEqual(self.client.put(url, headers=self.headers, json={"stix_object": invalid}).status_code, 400)
        self.assertEqual(self.client.put(url, headers=self.headers, json={}).status_code, 400)
        self.assertEqual(self.client.put("/api/intel/entities/indicator--missing", headers=self.headers,
                                         json={"stix_object": {}}).status_code, 404)
        self.as_reader()
        self.assertEqual(self.client.put(url, headers=self.headers, json={"stix_object": indicator.raw}).status_code, 403)

    def test_entity_edit_keeps_observable_identity(self):
        row = self.observable()
        db.session.commit()
        url = f"/api/intel/entities/{row.stix_id}"
        response = self.client.put(url, headers=self.headers, json={
            "stix_object": {**row.raw, "x_opencti_score": 90}})
        self.assertEqual(response.status_code, 200, response.json)
        db.session.expire_all()
        self.assertEqual(StixIPv4Addr.query.one().raw["x_opencti_score"], 90)
        self.assertEqual(StixIPv4Addr.query.one().value, "192.0.2.1")
        self.assertEqual(self.client.put(url, headers=self.headers, json={
            "stix_object": {**row.raw, "value": "192.0.2.2"}}).status_code, 400)
        db.session.expire_all()
        self.assertEqual(StixIPv4Addr.query.one().value, "192.0.2.1")

    def test_settings_endpoint_persists_and_requires_admin(self):
        policy = {**self.policy, "risk_threshold": 95}
        response = self.client.put("/api/settings/global", headers=self.headers, json={
            INDICATOR_AUTOMATION_KEY: policy,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["settings"][INDICATOR_AUTOMATION_KEY], policy)
        policy["risk_threshold"] = True
        self.assertEqual(self.client.put("/api/settings/global", headers=self.headers, json={
            INDICATOR_AUTOMATION_KEY: policy,
        }).status_code, 400)
        reader = User(username="reader", role="user", is_active=True)
        db.session.add(reader)
        db.session.commit()
        self.auth_user_id = reader.id
        self.assertEqual(self.client.put("/api/settings/global", headers=self.headers, json={
            INDICATOR_AUTOMATION_KEY: self.policy,
        }).status_code, 403)


if __name__ == "__main__":
    unittest.main()
