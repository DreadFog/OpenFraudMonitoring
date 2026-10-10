import base64
import json
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask

import routes.taxii as taxii
from routes.taxii import TAXII_MEDIA_TYPE, taxii_bp


FEED_ID = "8a0b5f7e-6f0e-4e41-9b44-2f4c1f0b7d11"
ROOT = "/taxii2/default"


def _record(stix_id, date_added, version=None, spec_version="2.1"):
    raw = {"type": stix_id.split("--")[0], "id": stix_id, "spec_version": spec_version}
    if version:
        raw["created"] = version
        raw["modified"] = version
    return taxii.TaxiiRecord(
        date_added=date_added,
        stix_id=stix_id,
        version=version or taxii.format_timestamp(date_added),
        spec_version=spec_version,
        raw=raw,
    )


IP_A = _record("ipv4-addr--00000000-0000-4000-8000-000000000001", datetime(2026, 1, 1, 10, 0, 0))
IP_B = _record("ipv4-addr--00000000-0000-4000-8000-000000000002", datetime(2026, 1, 1, 10, 0, 0))
IND = _record(
    "indicator--00000000-0000-4000-8000-000000000003",
    datetime(2026, 1, 2, 10, 0, 0, 123456),
    version="2025-12-31T08:00:00.000Z",
)
MAL = _record(
    "malware--00000000-0000-4000-8000-000000000004",
    datetime(2026, 1, 3, 10, 0, 0),
    version="2025-12-30T08:00:00.000Z",
    spec_version="2.0",
)
STORE = {"ipv4-addr": [IP_A, IP_B], "indicator": [IND], "malware": [MAL]}


def fake_sources(feed, types, ids=None, added_after=None, cursor=None):
    sources = []
    for stix_type in types:
        records = []
        for record in STORE.get(stix_type, []):
            if ids and record.stix_id not in ids:
                continue
            if added_after is not None and record.date_added <= added_after:
                continue
            if cursor is not None and record.sort_key <= cursor:
                continue
            records.append(record)
        sources.append(iter(sorted(records, key=lambda item: item.sort_key)))
    return sources


