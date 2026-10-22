#!/usr/bin/env python3
"""Reconcile a dedicated nftables table with private OFM CSV snapshots."""

import argparse
import csv
import fcntl
import http.client
import io
import ipaddress
import json
import logging
import logging.handlers
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from contextlib import contextmanager


# Edit these in the installed, root-only copy, never with real secrets in Git.
OFM_URL = "https://ofm.example.com"
API_TOKEN = "REPLACE_WITH_OFM_API_TOKEN"
FEEDS = {
    4: "REPLACE_WITH_IPV4_FEED_UUID",
    # 6: "REPLACE_WITH_IPV6_FEED_UUID",
}
ALLOWLIST = (
    "127.0.0.0/8",
    "::1/128",
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
)  # Add other management/VPN/feed-server CIDRs.

NFT = "/usr/bin/nft"
TABLE = "ofm_blocklist"
LOCK = "/run/ofm-nftables.lock"
LOG_FILE = "/var/log/ofm-nftables.log"
LOG_RETENTION_DAYS = 14
TIMEOUT = 30
MAX_BYTES = 16 * 1024 * 1024
MAX_ROWS = 200_000


class UpdateError(Exception):
    pass


class NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise UpdateError("OFM redirected the request; configure its final URL")


def validate_config():
    parsed = urllib.parse.urlsplit(OFM_URL)
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise UpdateError("OFM_URL must be an HTTP(S) URL without credentials or query")
    if parsed.scheme == "http" and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
        raise UpdateError("Use HTTPS unless OFM is reached through host loopback")
    if not API_TOKEN or API_TOKEN.startswith("REPLACE_") or "\n" in API_TOKEN or "\r" in API_TOKEN:
        raise UpdateError("Set API_TOKEN in the installed copy")
    if not FEEDS or any(version not in (4, 6) for version in FEEDS):
        raise UpdateError("Configure at least one IPv4 or IPv6 feed")
    for feed_id in FEEDS.values():
        try:
            if str(uuid.UUID(feed_id)) != feed_id:
                raise ValueError("noncanonical UUID")
        except (ValueError, TypeError, AttributeError) as error:
            raise UpdateError("Each configured feed must have a valid UUID") from error
    try:
        if any("%" in value for value in ALLOWLIST):
            raise ValueError("scoped addresses are not supported")
        return [ipaddress.ip_network(value, strict=True) for value in ALLOWLIST]
    except ValueError as error:
        raise UpdateError("ALLOWLIST contains an invalid address or network") from error


def download(opener, path, media_type):
    request = urllib.request.Request(
        OFM_URL.rstrip("/") + path,
        headers={"Authorization": f"Bearer {API_TOKEN}", "Accept": media_type},
    )
    with opener.open(request, timeout=TIMEOUT) as response:
        if response.status != 200 or response.headers.get_content_type() != media_type:
            raise UpdateError(f"Expected HTTP 200 with {media_type}")
        if response.headers.get("X-OFM-Generated-At"):
            raise UpdateError("Scheduled CSV batches are not full snapshots")
        content = response.read(MAX_BYTES + 1)
        if len(content) > MAX_BYTES:
            raise UpdateError("OFM response exceeds MAX_BYTES")
        return content.decode("utf-8-sig")


def parse_csv(content, feed, version):
    reader = csv.reader(io.StringIO(content, newline=""), delimiter=feed["csv_delimiter"], strict=True)
    if feed["include_headers"] and next(reader, None) != feed["export_fields"]:
        raise UpdateError(f"CSV header must be exactly {feed['export_fields'][0]!r}")
    networks = []
    for index, row in enumerate(reader, 1):
        if index > MAX_ROWS:
            raise UpdateError("CSV exceeds MAX_ROWS")
        if len(row) != 1 or not row[0].strip() or "%" in row[0]:
            raise UpdateError(f"Invalid CSV row {index}: expected one IP or CIDR")
        try:
            network = ipaddress.ip_network(row[0].strip(), strict=True)
        except ValueError as error:
            raise UpdateError(f"Invalid IP or CIDR in CSV row {index}") from error
        if network.version != version:
            raise UpdateError(f"Wrong address family in IPv{version} feed at row {index}")
        networks.append(network)
    return list(ipaddress.collapse_addresses(networks))


def fetch_snapshots():
    # Do not send the credential through environment-configured HTTP proxies.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirects())
    metadata = json.loads(download(opener, "/api/taxii-feeds", "application/json"))
    if not isinstance(metadata, dict) or not isinstance(metadata.get("feeds"), list):
        raise UpdateError("Invalid feed metadata response")
    snapshots = {4: [], 6: []}
    for version, feed_id in FEEDS.items():
        matches = [
            feed for feed in metadata["feeds"]
            if isinstance(feed, dict) and feed.get("uuid") == feed_id
        ]
        if len(matches) != 1:
            raise UpdateError(f"IPv{version} feed was not found uniquely")
        feed = matches[0]
        if (
            feed.get("is_active") is not True
            or feed.get("export_format") != "csv"
            or feed.get("auto_update") is not False
            or (feed.get("object_types"), feed.get("export_fields")) not in (
                ([f"ipv{version}-addr"], ["value"]),
                (["indicator"], ["name"]),
            )
            or not isinstance(feed.get("include_headers"), bool)
            or feed.get("csv_delimiter") not in (",", ";", "\t", "|")
        ):
            raise UpdateError(
                f"IPv{version} feed must be an active CSV full snapshot exporting only "
                f"'value' from ipv{version}-addr or 'name' from indicator"
            )
        content = download(opener, f"/api/csv/{feed_id}/", "text/csv")
        snapshots[version] = parse_csv(content, feed, version)
    return snapshots


