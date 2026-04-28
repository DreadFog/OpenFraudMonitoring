"""HTTP client for the OpenFraudMonitoring backend API."""

import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class BackendClient:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.token = token

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def ingest_bundle(self, connector: str, value: str, stix_bundle: dict, request_id: Optional[str] = None) -> bool:
        """POST a STIX bundle to /api/intel/ingest.  Returns True on 2xx."""
        try:
            r = requests.post(
                f"{self.base_url}/api/intel/ingest",
                headers=self._headers(),
                json={
                    "connector": connector,
                    "value": value,
                    "stix_bundle": stix_bundle,
                    "request_id": request_id,
                },
                timeout=30,
            )
            if r.status_code >= 300:
                logger.warning("ingest failed: %s %s", r.status_code, r.text)
                return False
            return True
        except requests.RequestException as e:
            logger.error("ingest request failed: %s", e)
            return False
