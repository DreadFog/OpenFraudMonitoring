import unittest
from types import SimpleNamespace
from unittest.mock import patch

from services.device_matching import (
    CANONICAL_FIELDS, _best_of, assess_match, resolve_device, score_match,
)


class DeviceMatchingTests(unittest.TestCase):
    def setUp(self):
        self.reading = {
            "device_platform": "Win32",
            "browser_user_agent": "Chrome/145",
            "graphics_web_gl_renderer": "NVIDIA GeForce RTX 4060",
            "device_screen_resolution_width": 1920,
            "device_screen_resolution_height": 1080,
            "device_screen_resolution_pixel_depth": 24,
            "device_screen_resolution_color_depth": 24,
            "device_cpu_count": 16,
            "device_memory": 8,
            "locale_languages_language": "en-US",
        }
        self.device = SimpleNamespace(id=24, match_profile=dict(self.reading))

    def test_three_groups_match_despite_context_changes(self):
        incoming = dict(self.reading, locale_languages_language="fr-FR")
        evidence = assess_match(self.device, incoming)
        self.assertTrue(evidence["eligible"])
        self.assertEqual(evidence["matched_groups"], ["graphics_model", "display", "capacity"])
        self.assertEqual(score_match(self.device, incoming), 0.95)

    def test_rebuild_replays_uuid_and_fuzzy_links_with_latest_session_assignment(self):
        from migration_helpers.v1_2_to_v1_3.rebuild_devices import plan_rebuild

        def reading(fingerprint_id, session_id, cookie, **changes):
            data = dict(self.reading, **changes)
            data["_extensions"] = {"device_id": {"uuid": cookie}}
            return {"id": fingerprint_id, "session_id": session_id,
                    "timestamp": fingerprint_id, "data": data}

        rows = [reading(1, 10, "first"), reading(2, 11, "second"),
                reading(3, 12, "second", device_cpu_count=8),
                reading(4, 10, "third", device_cpu_count=8)]
        with patch("migration_helpers.v1_2_to_v1_3.rebuild_devices.Fingerprint.extract_fields", side_effect=lambda data: data):
            devices, cookies, assignments, clusters = plan_rebuild(rows, [])
        self.assertEqual(len(devices), 2)
        self.assertEqual(cookies["second"]["match_method"], "fuzzy")
        self.assertEqual(cookies["second"]["match_confidence"], 0.95)
        self.assertEqual(devices[0].match_profile["device_cpu_count"], 16)
        self.assertEqual(assignments, {10: 1, 11: 0, 12: 0})
        self.assertEqual(clusters[10], {0, 1})

    def test_rebuild_keeps_sparse_firefox_uuid_identities_separate(self):
        from migration_helpers.v1_2_to_v1_3.rebuild_devices import plan_rebuild

        rows = [{"id": index, "session_id": index, "timestamp": index,
                 "data": dict(self.reading, browser_user_agent="Firefox/156",
                              _extensions={"device_id": {"uuid": f"uuid-{index}"}})}
                for index in (1, 2)]
        with patch("migration_helpers.v1_2_to_v1_3.rebuild_devices.Fingerprint.extract_fields", side_effect=lambda data: data):
            devices, cookies, assignments, clusters = plan_rebuild(rows, [])
        self.assertEqual(len(devices), 2)
        self.assertNotEqual(assignments[1], assignments[2])

    def test_rebuild_prunes_ambiguous_sessions_only_when_requested(self):
        from migration_helpers.v1_2_to_v1_3.rebuild_devices import prepare_rebuild

        def reading(fingerprint_id, session_id, cookie, **changes):
            data = dict(self.reading, **changes)
            data["_extensions"] = {"device_id": {"uuid": cookie}}
            return {"id": fingerprint_id, "session_id": session_id,
                    "timestamp": fingerprint_id, "data": data}

        rows = [reading(1, 10, "first"), reading(2, 11, "second"),
                reading(3, 12, "second", device_cpu_count=8),
                reading(4, 10, "third", device_cpu_count=8)]
        with patch("migration_helpers.v1_2_to_v1_3.rebuild_devices.Fingerprint.extract_fields", side_effect=lambda data: data):
            unpruned = prepare_rebuild(rows, [], prune_ambiguous=False)
            pruned = prepare_rebuild(rows, [], prune_ambiguous=True)

        self.assertEqual(unpruned[4], [])
        self.assertEqual(set(unpruned[5]), {10})
        self.assertEqual(pruned[4], [10])
        self.assertEqual(pruned[3], {11: {0}, 12: {0}})

    def test_missing_group_never_qualifies(self):
        for key in ("graphics_web_gl_renderer", "device_screen_resolution_width", "device_memory"):
            with self.subTest(key=key):
                incoming = dict(self.reading)
                incoming.pop(key)
                self.assertFalse(assess_match(self.device, incoming)["eligible"])

    def test_software_and_generic_renderers_do_not_qualify(self):
        for renderer in ("SwiftShader Device (0x0000C0DE)", "llvmpipe LLVM 15",
                         "WebKit WebGL", "Intel", "ERROR", "unknown",
                         "Mesa 24.1", "ANGLE (AMD, AMD Radeon(TM) Graphics Direct3D11 vs_5_0 ps_5_0)"):
            with self.subTest(renderer=renderer):
                reading = dict(self.reading, graphics_web_gl_renderer=renderer)
                self.assertFalse(assess_match(SimpleNamespace(match_profile=reading), reading)["eligible"])

    def test_matching_model_can_supply_graphics_group(self):
        reading = dict(self.reading, graphics_web_gl_renderer="", browser_high_entropy_values_model="Pixel 9")
        self.assertTrue(assess_match(SimpleNamespace(match_profile=reading), reading)["eligible"])

    def test_generic_model_is_not_identifying(self):
        for model in ("Android", "Generic", "ERROR", "unknown"):
            reading = dict(self.reading, graphics_web_gl_renderer="", browser_high_entropy_values_model=model)
            self.assertFalse(assess_match(SimpleNamespace(match_profile=reading), reading)["eligible"])

    def test_informative_renderer_families(self):
        for renderer in ("Adreno (TM) 642L", "Mali-G78", "Apple M3",
                         "AMD Radeon RX 6800", "Intel(R) UHD Graphics 630"):
            reading = dict(self.reading, graphics_web_gl_renderer=renderer)
            self.assertTrue(assess_match(SimpleNamespace(match_profile=reading), reading)["eligible"])

    def test_internally_inconsistent_architecture_is_not_trusted(self):
        reading = dict(self.reading, device_platform="Linux armv81",
                       browser_high_entropy_values_architecture="x86")
        self.assertFalse(assess_match(SimpleNamespace(match_profile=reading), reading)["eligible"])

    def test_hardware_conflicts_override_matching_model(self):
        profile = dict(self.reading, browser_high_entropy_values_model="Pixel 9")
        incoming = dict(profile, graphics_web_gl_renderer="NVIDIA GeForce RTX 4070")
        self.assertFalse(assess_match(SimpleNamespace(match_profile=profile), incoming)["eligible"])

    def test_display_capacity_and_platform_conflicts_reject(self):
        for key, value in (("device_screen_resolution_width", 2560),
                           ("device_cpu_count", 8), ("device_platform", "MacIntel")):
            with self.subTest(key=key):
                self.assertFalse(assess_match(self.device, dict(self.reading, **{key: value}))["eligible"])

    def test_firefox_is_uncertain_on_either_side(self):
        firefox = dict(self.reading, browser_user_agent="Firefox/156")
        self.assertFalse(assess_match(self.device, firefox)["eligible"])
        self.assertFalse(assess_match(SimpleNamespace(match_profile=firefox), self.reading)["eligible"])

    def test_invalid_numeric_values_do_not_qualify(self):
        for value in (0, -1, True, float("nan"), float("inf"), "ERROR"):
            with self.subTest(value=value):
                self.assertFalse(assess_match(self.device, dict(self.reading, device_memory=value))["eligible"])

    def test_device24_generic_firefox_readings_are_not_identity(self):
        reading = dict(self.reading, device_platform="Linux armv81",
                       browser_user_agent="Firefox/155", graphics_web_gl_renderer="")
        device = SimpleNamespace(match_profile=reading, recent_ips=["192.0.2.1"])
        self.assertEqual(score_match(device, reading, "192.0.2.2"), 0)

    def test_legacy_canonical_fields_are_not_a_trusted_profile(self):
        legacy = SimpleNamespace(**{attr: self.reading.get(key) for attr, key in CANONICAL_FIELDS})
        self.assertEqual(score_match(legacy, self.reading), 0)

    def test_ambiguous_candidates_are_not_merged(self):
        other = SimpleNamespace(id=25, match_profile=dict(self.reading))
        self.assertEqual(_best_of([self.device, other], self.reading, None), (None, 0))
        self.assertEqual(_best_of([self.device], self.reading, None), (self.device, 0.95))

    def test_known_alias_preserves_confidence_and_profile(self):
        self.device.cookie_id = "primary"
        self.device.confidence = 0.95
        self.device.recent_ips = []
        link = SimpleNamespace(device=self.device, match_confidence=0.95, last_seen=1)
        incoming = dict(self.reading, device_cpu_count=8)
        with patch("services.device_matching.DeviceCookie") as cookies, \
                patch("services.device_matching.db"):
            cookies.query.filter_by.return_value.first.return_value = link
            with self.assertLogs("services.device_matching", level="WARNING"):
                device, confidence = resolve_device(incoming, cookie_id="known", timestamp=2)
        self.assertIs(device, self.device)
        self.assertEqual(confidence, 0.95)
        self.assertEqual(device.match_profile, self.reading)
        self.assertEqual(link.last_seen, 2)

    def test_new_device_is_flushed_before_alias_and_profile_is_coherent(self):
        with patch("services.device_matching.DeviceCookie") as cookies, \
                patch("services.device_matching.Device") as devices, \
                patch("services.device_matching.db") as database:
            cookies.query.filter_by.return_value.first.return_value = None
            devices.query.filter_by.return_value.first.return_value = None
            devices.query.filter_by.return_value.all.return_value = []
            devices.return_value = SimpleNamespace(id=None, cookie_id=None, recent_ips=[])
            database.session.flush.side_effect = lambda: setattr(devices.return_value, "id", 30)
            device, confidence = resolve_device(self.reading, cookie_id="new", timestamp=2)
            self.assertEqual(device.id, 30)
            self.assertEqual(confidence, 1)
            self.assertEqual(device.match_profile["device_cpu_count"], 16)
            self.assertEqual(device.cpu_count, 16)
            self.assertEqual(device.memory, 8)
            cookies.assert_called_once_with(
                device_id=30, cookie_id="new", first_seen=2,
                match_confidence=1.0, match_method="created", match_evidence={},
            )

    def test_new_alias_records_fuzzy_evidence_without_canonical_overwrite(self):
        self.device.cookie_id = "primary"
        self.device.recent_ips = []
        with patch("services.device_matching.DeviceCookie") as cookies, \
                patch("services.device_matching.Device") as devices, \
                patch("services.device_matching.db"):
            cookies.query.filter_by.return_value.first.return_value = None
            devices.query.filter_by.return_value.first.return_value = None
            devices.query.filter_by.return_value.all.return_value = [self.device]
            device, confidence = resolve_device(self.reading, cookie_id="new", timestamp=2)
            self.assertIs(device, self.device)
            self.assertEqual(confidence, 0.95)
            self.assertEqual(cookies.call_args.kwargs["match_method"], "fuzzy")
            self.assertTrue(cookies.call_args.kwargs["match_evidence"]["eligible"])
            self.assertEqual(device.match_profile, self.reading)
            devices.assert_not_called()

    def test_ambiguous_resolution_creates_new_device(self):
        other = SimpleNamespace(id=25, match_profile=dict(self.reading))
        with patch("services.device_matching.DeviceCookie") as cookies, \
                patch("services.device_matching.Device") as devices, \
                patch("services.device_matching.db"):
            cookies.query.filter_by.return_value.first.return_value = None
            devices.query.filter_by.return_value.first.return_value = None
            devices.query.filter_by.return_value.all.return_value = [self.device, other]
            devices.return_value = SimpleNamespace(id=30, cookie_id=None, recent_ips=[])
            device, confidence = resolve_device(self.reading, cookie_id="new", timestamp=2)
            self.assertEqual(device.id, 30)
            self.assertEqual(confidence, 1)

    def test_insufficient_reading_does_not_query_candidates(self):
        with patch("services.device_matching.Device") as devices, \
                patch("services.device_matching.db"):
            devices.return_value = SimpleNamespace(id=30, cookie_id=None, recent_ips=[])
            resolve_device(dict(self.reading, device_memory=0))
            devices.query.filter_by.assert_not_called()

    def test_device_detail_exposes_hardware_and_creation_profile(self):
        from flask import Flask
        from routes.devices import get_device_detail

        device = SimpleNamespace(
            id=24, platform="Win32", screen_width=1920, screen_height=1080,
            webgl_renderer="NVIDIA GeForce RTX 4060", device_type="workstation",
            is_mobile=False, confidence=0.95, cookie_id="known", first_seen=1,
            last_seen=2, cpu_count=16, memory=8, match_profile=dict(self.reading),
            pixel_depth=24, color_depth=24, speakers=0, microphones=1, webcams=1,
            webgl_vendor="NVIDIA", hev_architecture="x86", hev_bitness="64",
            hev_model="", hev_platform="Windows", hev_platform_version="",
            timezone="Europe/Paris", language="en-US", recent_ips=[],
        )
        with Flask(__name__).app_context(), \
                patch("routes.devices.Device") as devices, \
                patch("routes.devices.Session") as sessions:
            devices.query.get.return_value = device
            sessions.query.filter_by.return_value.order_by.return_value.all.return_value = []
            response, status = get_device_detail.__wrapped__(24)
            self.assertEqual(status, 200)
            summary = response.get_json()
            self.assertEqual(summary["cpu_count"], 16)
            self.assertEqual(summary["memory"], 8)
            self.assertEqual(summary["match_profile"], self.reading)
            device.match_profile = None
            response, status = get_device_detail.__wrapped__(24)
            self.assertEqual(response.get_json()["match_profile"], {})


if __name__ == "__main__":
    unittest.main()