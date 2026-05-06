"""YAML-based configuration loader, with environment-variable overrides."""

import os
from dataclasses import dataclass, field
from typing import Any, Dict

import yaml


@dataclass
class ConnectorConfig:
    """Generic connector config fields.  Per-connector specifics are kept
    inside the ``params`` dict (untyped)."""
    name: str = ""
    mode: str = "manual"  # manual | auto | both
    connector_type: str = "enricher"  # enricher | importer | ...
    scope: list = field(default_factory=list)  # STIX entity types this connector can handle
    rabbitmq_url: str = "amqp://ofm:ofm@rabbitmq:5672/"
    backend_url: str = "http://backend:5000"
    admin_token: str = ""
    params: Dict[str, Any] = field(default_factory=dict)


def _from_env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def load_config(path: str) -> ConnectorConfig:
    """Load a YAML config file and overlay environment-variable overrides."""
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}

    cfg = ConnectorConfig(
        name=data.get("name", ""),
        mode=data.get("mode", "manual"),
        connector_type=data.get("connector_type", "enricher"),
        scope=data.get("scope", []),
        rabbitmq_url=data.get("rabbitmq_url", _from_env("RABBITMQ_URL", "amqp://ofm:ofm@rabbitmq:5672/")),
        backend_url=data.get("backend_url", _from_env("BACKEND_URL", "http://backend:5000")),
        admin_token=data.get("admin_token", _from_env("OFM_ADMIN_TOKEN", "")),
        params=data.get("params", {}) or {},
    )

    # Allow any top-level key besides the structural ones to be promoted
    # into params (so a connector can either define them flat or under params).
    structural = {"name", "mode", "connector_type", "scope", "rabbitmq_url", "backend_url", "admin_token", "params"}
    for k, v in data.items():
        if k not in structural and k not in cfg.params:
            cfg.params[k] = v

    return cfg
