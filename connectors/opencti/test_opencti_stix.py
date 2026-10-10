import unittest
from types import SimpleNamespace

import opencti_client


class OpenCtiStixTests(unittest.TestCase):
    def test_lookup_includes_only_unrevoked_based_on_indicators_and_supported_targets(self):
        ip = {
            "id": "ip-internal-id",
            "entity_type": "IPv4-Addr",
            "standard_id": "ipv4-addr--11111111-1111-4111-8111-111111111111",
            "value": "192.0.2.1",
        }
        active_indicator = {
            "id": "active-indicator-id",
            "entity_type": "Indicator",
            "standard_id": "indicator--22222222-2222-4222-8222-222222222222",
            "name": "active indicator",
            "pattern": "[ipv4-addr:value = '192.0.2.1']",
            "revoked": False,
            "objectLabel": [{"value": "malicious-activity"}, {"value": "ip-watchlist"}],
        }
        revoked_indicator = {
            "id": "revoked-indicator-id",
            "entity_type": "Indicator",
            "standard_id": "indicator--33333333-3333-4333-8333-333333333333",
            "name": "revoked indicator",
            "pattern": "[ipv4-addr:value = '192.0.2.1']",
            "revoked": True,
        }
        based_on = [
            {
                "id": "based-on-active",
                "standard_id": "relationship--44444444-4444-4444-8444-444444444444",
                "relationship_type": "based-on",
                "fromId": active_indicator["id"],
                "toId": ip["id"],
                "from": active_indicator,
            },
            {
                "id": "based-on-revoked",
                "standard_id": "relationship--55555555-5555-4555-8555-555555555555",
                "relationship_type": "based-on",
                "fromId": revoked_indicator["id"],
                "toId": ip["id"],
                "from": revoked_indicator,
            },
        ]
        targets = [
            ("Malware", "malware", "malware--66666666-6666-4666-8666-666666666666"),
            ("Campaign", "campaign", "campaign--77777777-7777-4777-8777-777777777777"),
            ("Intrusion-Set", "intrusion-set", "intrusion-set--88888888-8888-4888-8888-888888888888"),
            ("Tool", "tool", "tool--99999999-9999-4999-8999-999999999999"),
        ]
        indicates = []
        for index, (entity_type, _stix_type, standard_id) in enumerate(targets):
            indicates.append({
                "id": f"indicates-{index}",
                "standard_id": f"relationship--aaaaaaaa-aaaa-4aaa-8aaa-{index:012d}",
                "relationship_type": "indicates",
                "fromId": active_indicator["id"],
                "toId": f"target-{index}",
                "from": active_indicator,
                "to": {
                    "id": f"target-{index}",
                    "entity_type": entity_type,
                    "standard_id": standard_id,
                    "name": f"target {index}",
                    "is_family": True,
                },
            })

        calls = []
        indicator_reads = []

        def list_relationships(**kwargs):
            calls.append(kwargs)
            if kwargs.get("relationship_type") == "based-on":
                return based_on
            if kwargs.get("relationship_type") == "indicates":
                return indicates
            return []

        def read_indicator(**kwargs):
            indicator_reads.append(kwargs)
            return {
                active_indicator["id"]: active_indicator,
                revoked_indicator["id"]: revoked_indicator,
            }.get(kwargs.get("id"))

        client = opencti_client.OpenCTIClient.__new__(opencti_client.OpenCTIClient)
        client.client = SimpleNamespace(
            stix_cyber_observable=SimpleNamespace(list=lambda **_kwargs: [ip]),
            stix_core_relationship=SimpleNamespace(list=list_relationships),
            stix_core_object=SimpleNamespace(read=read_indicator),
        )

        bundle = client.lookup_ip("192.0.2.1")

        objects = bundle["objects"]
        types = [obj["type"] for obj in objects]
        self.assertEqual(types.count("indicator"), 1)
        self.assertEqual(types.count("malware"), 1)
        self.assertEqual(types.count("campaign"), 1)
        self.assertEqual(types.count("intrusion-set"), 1)
        self.assertNotIn("tool", types)
        active_indicator_object = next(obj for obj in objects if obj["type"] == "indicator")
        self.assertEqual(active_indicator_object["labels"], ["malicious-activity", "ip-watchlist"])
        self.assertNotIn(revoked_indicator["standard_id"], {obj["id"] for obj in objects})
        self.assertTrue(any(call.get("relationship_type") == "based-on" and call.get("toId") == ip["id"] for call in calls))
        self.assertTrue(all(call.get("getAll") is True for call in calls))
        self.assertEqual(len(indicator_reads), 2)
        self.assertTrue(all("revoked" in read["customAttributes"] and "pattern" in read["customAttributes"] for read in indicator_reads))
        attributes = indicator_reads[0]["customAttributes"]
        root_fields = attributes.split("... on StixDomainObject", 1)[0]
        self.assertNotIn("created\n", root_fields)
        self.assertIn("... on Indicator", attributes)
        self.assertNotIn("labels", attributes)
        target_query = next(call for call in calls if call.get("relationship_type") == "indicates")
        self.assertEqual(set(target_query["toTypes"]), {"Malware", "Campaign", "Intrusion-Set"})

    def test_country_keeps_opencti_name_aliases_and_timestamps(self):
        country = opencti_client._country_to_stix({
            "id": "62a2563f-700c-4758-918c-65044cd7c09f",
            "entity_type": "Country",
            "standard_id": "location--11111111-1111-4111-8111-111111111111",
            "name": "France",
            "x_opencti_aliases": ["FRA", "FR"],
            "created_at": "2023-11-19T00:56:37.043Z",
        })

        self.assertEqual(country["country"], "France")
        self.assertEqual(country["x_opencti_aliases"], ["FRA", "FR"])
        self.assertEqual(country["x_opencti_location_type"], "Country")
        self.assertEqual(country["created"], "2023-11-19T00:56:37.043Z")
        self.assertEqual(country["modified"], country["created"])

    def test_indicator_and_relationship_have_stix_version_fields(self):
        indicator = opencti_client._indicator_to_stix({
            "id": "fa7b2264-0f67-484f-97b3-3e69c7b2eded",
            "entity_type": "Indicator",
            "standard_id": "indicator--11111111-1111-4111-8111-111111111111",
            "name": "test",
            "description": "Known malicious activity",
            "pattern": "[ipv4-addr:value = '192.0.2.1']",
            "pattern_type": None,
            "valid_from": None,
            "confidence": None,
            "revoked": None,
            "created_at": "2026-10-06T12:00:00.000Z",
        })
        relationship = opencti_client._relationship_to_stix({
            "id": "3ce1486d-4365-4823-ab11-3ac40f1447a1",
            "relationship_type": "belongs-to",
            "created_at": "2026-10-06T12:00:00.000Z",
        }, "ipv4-addr--11111111-1111-4111-8111-111111111111",
            "autonomous-system--11111111-1111-4111-8111-111111111111")

        self.assertTrue(indicator["created"] and indicator["modified"] and indicator["valid_from"])
        self.assertEqual(indicator["name"], "test")
        self.assertEqual(indicator["description"], "Known malicious activity")
        self.assertEqual(indicator["pattern_type"], "stix")
        self.assertEqual(indicator["confidence"], 100)
        self.assertIs(indicator["revoked"], False)
        self.assertEqual(relationship["created"], relationship["modified"])
        self.assertEqual(relationship["x_opencti_type"], "belongs-to")
        self.assertNotIn("_octi_created_at", indicator)
        self.assertNotIn("_octi_created_at", relationship)


if __name__ == "__main__":
    unittest.main()