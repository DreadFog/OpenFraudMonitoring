"""
IPinfo connector entry point.

Reads its YAML config, then runs the shared `ConnectorRunner` which
consumes intel-lookup requests from RabbitMQ, calls the IPinfo API,
and publishes the resulting STIX bundle back on the response queue.
"""

import logging
import os
import sys

# Make the shared connector_base package importable.
sys.path.insert(0, "/connectors/base")

from connector_base import load_config, ConnectorRunner  # noqa: E402

from ipinfo_client import IPInfoClient  # noqa: E402


logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

from connector_base.log_shipper import install as install_log_shipper  # noqa: E402
install_log_shipper("connector:ipinfo")


def main():
    config_path = os.environ.get("CONNECTOR_CONFIG", "/connectors/ipinfo/config.yml")
    cfg = load_config(config_path)
    if not cfg.name:
        cfg.name = "ipinfo"

    token = cfg.params.get("ipinfo_token") or cfg.params.get("token")
    if not token:
        logger.error("IPinfo config missing token")
        sys.exit(1)

    client = IPInfoClient(token)
    logger.info("IPinfo connector ready (mode=%s)", cfg.mode)

    def handler(msg: dict) -> dict:
        request_type = msg.get("type", "ip_lookup")
        value = (msg.get("value") or "").strip()
        if request_type != "ip_lookup":
            logger.warning("Unsupported request type: %s", request_type)
            return {"type": "bundle", "objects": []}
        if not value:
            return {"type": "bundle", "objects": []}
        return client.lookup_ip(value)

    runner = ConnectorRunner(cfg, handler)
    runner.run()


if __name__ == "__main__":
    main()
