import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask
from flask_cors import CORS

from models import Heartbeat, Session
from routes.heartbeat import heartbeat_bp
from routes.latency import latency_bp
from services.cors_origins import apply_cors_headers
from routes.collect import collect_bp
from routes.behavioral_event import behavioral_event_bp
from routes.settings import update_globals
from services.latency import capture_latency, normalize_latency
from services.settings import (
    GLOBAL_DEFAULTS, SERVER_LOCATION_KEY, SERVER_TIMEZONE_KEY,
    validate_server_location, validate_server_timezone,
)
from services.schema import get_schema, get_field_meta
from rules.engine import build_condition, build_session_query
from services.database import db
from sqlalchemy.dialects import postgresql


class LatencyProbeTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        CORS(self.app, resources={r"/api/*": {"supports_credentials": True}}, origins=[])
        self.app.register_blueprint(latency_bp)
        self.app.after_request(apply_cors_headers)

    def test_probe_is_empty_uncached_public_and_skips_database_cors(self):
        with patch("services.cors_origins.dynamic_origin", side_effect=AssertionError("Database CORS lookup")) as origins:
            response = self.app.test_client().get("/api/latency", headers={"Origin": "https://other.test"})
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.data, b"")
        self.assertEqual(response.headers["X-OFM-Latency-Probe"], "1")
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertEqual(response.headers["Access-Control-Allow-Origin"], "*")
        self.assertNotIn("Access-Control-Allow-Credentials", response.headers)
        self.assertIn("X-OFM-Latency-Probe", response.headers["Access-Control-Expose-Headers"])
        origins.assert_not_called()

    def test_regular_routes_keep_existing_cors_validation(self):
        self.app.add_url_rule("/other", view_func=lambda: "ok")
        with patch("services.cors_origins.dynamic_origin", return_value="https://allowed.test") as origins:
            response = self.app.test_client().get("/other", headers={"Origin": "https://allowed.test"})
        origins.assert_called_once_with("https://allowed.test")
        self.assertEqual(response.headers["Access-Control-Allow-Origin"], "https://allowed.test")
        self.assertEqual(response.headers["Access-Control-Allow-Credentials"], "true")