class TaxiiServerTests(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        app.register_blueprint(taxii_bp)
        self.client = app.test_client()
        self.feed = SimpleNamespace(
            id=1, uuid=FEED_ID, name="Feed", description="", object_types=[], filters=[],
        )
        user = SimpleNamespace(id=1, is_active=True)
        self.patches = [
            patch.object(taxii, "refresh_indicator_revocation"),
            patch.object(taxii, "_resolve_taxii_user", return_value=user),
            patch.object(taxii, "active_feed_by_uuid", side_effect=lambda cid: self.feed if cid == FEED_ID else None),
            patch.object(taxii, "record_sources", side_effect=fake_sources),
        ]
        for item in self.patches:
            item.start()
        self.addCleanup(lambda: [item.stop() for item in self.patches])

    def get(self, path, **kwargs):
        headers = kwargs.pop("headers", {"Accept": TAXII_MEDIA_TYPE})
        return self.client.get(path, headers=headers, **kwargs)

    def body(self, response):
        return json.loads(response.data)

    def test_discovery_and_api_root(self):
        response = self.get("/taxii2/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], TAXII_MEDIA_TYPE)
        self.assertEqual(self.body(response)["api_roots"], ["/taxii2/default/"])

        root = self.body(self.get(f"{ROOT}/"))
        self.assertEqual(root["versions"], [TAXII_MEDIA_TYPE])
        self.assertGreater(root["max_content_length"], 0)

    def test_accept_negotiation(self):
        self.assertEqual(self.get("/taxii2/", headers={"Accept": "application/taxii+json;version=2.0"}).status_code, 406)
        self.assertEqual(self.get("/taxii2/", headers={"Accept": "text/html"}).status_code, 406)
        browser = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        self.assertEqual(self.get("/taxii2/", headers={"Accept": browser}).status_code, 200)
        self.assertEqual(self.get("/taxii2/", headers={"Accept": "application/taxii+json"}).status_code, 200)
        self.assertEqual(self.get("/taxii2/", headers={}).status_code, 200)

    def test_unauthenticated_request_gets_challenge(self):
        with patch.object(taxii, "_resolve_taxii_user", return_value=None):
            response = self.get(f"{ROOT}/collections/")
        self.assertEqual(response.status_code, 401)
        self.assertIn("Basic", response.headers["WWW-Authenticate"])
        self.assertIn("Bearer", response.headers["WWW-Authenticate"])
        self.assertEqual(self.body(response)["http_status"], "401")
        self.assertEqual(response.headers["Content-Type"], TAXII_MEDIA_TYPE)

    def test_collection_resources(self):
        with patch.object(taxii, "TaxiiFeed") as feed_model:
            feed_model.query.filter_by.return_value.order_by.return_value.all.return_value = [self.feed]
            listed = self.body(self.get(f"{ROOT}/collections/"))
            feed_model.query.filter_by.return_value.order_by.return_value.all.return_value = []
            empty = self.body(self.get(f"{ROOT}/collections/"))
        self.assertEqual(empty, {})
        collection = listed["collections"][0]
        self.assertEqual(collection["id"], FEED_ID)
        self.assertTrue(collection["can_read"])
        self.assertFalse(collection["can_write"])
        self.assertEqual(collection["media_types"], ["application/stix+json;version=2.1"])
        self.assertNotIn("objects", collection)
        self.assertEqual(self.get(f"{ROOT}/collections/unknown/").status_code, 404)

    def test_objects_envelope_pagination_and_headers(self):
        first = self.get(f"{ROOT}/collections/{FEED_ID}/objects/?limit=2")
        payload = self.body(first)
        self.assertTrue(payload["more"])
        self.assertEqual([obj["id"] for obj in payload["objects"]], [IP_A.stix_id, IP_B.stix_id])
        self.assertEqual(first.headers["X-TAXII-Date-Added-First"], "2026-01-01T10:00:00.000000Z")
        self.assertEqual(first.headers["X-TAXII-Date-Added-Last"], "2026-01-01T10:00:00.000000Z")

        second = self.body(self.get(f"{ROOT}/collections/{FEED_ID}/objects/?limit=2&next={payload['next']}"))
        self.assertFalse(second["more"])
        self.assertNotIn("next", second)
        self.assertEqual([obj["id"] for obj in second["objects"]], [IND.stix_id, MAL.stix_id])

    def test_objects_filters(self):
        url = f"{ROOT}/collections/{FEED_ID}/objects/"
        by_type = self.body(self.get(f"{url}?match[type]=indicator,malware"))
        self.assertEqual([obj["id"] for obj in by_type["objects"]], [IND.stix_id, MAL.stix_id])
        by_id = self.body(self.get(f"{url}?match[id]={IP_B.stix_id}"))
        self.assertEqual([obj["id"] for obj in by_id["objects"]], [IP_B.stix_id])
        after = self.body(self.get(f"{url}?added_after=2026-01-02T10:00:00.123456Z"))
        self.assertEqual([obj["id"] for obj in after["objects"]], [MAL.stix_id])
        spec = self.body(self.get(f"{url}?match[spec_version]=2.0"))
        self.assertEqual([obj["id"] for obj in spec["objects"]], [MAL.stix_id])
        version = self.body(self.get(f"{url}?match[version]=2025-12-31T08:00:00Z"))
        self.assertEqual([obj["id"] for obj in version["objects"]], [IND.stix_id])
        self.assertEqual(len(self.body(self.get(f"{url}?match[version]=all"))["objects"]), 4)
        empty = self.get(f"{url}?match[type]=campaign")
        self.assertEqual(self.body(empty), {"more": False})
        self.assertNotIn("X-TAXII-Date-Added-First", empty.headers)

    def test_feed_object_types_scope_collection(self):
        self.feed.object_types = ["malware"]
        payload = self.body(self.get(f"{ROOT}/collections/{FEED_ID}/objects/?match[type]=indicator,malware"))
        self.assertEqual([obj["id"] for obj in payload["objects"]], [MAL.stix_id])

    def test_invalid_parameters(self):
        url = f"{ROOT}/collections/{FEED_ID}/objects/"
        for query in ("limit=0", "limit=abc", "added_after=yesterday", "next=garbage",
                      "match[type]=indicator&match[type]=malware", "match[version]=latest"):
            response = self.get(f"{url}?{query}")
            self.assertEqual(response.status_code, 400, query)
            self.assertEqual(self.body(response)["http_status"], "400")

    def test_manifest_keeps_same_date_group_and_omits_next(self):
        response = self.get(f"{ROOT}/collections/{FEED_ID}/manifest/?limit=3")
        payload = self.body(response)
        self.assertTrue(payload["more"])
        self.assertNotIn("next", payload)
        self.assertEqual(
            payload["objects"][2],
            {
                "id": IND.stix_id,
                "date_added": "2026-01-02T10:00:00.123456Z",
                "version": "2025-12-31T08:00:00.000Z",
                "media_type": "application/stix+json;version=2.1",
            },
        )
        cut = self.body(self.get(f"{ROOT}/collections/{FEED_ID}/manifest/?limit=1"))
        self.assertEqual([item["id"] for item in cut["objects"]], [IP_A.stix_id])

    def test_object_and_versions(self):
        url = f"{ROOT}/collections/{FEED_ID}/objects/{IND.stix_id}/"
        payload = self.body(self.get(url))
        self.assertEqual(payload["objects"], [IND.raw])
        filtered = self.get(f"{url}?match[version]=2020-01-01T00:00:00Z")
        self.assertEqual(filtered.status_code, 200)
        self.assertEqual(self.body(filtered), {"more": False})

        versions = self.get(f"{url}versions/")
        self.assertEqual(self.body(versions), {"more": False, "versions": ["2025-12-31T08:00:00.000Z"]})
        self.assertEqual(versions.headers["X-TAXII-Date-Added-Last"], "2026-01-02T10:00:00.123456Z")

        missing = f"{ROOT}/collections/{FEED_ID}/objects/campaign--00000000-0000-4000-8000-000000000009/"
        self.assertEqual(self.get(missing).status_code, 404)
        self.assertEqual(self.get(f"{missing}versions/").status_code, 404)

    def test_read_only_operations(self):
        objects = f"{ROOT}/collections/{FEED_ID}/objects/"
        post = self.client.post(objects, data="{}", headers={
            "Accept": TAXII_MEDIA_TYPE, "Content-Type": TAXII_MEDIA_TYPE,
        })
        self.assertEqual(post.status_code, 403)
        delete = self.client.delete(f"{objects}{IND.stix_id}/", headers={"Accept": TAXII_MEDIA_TYPE})
        self.assertEqual(delete.status_code, 403)
        self.assertEqual(self.get(f"{ROOT}/status/2d086da7-4bdc-4f91-900e-d77486753710/").status_code, 404)

    def test_unknown_paths_return_taxii_errors(self):
        response = self.get("/taxii2/other-root/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.headers["Content-Type"], TAXII_MEDIA_TYPE)


class TaxiiHelperTests(unittest.TestCase):
    def test_cursor_round_trip_and_timestamp_format(self):
        ts = datetime(2026, 2, 3, 4, 5, 6, 7)
        self.assertEqual(taxii.decode_cursor(taxii.encode_cursor(ts, "x--1")), (ts, "x--1"))
        self.assertIsNone(taxii.decode_cursor(base64.urlsafe_b64encode(b"[]").decode()))
        self.assertEqual(taxii.format_timestamp(ts), "2026-02-03T04:05:06.000007Z")
        self.assertEqual(taxii.parse_timestamp("2026-02-03T05:05:06+01:00"), datetime(2026, 2, 3, 4, 5, 6))
        self.assertIsNone(taxii.parse_timestamp("2026-02-03"))

    def test_record_from_row_versions(self):
        created = datetime(2026, 1, 1, 0, 0, 0)
        refreshed = datetime(2026, 1, 5, 0, 0, 0)
        sco = SimpleNamespace(stix_id="ipv4-addr--1", created_at_platform=created, last_refreshed_at=refreshed,
                              raw={"type": "ipv4-addr", "id": "ipv4-addr--1", "value": "1.2.3.4"})
        record = taxii.record_from_row(sco)
        self.assertEqual(record.date_added, refreshed)
        self.assertEqual(record.version, "2026-01-01T00:00:00.000000Z")
        self.assertEqual(record.spec_version, "2.1")

        rel = SimpleNamespace(stix_id="relationship--1", created_at_platform=created,
                              raw={"type": "relationship", "modified": "2025-05-05T00:00:00.000Z"})
        self.assertEqual(taxii.record_from_row(rel).version, "2025-05-05T00:00:00.000Z")

    def test_feed_types(self):
        self.assertEqual(taxii.feed_types(SimpleNamespace(object_types=[])), list(taxii.SUPPORTED_TYPES))
        self.assertEqual(taxii.feed_types(SimpleNamespace(object_types=["Malware", "bogus"])), ["malware"])

    def test_indicator_export_includes_effective_revocation(self):
        row = SimpleNamespace(
            stix_id=IND.stix_id, created_at_platform=IND.date_added,
            last_refreshed_at=None, raw=IND.raw, revoked=True,
        )
        self.assertTrue(taxii.record_from_row(row).raw["revoked"])
        self.assertNotIn("revoked", IND.raw)


if __name__ == "__main__":
    unittest.main()
