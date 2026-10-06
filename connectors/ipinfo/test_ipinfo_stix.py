import unittest
from types import SimpleNamespace
from unittest.mock import patch

from ipinfo_client import IPInfoClient


class IPInfoStixTests(unittest.TestCase):
    def test_bundle_uses_country_location_and_standard_relationships(self):
        response = SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {
                "asn": "AS15169",
                "as_name": "Example AS",
                "country_code": "FR",
                "country": "France",
            },
        )
        with patch("ipinfo_client.requests.get", return_value=response):
            bundle = IPInfoClient("test").lookup_ip("192.0.2.8")

        by_type = {}
        for obj in bundle["objects"]:
            by_type.setdefault(obj["type"], []).append(obj)
            self.assertFalse(any(key.startswith("x_ofm_") or key.startswith("_") for key in obj))
        location = by_type["location"][0]
        self.assertEqual(location["country"], "France")
        self.assertEqual(location["x_opencti_aliases"], ["FR"])
        self.assertEqual(location["x_opencti_location_type"], "Country")
        self.assertTrue(location["created"] and location["modified"])
        self.assertEqual(
            {obj["relationship_type"] for obj in by_type["relationship"]},
            {"belongs-to", "located-at"},
        )


if __name__ == "__main__":
    unittest.main()