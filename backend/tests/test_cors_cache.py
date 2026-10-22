import unittest
from unittest.mock import patch

from services.cors_origins import (
    _active_origin_patterns,
    invalidate_origin_cache,
    is_origin_allowed,
)


class CorsOriginCacheTests(unittest.TestCase):
    def tearDown(self):
        invalidate_origin_cache()

    def test_queries_active_origins_once_until_invalidated(self):
        with patch("services.cors_origins.AllowedOrigin") as model:
            query = model.query.filter_by.return_value.with_entities.return_value
            query.all.return_value = [("https://first.example",), ("*.first.example",)]

            self.assertTrue(is_origin_allowed("https://first.example"))
            self.assertTrue(is_origin_allowed("https://sub.first.example"))
            model.query.filter_by.assert_called_once_with(active=True)

            query.all.return_value = [("https://second.example",)]
            invalidate_origin_cache()

            self.assertFalse(is_origin_allowed("https://first.example"))
            self.assertTrue(is_origin_allowed("https://second.example"))
            self.assertEqual(model.query.filter_by.call_count, 2)

    def test_empty_origins_are_cached_and_invalidation_clears_cache(self):
        with patch("services.cors_origins.AllowedOrigin") as model:
            query = model.query.filter_by.return_value.with_entities.return_value
            query.all.return_value = []

            self.assertEqual(_active_origin_patterns(), ())
            self.assertEqual(_active_origin_patterns(), ())
            model.query.filter_by.assert_called_once_with(active=True)

            invalidate_origin_cache()
            _active_origin_patterns()
            self.assertEqual(model.query.filter_by.call_count, 2)


if __name__ == "__main__":
    unittest.main()
