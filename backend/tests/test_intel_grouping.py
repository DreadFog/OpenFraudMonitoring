import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock, patch

from flask import Flask

from routes.intel import _build_entity_response


class FakeColumn:
    def __eq__(self, _other):
        return self

    def __or__(self, _other):
        return self

    def in_(self, _values):
        return self


class FakeEntity:
    def __init__(self, stix_type, stix_id, value, **properties):
        self.id = properties.pop("id", 1)
        self.stix_id = stix_id
        self.value = value
        self.revoked = False
        self.raw = {"type": stix_type, "id": stix_id, "value": value, **properties}

    def to_dict(self):
        return {
            "id": self.id,
            "stix_type": self.raw["type"],
            "stix_id": self.stix_id,
            "value": self.value,
            "raw": self.raw,
            "stix_object": self.raw,
            "platform": {"id": self.id},
        }


def relationship(stix_id, relationship_type, source_ref, target_ref, created_at_platform=None):
    return SimpleNamespace(
        stix_id=stix_id,
        relationship_type=relationship_type,
        source_ref=source_ref,
        target_ref=target_ref,
        start_time=None,
        stop_time=None,
        created_at_platform=created_at_platform,
        to_dict=lambda: {
            "stix_id": stix_id,
            "relationship_type": relationship_type,
            "source_ref": source_ref,
            "target_ref": target_ref,
            "platform": {},
        },
    )


class IntelligenceGroupingTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)

    def build_response(self, observable, direct, indirect, entities, session_summary=None):
        relationship_query = SimpleNamespace(
            filter=Mock(side_effect=[
                SimpleNamespace(all=lambda: direct),
                SimpleNamespace(all=lambda: indirect),
            ])
        )
        relationship_model = SimpleNamespace(
            query=relationship_query,
            source_ref=FakeColumn(),
            target_ref=FakeColumn(),
            relationship_type=FakeColumn(),
        )
        with self.app.app_context(), \
             patch("routes.intel.StixRelationship", relationship_model), \
             patch("routes.intel._resolve", side_effect=lambda sid: entities.get(sid)), \
             patch("routes.intel.apply_indicator_revocation"), \
             patch("routes.intel.get_revocation_days", return_value=7), \
             patch("routes.intel._session_summary", return_value=session_summary or {
                 "count": 0, "first_seen": None, "last_seen": None,
             }) as summarize:
            response = _build_entity_response(observable, observable.raw["type"])
        return response, summarize

    def test_sco_response_groups_context_and_keeps_other_relationships(self):
        ip = FakeEntity("ipv4-addr", "ipv4-addr--ip", "192.0.2.1", id=1)
        asn = FakeEntity("autonomous-system", "autonomous-system--as", "AS64512", id=2, number=64512)
        country = FakeEntity("location", "location--country", "FR", id=3, name="France")
        indicator = FakeEntity("indicator", "indicator--indicator", "pattern", id=4, name="Watchlist", pattern="[ipv4-addr:value = '192.0.2.1']", revoked=False)
        malware = FakeEntity("malware", "malware--malware", "Example", id=5, name="Example malware")
        campaign = FakeEntity("campaign", "campaign--campaign", "Campaign", id=6, name="Campaign")
        direct = [
            relationship("rel-as", "belongs-to", ip.stix_id, asn.stix_id),
            relationship("rel-country", "located-at", ip.stix_id, country.stix_id),
            relationship("rel-based", "based-on", indicator.stix_id, ip.stix_id),
            relationship("rel-other", "related-to", ip.stix_id, campaign.stix_id),
        ]
        indirect = [
            relationship("rel-indicates-malware", "indicates", indicator.stix_id, malware.stix_id,
                         datetime(2026, 1, 1)),
            relationship("rel-indicates-campaign", "indicates", indicator.stix_id, campaign.stix_id,
                         datetime(2026, 2, 1)),
        ]
        entities = {item.stix_id: item for item in (asn, country, indicator, malware, campaign)}

        response, summarize = self.build_response(
            ip, direct, indirect, entities,
            {"count": 3, "first_seen": 1000, "last_seen": 5000},
        )

        self.assertEqual(response["autonomous_system"]["stix_id"], asn.stix_id)
        self.assertEqual(response["country"]["stix_id"], country.stix_id)
        self.assertEqual(len(response["known_malicious_behavior"]), 1)
        behavior = response["known_malicious_behavior"][0]
        self.assertEqual(behavior["indicator"]["stix_id"], indicator.stix_id)
        self.assertEqual(
            {obj["stix_id"] for obj in behavior["indicates"]},
            {malware.stix_id, campaign.stix_id},
        )
        self.assertEqual(behavior["latest_indicated"]["entity"]["stix_id"], campaign.stix_id)
        self.assertEqual(behavior["latest_indicated"]["indicated_at"], "2026-02-01T00:00:00")
        self.assertEqual([rel["stix_id"] for rel in response["relationships"]], ["rel-other"])
        self.assertEqual(response["session_count"], 3)
        self.assertEqual(response["session_count_scope"], "this observable")
        summarize.assert_called_once()

    def test_indicator_response_reports_sco_scope_and_indicated_targets(self):
        indicator = FakeEntity("indicator", "indicator--indicator", "pattern", id=1, name="Watchlist", pattern="[ipv4-addr:value = '192.0.2.1']", valid_from="2026-01-01T00:00:00Z", valid_until="2026-12-31T00:00:00Z")
        ip = FakeEntity("ipv4-addr", "ipv4-addr--ip", "192.0.2.1", id=2)
        malware = FakeEntity("malware", "malware--malware", "Example", id=3, name="Example malware", description="Description")
        direct = [
            relationship("rel-based", "based-on", indicator.stix_id, ip.stix_id),
            relationship("rel-indicates", "indicates", indicator.stix_id, malware.stix_id),
        ]
        entities = {ip.stix_id: ip, malware.stix_id: malware}
        summary = {"count": 4, "first_seen": 1000, "last_seen": 9000}

        response, summarize = self.build_response(indicator, direct, [], entities, summary)

        self.assertEqual([obj["stix_id"] for obj in response["based_on_observables"]], [ip.stix_id])
        self.assertEqual([obj["stix_id"] for obj in response["indicates"]], [malware.stix_id])
        self.assertEqual(response["session_count"], 4)
        self.assertEqual(response["session_count_scope"], "based-on observable(s)")
        self.assertEqual(response["first_seen"], 1000)
        self.assertEqual(response["last_seen"], 9000)
        self.assertEqual(response["relationships"], [])
        summarize.assert_called_once_with(response["based_on_observables"])


if __name__ == "__main__":
    unittest.main()