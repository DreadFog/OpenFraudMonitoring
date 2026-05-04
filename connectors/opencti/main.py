"""
OpenCTI connector entry point.

Reads its YAML config, then runs the shared `ConnectorRunner` which
consumes intel-lookup requests from RabbitMQ, calls the OpenCTI client,
and publishes the resulting STIX bundle back on the response queue.
"""

import logging
import os
import sys

# Make the shared connector_base package importable.
sys.path.insert(0, "/connectors/base")

from connector_base import load_config, ConnectorRunner  # noqa: E402

from opencti_client import OpenCTIClient  # noqa: E402


logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logging.getLogger('pika').setLevel(logging.INFO)
logger = logging.getLogger(__name__)

from connector_base.log_shipper import install as install_log_shipper  # noqa: E402
install_log_shipper("connector:opencti")


def main():
    config_path = os.environ.get("CONNECTOR_CONFIG", "/connectors/opencti/config.yml")
    cfg = load_config(config_path)
    if not cfg.name:
        cfg.name = "opencti"

    octi_url = cfg.params.get("opencti_url") or cfg.params.get("url")
    octi_token = cfg.params.get("opencti_token") or cfg.params.get("token")
    if not octi_url or not octi_token:
        logger.error("OpenCTI config missing url/token")
        sys.exit(1)

    ssl_verify = bool(cfg.params.get("ssl_verify", True))
    octi = OpenCTIClient(octi_url, octi_token, ssl_verify=ssl_verify)
    logger.info("OpenCTI connector ready (url=%s, mode=%s)", octi_url, cfg.mode)

    def handler(msg: dict) -> dict:
        request_type = msg.get("type", "ip_lookup")
        value = (msg.get("value") or "").strip()
        if request_type != "ip_lookup":
            logger.warning("Unsupported request type: %s", request_type)
            return {"type": "bundle", "objects": []}
        if not value:
            return {"type": "bundle", "objects": []}
        return octi.lookup_ip(value)

    runner = ConnectorRunner(cfg, handler)
    runner.run()


if __name__ == "__main__":
    main()
