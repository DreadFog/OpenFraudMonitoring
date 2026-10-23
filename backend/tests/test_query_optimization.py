"""Query-count and result regressions; requires a disposable PostgreSQL database."""

import os
import unittest
from contextlib import contextmanager

from flask import Flask
from sqlalchemy import event, null, select

from models import Fingerprint, Heartbeat, Session
from models.associations import BrowserSession, SessionURL
from models.behavioral_event import TYPED_EVENT_MODELS
from models.device import Device
from routes.devices import get_device_detail, get_devices
from routes.overview import _window_counts
from routes.sessions import _fetch_typed_events, get_sessions
from routes.stats import get_stats
from services.bot_detection import bot_flag_expression, has_bot_flag
from services.database import db


@contextmanager
def queries():
    statements = []

    def record(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(db.engine, "before_cursor_execute", record)
    try:
        yield statements
    finally:
        event.remove(db.engine, "before_cursor_execute", record)


@unittest.skipUnless(os.getenv("QUERY_TEST_DATABASE_URL"), "Requires disposable QUERY_TEST_DATABASE_URL")
class QueryOptimizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Flask(__name__)
        cls.app.config.update(
            TESTING=True, SQLALCHEMY_DATABASE_URI=os.environ["QUERY_TEST_DATABASE_URL"],
        )
        db.init_app(cls.app)
        cls.app.add_url_rule("/sessions", view_func=get_sessions.__wrapped__)
        cls.app.add_url_rule("/devices", view_func=get_devices.__wrapped__)
        cls.app.add_url_rule("/devices/<int:device_id>", view_func=get_device_detail.__wrapped__)
        cls.app.add_url_rule("/stats", view_func=get_stats.__wrapped__)
        with cls.app.app_context():
            db.create_all()

    @classmethod
    def tearDownClass(cls):
        with cls.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()

    def setUp(self):
        self.context = self.app.app_context()
        self.context.push()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.rollback()
        db.session.remove()
        self.context.pop()

    def session(self, **kwargs):
        row = Session(fsid="shared", **kwargs)
        db.session.add(row)
        db.session.flush()
        return row

    def test_session_listing_constant_queries_and_previews(self):
        rows = [self.session(last_seen=i, flags=["Bot"]) for i in range(26)]
        newest = rows[-1]
        for timestamp, agent in ((1, "old"), (2, "latest")):
            db.session.add(Fingerprint(
                session_id=newest.id, timestamp=timestamp,
                data={"signals": {"browser": {"userAgent": agent}}, "fastBotDetection": True},
            ))
        for i in range(5):
            db.session.add(SessionURL(session_id=newest.id, url=f"url-{i}"))
        for i in range(3):
            db.session.add(BrowserSession(session_id=newest.id, browser_session_id=f"browser-{i}"))
        db.session.add_all([Heartbeat(session_id=newest.id, timestamp=i) for i in range(2)])
        for model in TYPED_EVENT_MODELS.values():
            db.session.add(model(session_id=newest.id, timestamp=10))
        db.session.flush()
        with queries() as small:
            first = self.client.get("/sessions?per_page=10").get_json()
        with queries() as large:
            second = self.client.get("/sessions?per_page=25").get_json()
        self.assertEqual(len(small), len(large))
        self.assertLessEqual(len(large), 12)
        self.assertEqual((first["total"], len(first["sessions"])), (26, 10))
        summary = second["sessions"][0]
        self.assertEqual(summary["user_agent"], "latest")
        self.assertTrue(summary["fast_bot_detection"])
        self.assertEqual(summary["urls"], ["url-0", "url-1", "url-2"])
        self.assertEqual(summary["urls_count"], 5)
        self.assertEqual(summary["session_ids"], ["browser-0", "browser-1"])
        self.assertEqual(summary["heartbeats"], 2)
        self.assertEqual(summary["behavioral_events"], len(TYPED_EVENT_MODELS))
        self.assertEqual(second["sessions"][1]["user_agent"], "unknown")
        self.assertEqual(second["sessions"][1]["urls_count"], 0)
        self.assertEqual(self.client.get('/sessions?filters=[{"field":"fsid","op":"eq","value":"missing"}]')
                         .get_json()["total"], 0)

    def test_events_limit_before_loading_and_merge_all_types(self):
        session = self.session()
        for kind, model in enumerate(TYPED_EVENT_MODELS.values()):
            db.session.add_all([
                model(session_id=session.id, timestamp=i * 10 + kind)
                for i in range(20)
            ])
        db.session.flush()
        loaded = []

        def on_load(session, instance):
            loaded.append(instance)

        event.listen(db.session(), "loaded_as_persistent", on_load)
        try:
            with queries() as statements:
                result = _fetch_typed_events(session.id, limit=7)
        finally:
            event.remove(db.session(), "loaded_as_persistent", on_load)
        self.assertEqual(len(result), 7)
        self.assertEqual([row["timestamp"] for row in result], [183, 184, 190, 191, 192, 193, 194])
        self.assertLessEqual(len(loaded), 7 * len(TYPED_EVENT_MODELS))
        self.assertTrue(all("LIMIT" in statement for statement in statements))
        self.assertEqual(len({row["event_type"] for row in result}), 5)

    def test_device_summary_aggregation_is_constant_and_excludes_empty_ips(self):
        devices = [Device(last_seen=i) for i in range(26)]
        db.session.add_all(devices)
        db.session.flush()
        for ip in ("", None, "192.0.2.1", "192.0.2.1", "192.0.2.2"):
            row = self.session(device_id=devices[-1].id, client_ip=ip)
            if ip is None:
                row.client_ip = None
                db.session.flush()
        with queries() as small:
            self.client.get("/devices?per_page=10")
        with queries() as large:
            result = self.client.get("/devices?per_page=25").get_json()
        self.assertEqual(len(small), len(large))
        self.assertEqual(len(large), 3)
        summary = result["devices"][0]
        self.assertEqual((summary["sessions_count"], summary["distinct_fsids"], summary["distinct_ips"]), (5, 1, 2))
        self.assertEqual(result["devices"][1]["sessions_count"], 0)

    def test_device_detail_pagination_bounds_and_empty_device(self):
        device = Device()
        empty = Device()
        db.session.add_all([device, empty])
        db.session.flush()
        rows = [self.session(device_id=device.id, last_seen=i) for i in range(126)]
        with queries() as statements:
            result = self.client.get(f"/devices/{device.id}").get_json()
        self.assertEqual((result["page"], result["per_page"], result["pages"], result["total"]), (1, 25, 6, 126))
        self.assertEqual(len(result["sessions"]), 25)
        self.assertEqual(result["sessions"][0]["id"], rows[-1].id)
        self.assertTrue(any("LIMIT" in statement for statement in statements))
        last = self.client.get(f"/devices/{device.id}?page=999&per_page=100").get_json()
        self.assertEqual((last["page"], last["pages"], len(last["sessions"])), (2, 2, 26))
        invalid = self.client.get(f"/devices/{device.id}?page=bad&per_page=9999").get_json()
        self.assertEqual((invalid["page"], invalid["per_page"]), (1, 25))
        empty_result = self.client.get(f"/devices/{empty.id}").get_json()
        self.assertEqual((empty_result["sessions"], empty_result["total"], empty_result["pages"]), ([], 0, 1))
        self.assertEqual(self.client.get("/devices/999999").status_code, 404)

    def test_sql_bot_classification_matches_python_and_counts_once_per_session(self):
        flags = [
            [], None, ["Webdriver"], ["Selenium", "CDP"], ["Playwright detected"],
            ["Bot", "Bot"], ["bot"], ["ordinary"], ["prefixBotSuffix"],
            ["Web", "driver"], ["BOT"], ["CDP", "Other"],
        ]
        rows = [self.session(flags=value, risk_score=60 if i % 2 else 59, last_seen=i)
                for i, value in enumerate(flags)]
        # Cover SQL NULL as well as JSON null.
        db.session.execute(Session.__table__.update().where(Session.id == rows[0].id).values(flags=null()))
        db.session.flush()
        matches = db.session.execute(
            select(Session.id, bot_flag_expression(Session.flags)).order_by(Session.id)
        ).all()
        self.assertEqual([bool(value) for _, value in matches], [has_bot_flag(value) for value in flags])
        with queries() as stats_queries:
            stats = self.client.get("/stats").get_json()
        self.assertEqual(len(stats_queries), 1)
        self.assertEqual(stats["bots_detected"], sum(has_bot_flag(value) for value in flags))
        self.assertEqual((stats["total_sessions"], stats["high_risk_count"], stats["low_risk_count"]), (12, 6, 6))
        with queries() as window_queries:
            window = _window_counts(1, 8)
        self.assertEqual(len(window_queries), 2)
        self.assertEqual(window["sessions"], 7)
        self.assertEqual(window["high_risk"], 4)
        self.assertEqual(window["bots"], sum(has_bot_flag(value) for value in flags[1:8]))
        self.assertEqual(_window_counts(1000, 2000)["sessions"], 0)

    def test_empty_lists_and_statistics(self):
        with queries() as statements:
            sessions = self.client.get("/sessions").get_json()
        self.assertEqual(len(statements), 2)
        self.assertEqual((sessions["sessions"], sessions["pages"], sessions["total"]), ([], 1, 0))
        with queries() as statements:
            devices = self.client.get("/devices").get_json()
        self.assertEqual(len(statements), 2)
        self.assertEqual(devices["devices"], [])
        stats = self.client.get("/stats").get_json()
        self.assertEqual(
            {key: stats[key] for key in ("total_sessions", "high_risk_count", "low_risk_count", "bots_detected")},
            dict(total_sessions=0, high_risk_count=0, low_risk_count=0, bots_detected=0),
        )