class LatencyTests(unittest.TestCase):
    def setUp(self):
        self.sample = {
            "round_trip_ms": 42.125,
            "measured_at": 1791200000000,
            "request_path": "/api/initial",
            "client_timezone": "Europe/Paris",
            "client_utc_offset_minutes": 120,
        }

    def test_server_setting_defaults_and_validation(self):
        self.assertEqual(GLOBAL_DEFAULTS[SERVER_TIMEZONE_KEY], "UTC")
        self.assertEqual(validate_server_timezone(" Europe/Paris "), "Europe/Paris")
        for timezone in ("", "not/a-timezone", "../UTC", None, 123):
            self.assertIsNone(validate_server_timezone(timezone))
        self.assertEqual(validate_server_location({"name": " Paris ", "latitude": 48.85, "longitude": 2.35}),
                         {"name": "Paris", "latitude": 48.85, "longitude": 2.35})
        for location in ({"latitude": 1}, {"latitude": 91, "longitude": 0},
                         {"latitude": 0, "longitude": 181}, {"latitude": True, "longitude": 0},
                         {"latitude": float("nan"), "longitude": 0},
                         {"latitude": 10 ** 400, "longitude": 0}, {"unknown": "value"}, "Paris"):
            self.assertIsNone(validate_server_location(location))

    def test_latency_filter_schema_uses_numeric_operators_and_milliseconds(self):
        field = next(field for field in get_schema() if field["name"] == "latency_ms")
        self.assertEqual(field["label"], "Session Latency (ms)")
        self.assertEqual(field["type"], "number")
        self.assertEqual({operator["name"] for operator in field["operators"]},
                         {"eq", "neq", "gt", "gte", "lt", "lte"})
        self.assertEqual(get_field_meta("latency_ms")["model"], "Session")

    def test_latency_value_uses_latest_sample_and_preserves_missing_values(self):
        session = Session(fsid="test")
        self.assertIsNone(session.latency_ms)
        session.latency = {"round_trip_ms": 42.125}
        self.assertEqual(session.latency_ms, 42.125)
        session.latency = {"round_trip_ms": 0}
        self.assertEqual(session.latency_ms, 0)
        session.latency = {}
        self.assertIsNone(session.latency_ms)

    def test_latency_filters_cast_json_to_numeric_values(self):
        metadata = get_field_meta("latency_ms")
        for operator in ("eq", "neq", "gt", "gte", "lt", "lte"):
            with self.subTest(operator=operator):
                condition = build_condition(metadata, operator, "42.125")
                compiled = condition.compile(dialect=postgresql.dialect())
                self.assertIn("CAST", str(compiled))
                self.assertIn("round_trip_ms", compiled.params.values())
                self.assertIn(42.125, compiled.params.values())
        self.assertIsNone(build_condition(metadata, "gt", "not-a-number"))

    def test_invalid_timezone_does_not_partially_save_location(self):
        app = Flask(__name__)
        with app.test_request_context(json={SERVER_LOCATION_KEY: {"name": "Paris"}, SERVER_TIMEZONE_KEY: "invalid"}), \
                patch("routes.settings.set_global_setting") as save:
            response, status = update_globals.__wrapped__.__wrapped__()
        self.assertEqual(status, 400)
        save.assert_not_called()

    def test_context_is_server_controlled_and_sample_is_client_reported(self):
        settings = {SERVER_LOCATION_KEY: {"name": "Paris", "latitude": 48.85, "longitude": 2.35},
                    SERVER_TIMEZONE_KEY: "Europe/Paris"}
        with patch("services.latency.get_global_setting", side_effect=settings.get):
            sample = normalize_latency({**self.sample, "server": {"timezone": "forged"}})
        self.assertEqual(sample["round_trip_ms"], 42.125)
        self.assertEqual(sample["source"], "client_reported")
        self.assertEqual(sample["server"]["timezone"], "Europe/Paris")
        self.assertEqual(sample["server"]["location"]["latitude"], 48.85)

    def test_invalid_samples_are_ignored_without_reading_settings(self):
        invalid = [None, [], {}, {**self.sample, "round_trip_ms": -1},
                   {**self.sample, "round_trip_ms": True}, {**self.sample, "round_trip_ms": float("nan")},
                   {**self.sample, "round_trip_ms": 60001}, {**self.sample, "measured_at": float("inf")},
                   {**self.sample, "round_trip_ms": 10 ** 400}, {**self.sample, "measured_at": 10 ** 400},
                   {**self.sample, "request_path": "https://other.test"},
                   {**self.sample, "client_utc_offset_minutes": False}]
        with patch("services.latency.get_global_setting") as settings:
            for sample in invalid:
                self.assertIsNone(normalize_latency(sample))
            settings.assert_not_called()

    def test_probe_measurements_are_distinguished_from_legacy_ingestion_timings(self):
        with patch("services.latency.get_global_setting", side_effect=GLOBAL_DEFAULTS.get):
            probe = normalize_latency({**self.sample, "request_path": "/api/latency", "measurement": "lightweight_probe"})
            legacy = normalize_latency(self.sample)
            forged = normalize_latency({**self.sample, "measurement": "lightweight_probe"})
        self.assertEqual(probe["measurement"], "lightweight_probe")
        self.assertEqual(legacy["measurement"], "fetch_response_headers")
        self.assertEqual(forged["measurement"], "fetch_response_headers")

    def test_capture_updates_latest_sample_but_absence_does_not_erase_it(self):
        session = SimpleNamespace(latency=None)
        with patch("services.latency.get_global_setting", side_effect=GLOBAL_DEFAULTS.get):
            sample = capture_latency(session, {"latency": self.sample})
        self.assertIs(session.latency, sample)
        self.assertIsNone(capture_latency(session, {}))
        self.assertIs(session.latency, sample)

    def test_heartbeat_stores_and_serializes_latency(self):
        app = Flask(__name__)
        app.register_blueprint(heartbeat_bp)
        session = SimpleNamespace(id=1, fsid="fingerprint", latency=None)
        records = []
        with patch("routes.heartbeat.Session") as model, \
                patch("routes.heartbeat.db") as database, \
                patch("routes.heartbeat.auth_cookie_present", return_value=False), \
                patch("routes.heartbeat.add_session_domain"), \
                patch("routes.heartbeat.enqueue_event"), \
                patch("services.latency.get_global_setting", side_effect=GLOBAL_DEFAULTS.get):
            model.query.filter_by.return_value.first.return_value = session
            database.session.add.side_effect = records.append
            response = app.test_client().post("/api/heartbeat", json={
                "visit_id": "00000000-0000-4000-8000-000000000001",
                "timestamp": 1791200001000, "extensions": {"latency": self.sample},
            })
        self.assertEqual(response.status_code, 200)
        heartbeat = next(record for record in records if isinstance(record, Heartbeat))
        self.assertEqual(heartbeat.to_summary()["latency"]["round_trip_ms"], 42.125)
        self.assertEqual(session.latency["server"]["timezone"], "UTC")
        self.assertIn("latency", Session.__table__.c)

    def test_initial_fingerprint_stores_normalized_extension(self):
        app = Flask(__name__)
        app.config["OFM_SAVE_PRIVATE_IP"] = True
        app.register_blueprint(collect_bp)
        session = SimpleNamespace(id=1, fsid="fingerprint", latency=None)
        with patch("routes.collect.get_or_create_visit", return_value=session), \
                patch("routes.collect.Fingerprint") as fingerprint, \
                patch("routes.collect.SessionURL"), \
                patch("routes.collect.resolve_device", return_value=(SimpleNamespace(id=1), 1)), \
                patch("routes.collect.get_or_create_ip", return_value=None), \
                patch("routes.collect.get_or_create_user_agent", return_value=None), \
                patch("routes.collect.auth_cookie_present", return_value=False), \
                patch("routes.collect.add_session_domain"), \
                patch("routes.collect.enqueue_event"), \
                patch("routes.collect.db"), \
                patch("services.latency.get_global_setting", side_effect=GLOBAL_DEFAULTS.get):
            fingerprint.extract_fields.return_value = {"fsid": "fingerprint"}
            response = app.test_client().post("/api/initial", json={
                "visit_id": "00000000-0000-4000-8000-000000000001", "fsid": "fingerprint",
                "time": 1791200001000, "extensions": {"latency": self.sample},
            })
        self.assertEqual(response.status_code, 200)
        stored = fingerprint.call_args.kwargs["data"]["_extensions"]["latency"]
        self.assertEqual(stored["server"]["timezone"], "UTC")
        self.assertEqual(session.latency["round_trip_ms"], 42.125)

    def test_direct_behavior_updates_latest_latency(self):
        app = Flask(__name__)
        app.register_blueprint(behavioral_event_bp)
        session = SimpleNamespace(id=1, fsid="fingerprint", latency=None)
        with patch("routes.behavioral_event.Session") as model, \
                patch("routes.behavioral_event.db"), \
                patch("routes.behavioral_event.auth_cookie_present", return_value=False), \
                patch("routes.behavioral_event.add_session_domain"), \
                patch("routes.behavioral_event.enqueue_event"), \
                patch("services.latency.get_global_setting", side_effect=GLOBAL_DEFAULTS.get):
            model.query.filter_by.return_value.first.return_value = session
            response = app.test_client().post("/api/behavioral_event", json={
                "visit_id": "00000000-0000-4000-8000-000000000001", "timestamp": 1791200001000,
                "event_type": "button_click", "data": {}, "extensions": {"latency": self.sample},
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(session.latency["round_trip_ms"], 42.125)


@unittest.skipUnless(os.environ.get("LATENCY_TEST_DATABASE_URL"), "Requires isolated PostgreSQL")
class LatencyFilterDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Flask(__name__)
        cls.app.config["SQLALCHEMY_DATABASE_URI"] = os.environ["LATENCY_TEST_DATABASE_URL"]
        cls.app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "connect_args": {"options": "-c statement_timeout=15000 -c lock_timeout=5000"},
        }
        db.init_app(cls.app)
        cls.context = cls.app.app_context()
        cls.context.push()
        db.create_all()

    @classmethod
    def tearDownClass(cls):
        db.session.remove()
        db.drop_all()
        cls.context.pop()

    def test_numeric_comparisons_missing_samples_and_combined_filters(self):
        for name, sample, risk in (
            ("missing", None, 0), ("empty", {}, 0),
            ("zero", {"round_trip_ms": 0}, 0),
            ("fast", {"round_trip_ms": 9.5}, 10),
            ("medium", {"round_trip_ms": 42.125}, 50),
            ("slow", {"round_trip_ms": 100}, 80),
        ):
            db.session.add(Session(fsid=name, latency=sample, risk_score=risk))
        db.session.commit()
        expected = {
            "eq": {"medium"}, "neq": {"zero", "fast", "slow"},
            "gt": {"slow"}, "gte": {"medium", "slow"},
            "lt": {"zero", "fast"}, "lte": {"zero", "fast", "medium"},
        }
        for operator, names in expected.items():
            with self.subTest(operator=operator):
                query = build_session_query([{"field": "latency_ms", "op": operator, "value": "42.125"}])
                self.assertEqual({session.fsid for session in query.all()}, names)
        latency_filter = {"field": "latency_ms", "op": "gt", "value": "10"}
        risk_filter = {"field": "risk_score", "op": "gte", "value": "70"}
        self.assertEqual({session.fsid for session in build_session_query([latency_filter, risk_filter]).all()}, {"slow"})
        latency_filter["op"] = "lt"
        self.assertEqual({session.fsid for session in build_session_query([latency_filter, risk_filter], logic="OR").all()},
                         {"zero", "fast", "slow"})
        Session.query.filter_by(fsid="fast").first().latency = {"round_trip_ms": 80}
        db.session.commit()
        query = build_session_query([{"field": "latency_ms", "op": "gt", "value": "50"}])
        self.assertEqual({session.fsid for session in query.all()}, {"fast", "slow"})


if __name__ == "__main__":
    unittest.main()