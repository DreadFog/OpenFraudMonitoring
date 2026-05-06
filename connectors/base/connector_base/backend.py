"""HTTP client for the OpenFraudMonitoring backend API.

Supports self-registration: on first use the connector authenticates with
the bootstrap admin token, creates its own user (role=connector) and
API token, then uses its own token going forward.
"""

import json
import logging
import os
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class BackendClient:
    def __init__(self, base_url: str, admin_token: str, connector_name: str,
                 token_store_path: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.admin_token = admin_token
        self.connector_name = connector_name
        self.token_store_path = token_store_path or f"/tmp/ofm_connector_token_{connector_name}"
        self._token: Optional[str] = None
        self._registered = False

    def _load_saved_token(self) -> Optional[str]:
        try:
            if os.path.exists(self.token_store_path):
                with open(self.token_store_path, "r") as f:
                    return f.read().strip() or None
        except Exception:
            pass
        return None

    def _save_token(self, token: str) -> None:
        try:
            with open(self.token_store_path, "w") as f:
                f.write(token)
        except Exception as e:
            logger.warning("could not persist connector token: %s", e)

    def _validate_token(self, token: str) -> bool:
        try:
            r = requests.get(
                f"{self.base_url}/api/auth/me",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10,
            )
            return r.status_code == 200
        except requests.RequestException:
            return False

    def _ensure_registered(self) -> None:
        """Ensure the connector has its own API token, self-registering if needed."""
        if self._token and self._registered:
            return

        # 1. Try saved token
        saved = self._load_saved_token()
        if saved and self._validate_token(saved):
            self._token = saved
            self._registered = True
            logger.info("Connector %s: using saved API token", self.connector_name)
            return

        # 2. Self-register using admin token
        admin_headers = {
            "Authorization": f"Bearer {self.admin_token}",
            "Content-Type": "application/json",
        }

        # Create connector user (ignore 409 if already exists)
        try:
            r = requests.post(
                f"{self.base_url}/api/auth/users",
                headers=admin_headers,
                json={"username": self.connector_name, "role": "connector"},
                timeout=10,
            )
            if r.status_code == 201:
                user_data = r.json()
                user_id = user_data["id"]
                logger.info("Connector %s: created user (id=%s)", self.connector_name, user_id)
            elif r.status_code == 409:
                # User already exists, look up its id
                users_r = requests.get(
                    f"{self.base_url}/api/auth/users",
                    headers=admin_headers,
                    timeout=10,
                )
                users_r.raise_for_status()
                user_id = None
                for u in users_r.json():
                    if u["username"] == self.connector_name:
                        user_id = u["id"]
                        break
                if user_id is None:
                    raise RuntimeError(f"Connector {self.connector_name}: user exists but not found in list")
            else:
                raise RuntimeError(f"Connector {self.connector_name}: failed to create user: {r.status_code} {r.text}")
        except requests.RequestException as e:
            raise RuntimeError(f"Connector {self.connector_name}: registration request failed: {e}") from e

        # Create API token for the connector user
        try:
            r = requests.post(
                f"{self.base_url}/api/auth/users/{user_id}/tokens",
                headers=admin_headers,
                json={"name": f"{self.connector_name}-auto"},
                timeout=10,
            )
            if r.status_code != 201:
                raise RuntimeError(f"Connector {self.connector_name}: failed to create token: {r.status_code} {r.text}")
            token_data = r.json()
            self._token = token_data["token"]
            self._save_token(self._token)
            self._registered = True
            logger.info("Connector %s: self-registered with new API token", self.connector_name)
        except requests.RequestException as e:
            raise RuntimeError(f"Connector {self.connector_name}: token creation failed: {e}") from e

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._token or self.admin_token}",
            "Content-Type": "application/json",
        }

    def ingest_bundle(self, connector: str, value: str, stix_bundle: dict, request_id: Optional[str] = None) -> bool:
        """POST a STIX bundle to /api/intel/ingest.  Returns True on 2xx."""
        self._ensure_registered()
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
            if r.status_code == 401:
                # Token may have been revoked; re-register
                self._registered = False
                self._token = None
                self._ensure_registered()
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