def build_batch(snapshots, allowlist):
    lines = [f"destroy table inet {TABLE}", f"table inet {TABLE} {{"]
    for version in (4, 6):
        allowed = list(ipaddress.collapse_addresses(
            network for network in allowlist if network.version == version
        ))
        for name, networks in ((f"blocked{version}", snapshots[version]), (f"allowed{version}", allowed)):
            lines.extend([
                f"    set {name} {{",
                f"        type ipv{version}_addr",
                "        flags interval",
            ])
            if networks:
                lines.append("        elements = { " + ", ".join(map(str, networks)) + " }")
            lines.append("    }")
    lines.extend([
        "    chain incoming {",
        "        type filter hook prerouting priority -310; policy accept;",
        '        iifname "lo" return',
        "        ip saddr @allowed4 return",
        "        ip6 saddr @allowed6 return",
        "        ip saddr @blocked4 counter drop",
        "        ip6 saddr @blocked6 counter drop",
        "    }",
        "}",
    ])
    return "\n".join(lines) + "\n"


def run_nft(batch, check=False):
    command = [NFT, "--check", "--file", "-"] if check else [NFT, "--file", "-"]
    result = subprocess.run(command, input=batch, text=True, capture_output=True, timeout=60, check=False)
    if result.returncode:
        raise UpdateError(f"nft {'check' if check else 'update'} failed: {result.stderr.strip()}")


@contextmanager
def update_lock():
    descriptor = os.open(LOCK, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    with os.fdopen(descriptor, "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise UpdateError("Another updater is running") from None
        yield


def prune_logs(now=None):
    """Delete rotated log files whose newest entry is older than the retention period."""
    cutoff = (time.time() if now is None else now) - LOG_RETENTION_DAYS * 86400
    directory, base = os.path.split(LOG_FILE)
    rotated = re.compile(re.escape(base) + r"\.\d{4}-\d{2}-\d{2}")
    for name in os.listdir(directory or "."):
        path = os.path.join(directory, name)
        if rotated.fullmatch(name) and os.path.isfile(path) and not os.path.islink(path) \
                and os.lstat(path).st_mtime < cutoff:
            os.unlink(path)


def setup_logging(to_file):
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    handlers = []
    if to_file:
        try:
            if os.path.islink(LOG_FILE):
                raise OSError(f"{LOG_FILE} must not be a symlink")
            os.umask(0o077)
            # Rotates daily (UTC); prune_logs enforces the age-based retention.
            handler = logging.handlers.TimedRotatingFileHandler(
                LOG_FILE, when="midnight", utc=True, backupCount=0, encoding="utf-8",
            )
            os.fchmod(handler.stream.fileno(), 0o600)
            prune_logs()
            handlers.append(handler)
        except OSError as error:
            print(f"Cannot use {LOG_FILE}: {error}", file=sys.stderr)
            to_file = False
    if not to_file or sys.stderr.isatty():
        handlers.append(logging.StreamHandler())
    for handler in handlers:
        handler.setFormatter(formatter)
    logging.basicConfig(level=logging.INFO, handlers=handlers, force=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Fetch and print rules, without root or nft")
    mode.add_argument("--check", action="store_true", help="Fetch and validate with nft, without applying")
    args = parser.parse_args()
    setup_logging(to_file=not args.dry_run and os.geteuid() == 0)
    try:
        allowlist = validate_config()
        if not args.dry_run and os.geteuid() != 0:
            raise UpdateError("Run as root (firewall updates require CAP_NET_ADMIN)")
        if args.dry_run:
            print(build_batch(fetch_snapshots(), allowlist), end="")
        else:
            with update_lock():
                snapshots = fetch_snapshots()
                batch = build_batch(snapshots, allowlist)
                run_nft(batch, check=True)
                if not args.check:
                    run_nft(batch)
                logging.info(
                    "%s: IPv4=%d IPv6=%d networks (empty snapshots clear sets)",
                    "Checked" if args.check else "Applied", len(snapshots[4]), len(snapshots[6]),
                )
    except (UpdateError, OSError, ValueError, csv.Error, urllib.error.URLError, http.client.HTTPException,
            subprocess.SubprocessError) as error:
        logging.error("%s", error)
        return 1
    except Exception:
        logging.exception("Unexpected failure")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
