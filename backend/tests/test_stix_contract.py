import unittest
from datetime import datetime

from models.stix.sco import StixIPv4Addr
from services.stix_objects import normalize_stix_object


class StixNormalizationTests(unittest.TestCase):
    def test_api_wrapper_separates_payload_and_preserves_legacy_fields(self):
        raw = {
            "type": "ipv4-addr",
            "spec_version": "2.1",
            "id": "ipv4-addr--11111111-1111-4111-8111-111111111111",
            "value": "192.0.2.1",
        }
        row = StixIPv4Addr(
            id=7,
            stix_id=raw["id"],
            value="192.0.2.1",
            created_at_platform=datetime(2026, 10, 6),
            decayed=True,
            raw=raw,
            source_connector_id=3,
        )

        result = row.to_dict()

        self.assertEqual(result["raw"], raw)
        self.assertEqual(result["stix_object"], raw)
        self.assertEqual(result["platform"]["id"], 7)
        self.assertEqual(result["created_at_platform"], "2026-10-06T00:00:00")
        self.assertTrue(result["decayed"])
        self.assertEqual(result["platform"]["source_connector_id"], 3)

    def test_user_agent_uses_opencti_value_shape(self):
        obj = normalize_stix_object({
            "type": "user-agent",
            "id": "user-agent--11111111-1111-4111-8111-111111111111",
            "string": "Browser/1.0",
            "x_ofm_type": "User-Agent",
        })

        self.assertEqual(obj["value"], "Browser/1.0")
        self.assertEqual(obj["x_opencti_type"], "User-Agent")
        self.assertNotIn("string", obj)
        self.assertNotIn("created", obj)
        self.assertNotIn("x_ofm_type", obj)

    def test_country_uses_location_sdo_properties_and_version_times(self):
        obj = normalize_stix_object({
            "type": "location",
            "id": "location--11111111-1111-4111-8111-111111111111",
            "name": "France",
            "country": "France",
            "x_ofm_location_type": "Country",
        })

        self.assertEqual(obj["type"], "location")
        self.assertEqual(obj["x_opencti_location_type"], "Country")
        self.assertEqual(obj["modified"], obj["created"])
        self.assertEqual(obj["confidence"], 100)
        self.assertNotIn("x_ofm_location_type", obj)

    def test_relationship_maps_legacy_source_timestamp_and_type(self):
        obj = normalize_stix_object({
            "type": "relationship",
            "id": "relationship--11111111-1111-4111-8111-111111111111",
            "relationship_type": "belongs-to",
            "source_ref": "ipv4-addr--11111111-1111-4111-8111-111111111111",
            "target_ref": "autonomous-system--11111111-1111-4111-8111-111111111111",
            "_octi_created_at": "2026-10-06T12:00:00Z",
        })

        self.assertEqual(obj["created"], "2026-10-06T12:00:00.000Z")
        self.assertEqual(obj["modified"], obj["created"])
        self.assertEqual(obj["x_opencti_type"], "belongs-to")
        self.assertEqual(obj["confidence"], 100)
        self.assertNotIn("_octi_created_at", obj)

    def test_sco_drops_version_timestamps_and_platform_keys(self):
        obj = normalize_stix_object({
            "type": "autonomous-system",
            "id": "autonomous-system--11111111-1111-4111-8111-111111111111",
            "number": 64512,
            "created": "2026-10-06T12:00:00Z",
            "created_at_platform": "2026-10-06T12:00:00Z",
            "name": "Example AS",
        })

        self.assertEqual(obj["number"], 64512)
        self.assertEqual(obj["x_opencti_type"], "Autonomous-System")
        self.assertNotIn("created", obj)
        self.assertNotIn("created_at_platform", obj)

    def test_unknown_types_are_rejected(self):
        with self.assertRaises(ValueError):
            normalize_stix_object({
                "type": "custom-observable",
                "id": "custom-observable--11111111-1111-4111-8111-111111111111",
            })


if __name__ == "__main__":
    unittest.main()