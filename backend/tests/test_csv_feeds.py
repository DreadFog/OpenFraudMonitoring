import csv
import io
import os
import unittest
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask
from sqlalchemy import create_engine, text

from models import StixIPv4Addr, TaxiiFeed, User
from routes.taxii import taxii_bp
from routes.taxii_feeds import csv_feeds_bp, taxii_feeds_bp
from services.csv_feeds import render_csv, update_csv_batch, validate_feed_options
from services.database import db


def observable(stix_id, value):
    return StixIPv4Addr(stix_id=stix_id, value=value, raw={"type": "ipv4-addr", "id": stix_id, "value": value})


class CsvFeedTests(unittest.TestCase):
    def test_standard_delimiters_preserve_cells_and_headers(self):
        for delimiter in (",", ";", "\t", "|"):
            with self.subTest(delimiter=delimiter):
                value = f'first{delimiter}"second"\nthird'
                row = observable("ipv4-addr--one", value)
                content = render_csv([row], ["value", "id"], True, delimiter)
                self.assertEqual(list(csv.reader(io.StringIO(content), delimiter=delimiter)), [
                    ["value", "id"], [value, "ipv4-addr--one"],
                ])
                self.assertTrue(content.startswith(f"value{delimiter}id\r\n"))

    def test_order_headers_quoting_unicode_and_formula_safety(self):
        row = observable("ipv4-addr--one", 'value, "quoted"\nnext')
        content = render_csv([row], ["value", "id"], True)
        self.assertEqual(list(csv.reader(io.StringIO(content))), [
            ["value", "id"], ['value, "quoted"\nnext', "ipv4-addr--one"],
        ])
        self.assertEqual(render_csv([observable("id", "=SUM(1,2)")], ["value"], False), '"\'=SUM(1,2)"\r\n')
        self.assertEqual(render_csv([], ["value"], False), "")

    def test_scheduled_baseline_new_matches_reentry_and_stable_download(self):
        feed = SimpleNamespace(
            last_generated_at=None, update_interval_minutes=5, matching_ids=[],
            export_fields=["value"], include_headers=False,
        )
        first = observable("ipv4-addr--one", "192.0.2.1")
        second = observable("ipv4-addr--two", "192.0.2.2")
        now = datetime(2026, 10, 10)
        with patch("services.csv_feeds.matching_rows", return_value=[first]) as source:
            self.assertTrue(update_csv_batch(feed, now))
            self.assertEqual(feed.csv_content, "192.0.2.1\r\n")
            self.assertFalse(update_csv_batch(feed, now + timedelta(minutes=1)))
            self.assertEqual(feed.csv_content, "192.0.2.1\r\n")
            source.return_value = [first, second]
            update_csv_batch(feed, now + timedelta(minutes=5))
            self.assertEqual(feed.csv_content, "192.0.2.2\r\n")
            source.return_value = [second]
            update_csv_batch(feed, now + timedelta(minutes=10))
            self.assertEqual(feed.csv_content, "")
            source.return_value = [first, second]
            update_csv_batch(feed, now + timedelta(minutes=15))
            self.assertEqual(feed.csv_content, "192.0.2.1\r\n")

    def test_configuration_validation_and_private_defaults(self):
        self.assertFalse(validate_feed_options({})["is_public"])
        self.assertEqual(validate_feed_options({})["csv_delimiter"], ",")
        config = {"export_format": "csv", "object_types": ["indicator"], "export_fields": ["name", "valid_until", "revoked"]}
        self.assertTrue(validate_feed_options(config)["include_headers"])
        for changes in (
            {"export_fields": []}, {"export_fields": ["secret"]}, {"export_fields": ["name", "name"]},
            {"object_types": ["indicator", "malware"]}, {"is_public": "false"},
            {"update_interval_minutes": True}, {"update_interval_minutes": 0},
            {"filter_logic": "XOR"}, {"export_format": "taxii", "auto_update": True},
            {"csv_delimiter": "::"}, {"csv_delimiter": "\n"}, {"csv_delimiter": None},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_feed_options({**config, **changes})


@unittest.skipUnless(os.environ.get("CSV_TEST_DATABASE_URL"), "Requires PostgreSQL for isolated export schema")
class CsvFeedDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = "csv_test_" + uuid.uuid4().hex
        cls.engine = create_engine(os.environ["CSV_TEST_DATABASE_URL"])
        with cls.engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{cls.schema}"'))
        cls.app = Flask(__name__)
        cls.app.config["SQLALCHEMY_DATABASE_URI"] = os.environ["CSV_TEST_DATABASE_URL"]
        cls.app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "connect_args": {"options": f"-c search_path={cls.schema} -c statement_timeout=15000 -c lock_timeout=5000"},
        }
        db.init_app(cls.app)
        cls.app.register_blueprint(taxii_feeds_bp)
        cls.app.register_blueprint(csv_feeds_bp)
        cls.app.register_blueprint(taxii_bp)
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
        self.client = self.app.test_client()
        db.session.query(TaxiiFeed).delete()
        db.session.query(StixIPv4Addr).delete()
        db.session.query(User).delete()
        user = User(username="csv-admin", role="admin", is_active=True)
        db.session.add(user)
        db.session.flush()
        self.user_id = user.id
        db.session.add(observable("ipv4-addr--one", "192.0.2.1"))
        db.session.commit()
        authentication = patch("services.auth.decode_jwt", return_value={"sub": self.user_id})
        authentication.start()
        self.addCleanup(authentication.stop)
        self.headers = {"Authorization": "Bearer test"}

    def tearDown(self):
        db.session.remove()

    def create(self, **changes):
        response = self.client.post("/api/taxii-feeds", headers=self.headers, json={
            "name": "CSV", "export_format": "csv", "object_types": ["ipv4-addr"],
            "export_fields": ["value"], **changes,
        })
        self.assertEqual(response.status_code, 201, response.json)
        self.assertTrue(response.json["objects_url"].endswith(f"/api/csv/{response.json['uuid']}/"))
        return response.json

    def test_private_csv_requires_auth_and_public_download_has_optional_headers(self):
        feed = self.create()
        with patch("routes.taxii._resolve_taxii_user", return_value=None):
            response = self.client.get(f"/api/csv/{feed['uuid']}/")
            self.assertEqual(response.status_code, 401)
            self.assertIn("WWW-Authenticate", response.headers)
        feed = self.create(is_public=True, include_headers=False)
        response = self.client.get(f"/api/csv/{feed['uuid']}/")
        self.assertEqual(response.data.decode(), "192.0.2.1\r\n")
        self.assertEqual(response.data, self.client.get(f"/api/taxii-feeds/{feed['uuid']}/csv").data)
        self.assertEqual(response.mimetype, "text/csv")
        self.assertEqual(self.client.get("/api/taxii-feeds").status_code, 401)

    def test_incremental_persistence_filter_entry_and_metadata_edits(self):
        feed = self.create(is_public=True, auto_update=True, update_interval_minutes=1,
                           filters=[{"field": "value", "op": "starts_with", "value": "192."}])
        path = f"/api/csv/{feed['uuid']}/"
        first = self.client.get(path).data
        self.assertEqual(first, self.client.get(path).data)
        stored = db.session.get(TaxiiFeed, feed["id"])
        generated = stored.last_generated_at
        response = self.client.patch(f"/api/taxii-feeds/{feed['id']}", headers=self.headers, json={"name": "Renamed"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(db.session.get(TaxiiFeed, feed["id"]).last_generated_at, generated)
        db.session.add(observable("ipv4-addr--two", "198.51.100.1"))
        db.session.commit()
        new = db.session.query(StixIPv4Addr).filter_by(stix_id="ipv4-addr--two").one()
        new.value = "192.0.2.2"
        new.raw = {**new.raw, "value": new.value}
        stored.last_generated_at = datetime.utcnow() - timedelta(minutes=2)
        db.session.commit()
        content = self.client.get(path).data
        self.assertIn(b"192.0.2.2", content)
        self.assertNotIn(b"192.0.2.1", content)
        self.assertEqual(content, self.client.get(path).data)

    def test_delimiter_saved_for_full_and_incremental_exports_and_can_change(self):
        for incremental in (False, True):
            with self.subTest(incremental=incremental):
                feed = self.create(
                    is_public=True, auto_update=incremental, csv_delimiter=";",
                    export_fields=["value", "id"],
                )
                self.assertEqual(feed["csv_delimiter"], ";")
                path = f"/api/csv/{feed['uuid']}/"
                expected = "value;id\r\n192.0.2.1;ipv4-addr--one\r\n"
                self.assertEqual(self.client.get(path).data.decode(), expected)
                response = self.client.patch(
                    f"/api/taxii-feeds/{feed['id']}", headers=self.headers,
                    json={"csv_delimiter": "\t"},
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json["csv_delimiter"], "\t")
                self.assertEqual(self.client.get(path).data.decode(), expected.replace(";", "\t"))

    def test_public_taxii_hides_private_collections_and_csv(self):
        self.create(is_public=True)
        for public in (False, True):
            response = self.client.post("/api/taxii-feeds", headers=self.headers, json={
                "name": "public" if public else "private", "object_types": ["ipv4-addr"], "is_public": public,
            })
            self.assertEqual(response.status_code, 201)
            if public:
                public_id = response.json["uuid"]
            else:
                private_id = response.json["uuid"]
        with patch("routes.taxii._resolve_taxii_user", return_value=None):
            response = self.client.get("/taxii2/default/collections/")
            self.assertEqual([item["id"] for item in response.json["collections"]], [public_id])
            self.assertEqual(self.client.get(f"/taxii2/default/collections/{private_id}/objects/").status_code, 401)
            self.assertEqual(self.client.get(f"/taxii2/default/collections/{public_id}/objects/").status_code, 200)
            self.assertEqual(self.client.get(f"/taxii2/default/collections/{public_id}/manifest/").status_code, 200)
            self.assertEqual(self.client.post(f"/taxii2/default/collections/{public_id}/objects/").status_code, 401)

    def test_filters_and_configuration_rejected_without_creating_feed(self):
        for changes in ({"export_fields": ["missing"]}, {"filters": [{"field": "missing", "op": "eq", "value": "x"}]}):
            response = self.client.post("/api/taxii-feeds", headers=self.headers, json={
                "name": "Invalid", "export_format": "csv", "object_types": ["ipv4-addr"], "export_fields": ["value"], **changes,
            })
            self.assertEqual(response.status_code, 400)
        self.assertEqual(db.session.query(TaxiiFeed).count(), 0)


if __name__ == "__main__":
    unittest.main()