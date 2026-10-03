import unittest
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask

from models import Session
from routes.behavioral_event import behavioral_event_bp
from routes.collect import collect_bp
from routes.heartbeat import heartbeat_bp
from services.visit_identity import get_or_create_visit, normalize_visit_id


class VisitIdentityTests(unittest.TestCase):
    def test_normalize_visit_id_requires_uuid(self):
        self.assertEqual(
            normalize_visit_id("00000000-0000-4000-8000-000000000001"),
            "00000000-0000-4000-8000-000000000001",
        )
        for value in (None, "", "not-a-uuid", 123):
            with self.subTest(value=value):
                self.assertIsNone(normalize_visit_id(value))

    def test_same_fsid_creates_distinct_visits(self):
        visits = {}

        class Query:
            def filter_by(self, **filters):
                return SimpleNamespace(first=lambda: visits.get(filters["visit_id"]))

        class SessionModel:
            query = Query()

            def __new__(cls, visit_id, fsid, first_seen):
                session = SimpleNamespace(
                    id=len(visits) + 1, visit_id=visit_id, fsid=fsid,
                    first_seen=first_seen,
                )
                visits[visit_id] = session
                return session

        app = Flask(__name__)
        with app.app_context(), \
                patch("models.Session", SessionModel), \
                patch("services.visit_identity.db") as database:
            database.session.flush.side_effect = lambda: None
            first = get_or_create_visit("visit-one", "same-fsid", 1)
            second = get_or_create_visit("visit-two", "same-fsid", 2)
            repeated = get_or_create_visit("visit-one", "new-fsid", 3)

        self.assertNotEqual(first.id, second.id)
        self.assertIs(first, repeated)
        self.assertEqual(first.fsid, "same-fsid")
        self.assertEqual(second.fsid, "same-fsid")
        self.assertEqual(len(visits), 2)

    def test_visit_id_is_unique_and_fsid_is_not(self):
        self.assertTrue(Session.__table__.c.visit_id.unique)
        self.assertFalse(Session.__table__.c.fsid.unique)

    def test_heartbeat_rejects_missing_visit_id_instead_of_falling_back(self):
        app = Flask(__name__)
        app.register_blueprint(heartbeat_bp)
        response = app.test_client().post("/api/heartbeat", json={"fsid": "old-fingerprint"})
        self.assertEqual(response.status_code, 400)

    def test_behavioral_event_rejects_missing_visit_id_instead_of_falling_back(self):
        app = Flask(__name__)
        app.register_blueprint(behavioral_event_bp)
        response = app.test_client().post("/api/behavioral_event", json={
            "fsid": "old-fingerprint", "event_type": "button_click", "data": {},
        })
        self.assertEqual(response.status_code, 400)

    def test_initial_route_creates_separate_rows_for_same_fsid(self):
        app = Flask(__name__)
        app.config["OFM_SAVE_PRIVATE_IP"] = True
        app.register_blueprint(collect_bp)
        sessions = {}

        def get_visit(visit_id, fsid, timestamp):
            sessions.setdefault(visit_id, SimpleNamespace(
                id=len(sessions) + 1, visit_id=visit_id, fsid=fsid,
                first_seen=timestamp, last_seen=timestamp, client_ip="",
                authenticated=False, domains=[],
            ))
            return sessions[visit_id]

        with patch("routes.collect.get_or_create_visit", side_effect=get_visit), \
                patch("routes.collect.Fingerprint") as fingerprint, \
                patch("routes.collect.SessionURL") as session_url, \
                patch("routes.collect.resolve_device", return_value=(SimpleNamespace(id=1, cookie_id=None), 1)), \
                patch("routes.collect.get_or_create_ip", return_value=None), \
                patch("routes.collect.get_or_create_user_agent", return_value=None), \
                patch("routes.collect.auth_cookie_present", return_value=False), \
                patch("routes.collect.add_session_domain"), \
                patch("routes.collect.enqueue_event"), \
                patch("routes.collect.db"):
            fingerprint.extract_fields.return_value = {"fsid": "same-fsid", "fast_bot_detection": False, "url": ""}
            session_url.query.filter_by.return_value.first.return_value = None
            client = app.test_client()
            responses = [client.post("/api/initial", json={
                "fsid": "same-fsid", "time": timestamp, "extensions": {},
                "visit_id": visit_id,
            }) for timestamp, visit_id in (
                (1, "00000000-0000-4000-8000-000000000001"),
                (2, "00000000-0000-4000-8000-000000000002"),
            )]

        self.assertEqual([response.status_code for response in responses], [200, 200])
        bodies = [response.get_json() for response in responses]
        self.assertEqual([body["session_id"] for body in bodies], [1, 2])
        self.assertEqual([body["fsid"] for body in bodies], ["same-fsid", "same-fsid"])
        self.assertEqual(len(sessions), 2)


if __name__ == "__main__":
    unittest.main()