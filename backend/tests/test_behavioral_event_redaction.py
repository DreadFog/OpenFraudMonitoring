import unittest
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask

from models import AuthAttemptEvent, FormSubmitEvent
from routes.behavioral_event import (
    _build_typed_event, _redact_event_data, behavioral_event_bp,
)
from models import TYPED_EVENT_MODELS


class BehavioralEventRedactionTests(unittest.TestCase):
    def setUp(self):
        self.config = SimpleNamespace(
            id=1, form_action="/login", form_method="post",
            form_field_names=["email", "password"],
        )
        self.lookup = patch(
            "routes.behavioral_event.configured_domain_for_host",
            side_effect=lambda host: self.config if host == "shop.example.com" else None,
        )
        self.lookup.start()
        self.addCleanup(self.lookup.stop)

    def test_copy_and_paste_credentials_are_redacted_before_storage(self):
        for event_type, prefix in [("copy", "source"), ("paste", "target")]:
            for field in ["email", "password"]:
                with self.subTest(event_type=event_type, field=field):
                    data = {
                        "text": "private-value", "length": 13,
                        f"{prefix}Name": field.upper(), f"{prefix}Id": "login-field",
                        "formAction": "https://shop.example.com/login",
                    }
                    sanitized = _redact_event_data(event_type, data, "shop.example.com", "")
                    event = _build_typed_event(
                        TYPED_EVENT_MODELS[event_type], 1, 123, "", sanitized, False,
                    )
                    self.assertEqual(event.text, "redacted")
                    self.assertEqual(event.length, 13)
                    self.assertEqual(getattr(event, f"{prefix}_id"), "login-field")
                    self.assertEqual(data["text"], "private-value")

    def test_page_host_matches_when_collection_host_is_separate(self):
        data = {"text": "private-value", "targetId": "email", "formAction": "/login"}
        sanitized = _redact_event_data(
            "paste", data, "ofm.example.com", "https://shop.example.com/login",
        )
        self.assertEqual(sanitized["text"], "redacted")

    def test_incomplete_metadata_still_protects_credentials(self):
        for metadata in [
            {"targetName": "email"},
            {"targetType": "password", "formAction": "/other"},
            {"formAction": "/login"},
        ]:
            with self.subTest(metadata=metadata):
                sanitized = _redact_event_data(
                    "paste", {"text": "secret", **metadata}, "shop.example.com", "",
                )
                self.assertEqual(sanitized["text"], "redacted")

    def test_unrelated_clipboard_events_are_unchanged(self):
        for host, metadata in [
            ("unknown.example.com", {"targetName": "email", "formAction": "/login"}),
            ("shop.example.com", {"targetName": "comment", "formAction": "/login"}),
            ("shop.example.com", {"targetName": "email", "formAction": "/newsletter"}),
        ]:
            with self.subTest(host=host, metadata=metadata):
                data = {"text": "ordinary-text", **metadata}
                self.assertEqual(_redact_event_data("paste", data, host, ""), data)

    def test_absent_clipboard_text_is_not_added(self):
        data = {"targetName": "password", "formAction": "/login"}
        self.assertNotIn("text", _redact_event_data("paste", data, "shop.example.com", ""))

    def test_missing_active_login_configuration_leaves_clipboard_unchanged(self):
        data = {"text": "ordinary-text", "targetName": "email", "formAction": "/login"}
        self.config = None
        self.assertEqual(_redact_event_data("paste", data, "shop.example.com", ""), data)
        self.config = SimpleNamespace(form_action="", form_field_names=["email"])
        self.assertEqual(_redact_event_data("paste", data, "shop.example.com", ""), data)

    def test_form_values_are_discarded(self):
        data = {
            "action": "/login", "method": "post", "fieldNames": ["email", "password"],
            "fields": [{"name": "email", "value": "private-user"},
                       {"name": "password", "value": "private-password"}],
        }
        sanitized = _redact_event_data("form_submit", data, "shop.example.com", "")
        self.assertNotIn("fields", sanitized)
        self.assertEqual(sanitized["fieldNames"], ["email", "password"])
        self.assertIn("fields", data)

    def test_endpoint_stores_redacted_clipboard_and_preserves_auth_attempt(self):
        app = Flask(__name__)
        app.register_blueprint(behavioral_event_bp)
        session = SimpleNamespace(id=1, visit_id="00000000-0000-4000-8000-000000000001",
                      fsid="test-session", domains=[])
        with patch("routes.behavioral_event.Session") as session_model, \
                patch("routes.behavioral_event.db") as database, \
                patch("routes.behavioral_event.auth_cookie_present", return_value=False), \
                patch("routes.behavioral_event.matching_form_config", return_value=self.config), \
                patch("routes.behavioral_event.enqueue_event"):
            session_model.query.filter_by.return_value.first.return_value = session
            client = app.test_client()
            response = client.post("/api/behavioral_event", base_url="https://shop.example.com", json={
                "visit_id": session.visit_id, "fsid": session.fsid, "timestamp": 123, "url": "https://shop.example.com/login",
                "event_type": "paste", "data": {
                    "text": "private-password", "targetName": "password", "formAction": "/login",
                },
            })
            self.assertEqual(response.status_code, 200)
            session_model.query.filter_by.assert_called_with(visit_id=session.visit_id)
            self.assertEqual(database.session.add.call_args.args[0].text, "redacted")
            database.session.add.reset_mock()
            response = client.post("/api/behavioral_event", base_url="https://shop.example.com", json={
                "visit_id": session.visit_id, "fsid": session.fsid, "timestamp": 124, "url": "https://shop.example.com/login",
                "event_type": "form_submit", "data": {
                    "action": "/login", "method": "post", "fieldNames": ["email", "password"],
                    "fields": [{"name": "password", "value": "private-password"}],
                },
            })
            self.assertEqual(response.status_code, 200)
            stored = [call.args[0] for call in database.session.add.call_args_list]
            self.assertEqual([type(event) for event in stored], [FormSubmitEvent, AuthAttemptEvent])
            for event in stored:
                self.assertNotIn("private-password", str(event.to_dict()))


if __name__ == "__main__":
    unittest.main()