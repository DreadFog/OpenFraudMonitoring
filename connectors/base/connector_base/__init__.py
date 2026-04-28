"""
Shared library used by every OpenFraudMonitoring connector container.

Public API:

    from connector_base import (
        load_config,            # load YAML + apply env overrides
        ConnectorRunner,        # main loop helper (consume requests, publish responses)
        BackendClient,          # HTTP client to POST results to the backend
    )
"""

from .config import load_config, ConnectorConfig
from .runner import ConnectorRunner
from .backend import BackendClient

__all__ = ["load_config", "ConnectorConfig", "ConnectorRunner", "BackendClient"]
