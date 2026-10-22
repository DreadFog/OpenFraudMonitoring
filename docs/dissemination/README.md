# Disseminating OFM blocklists to nftables

[update_nftables.py](update_nftables.py) is a standalone Python 3.10+ script using
only the standard library. It fetches OFM CSV full snapshots and atomically
replaces its own `inet ofm_blocklist` table. No Caddy restart is needed. Use
nftables 1.0.9 or newer (the script uses `destroy table`, including on first run).

## Host inspection

On 2026-10-22, the inspected host had:

- `/usr/bin/nft`, nftables 1.1.6, and Python 3.14.6.
- An inactive, disabled `nftables.service`.
- A saved `/etc/nftables.conf` with default-drop input and forward policies.
  This file is not the current live ruleset.
- Live Docker/iptables-nft IPv4 and IPv6 NAT/filter tables, and an IPv4 raw table.
  Several Docker services publish host ports, including OFM on TCP 5000.

An inactive nftables service does **not** mean the kernel has no firewall rules.
Do not enable the service or load the saved configuration without reviewing its
effect on Docker and remote access. The updater does not change service settings,
the saved configuration, or Docker's tables.

## Traffic and safety

The requested scope is **all incoming packets from listed source IPs**, not just
HTTP(S). An IPv4/IPv6 prerouting hook at priority `-310` drops matching packets
before connection tracking and destination NAT, covering host services and
Docker-published ports. It also affects established traffic and routed traffic;
there is no established-connection bypass. Replies from blocked remote servers
will also be dropped, even if this host initiated the connection.

Loopback traffic and the RFC 1918 private IPv4 ranges (`10.0.0.0/8`,
`172.16.0.0/12`, and `192.168.0.0/16`) are allowlisted by default. This covers
only `172.16` through `172.31`, not all `172.*` addresses.
`ALLOWLIST` entries bypass this script's block rules,
including when contained inside a blocked CIDR; they do not bypass other firewall
tables. Add management/VPN addresses and, where necessary, the OFM server's IPs
before activation. Other firewall tables can still drop packets.

This assumes the host sees the real visitor's network source address. Behind a
CDN or another proxy, nftables sees that intermediary's address, not
`X-Forwarded-For`; use application/proxy enforcement for those visitor IPs.

All configured feeds must download and validate successfully before any firewall
change. Network, authentication, malformed-data, oversized-response, and nft
validation failures exit nonzero and retain the previous table. Each replacement
is one nft transaction; only the dedicated table is destroyed/recreated, with no
unprotected interval. Counters reset on successful replacement. Do not put manual
rules in that table.

**A valid empty snapshot clears the corresponding set**, as requested. Removing
an address family from `FEEDS` also clears that family's set on the next update.
The updater does not merge incremental batches or retain addresses absent from
the latest snapshot.

## Configure OFM

In **Exports**, create one feed per required address family:

| Option | Value |
| --- | --- |
| Format | CSV |
| Entity type | `ipv4-addr`, `ipv6-addr`, or `indicator` |
| Export columns | Only `value` for IP observables; only `name` for indicators |
| Auto-update (incremental) | **Off** |
| Include headers | Either (read from feed metadata) |
| Delimiter | Any supported CSV delimiter |
| Public | Off recommended |
| Filters | Explicitly select only the addresses you intend to block |

Auto-update off still evaluates current matches on **every download**; cron
controls the polling interval. Incremental feeds are rejected because they omit
existing matches and removals.

For indicator feeds, each `name` must contain only an IP address or canonical
CIDR, not a descriptive label or STIX pattern. The script validates every cell
with Python's `ipaddress` module and checks the address family against the
`FEEDS` key (`4` or `6`). Hostnames, malformed addresses, scoped IPv6 addresses,
wrong-family addresses, extra columns, and CIDRs with host bits are rejected.
A single invalid row aborts the entire update, preserving the current rules;
invalid rows are never silently skipped. Optional CSV headers must match the
selected column (`value` or `name`). Separate IPv4/IPv6 indicator feeds using
appropriate OFM filters.

Indicator names are treated as your authoritative blocking decisions; the script
does not parse STIX patterns or independently check revocation/expiry. Configure
the indicator feed filters to exclude revoked indicators (and any other
indicators you do not intend to block).

An IP observable is not automatically malicious. Exporting all observed IPs
would block legitimate visitors. Current IP export filters are observable fields,
not arbitrary session-risk or relationship queries; confirm that your selection
expresses the desired blocking policy. See [exports](../architecture.md#csv-and-taxii-exports).

Create a dedicated API token in **Profile**, preferably for a non-admin user.
Feed downloads and metadata listing accept that user's Bearer API token. Use
the UUID in `/api/csv/<uuid>/`, not the numeric management ID. The script
reads `/api/taxii-feeds` first to reject incompatible feed configurations.

## Install and privileges

Run the installed script as **root**, from **root's crontab**. Kernel firewall
management requires `CAP_NET_ADMIN`; this script deliberately requires effective
UID 0 for check/apply modes. Reading private feeds requires an OFM API token,
not an OFM administrator password. `--dry-run` does not require root.

Install a separate protected copy, from the repository root:

```sh
sudo install -o root -g root -m 0700 docs/dissemination/update_nftables.py /usr/local/sbin/ofm-update-nftables.py
sudoedit /usr/local/sbin/ofm-update-nftables.py
```

Edit `OFM_URL`, `API_TOKEN`, `FEEDS`, and `ALLOWLIST` at the top of the installed
copy. Authentication is hardcoded in that one file; **never put a real token in
the repository copy or commit it**. Keep the installed file and parent directory
root-owned and not writable by other users. Do not run a user-writable repository
checkout as root from cron.

HTTPS certificate verification is enabled. Plain HTTP is allowed only with
`localhost`, `127.0.0.1`, or `::1`, for a directly published local OFM backend.
Redirects and environment HTTP proxies are disabled to avoid forwarding the
token elsewhere. Configure the final URL; path prefixes are supported.

Validate before activation, while retaining a separate management session:

```sh
sudo /usr/bin/python3 /usr/local/sbin/ofm-update-nftables.py --dry-run
sudo /usr/bin/python3 /usr/local/sbin/ofm-update-nftables.py --check
sudo /usr/bin/python3 /usr/local/sbin/ofm-update-nftables.py
sudo nft list table inet ofm_blocklist
```

`--dry-run` fetches and prints the generated rules without invoking nft.
`--check` additionally asks the kernel to validate the transaction without
applying it. Neither mode tests your ability to reconnect; verify allowed
management access and a blocked test source separately before scheduling.

## Cron and reboot behavior

After a successful manual test, use `sudo crontab -e`:

```cron
*/5 * * * * /usr/bin/python3 /usr/local/sbin/ofm-update-nftables.py >> /var/log/ofm-nftables.log 2>&1
@reboot /usr/bin/python3 /usr/local/sbin/ofm-update-nftables.py >> /var/log/ofm-nftables.log 2>&1
```

A nonblocking lock at `/run/ofm-nftables.lock` prevents overlapping check/apply
runs; overlap exits nonzero and logs an explicit error. Do not delete the lock
file during a run. Logs contain timestamps and success/error status, not the
token. Monitor and rotate the log with your usual host tooling.

Rules remain in the kernel between cron runs, but **do not survive reboot**.
The reboot job may fail before networking/OFM is ready; periodic execution will
retry. Until the first successful run after boot there is no OFM blocking.
If boot-time enforcement during OFM outages is required, add a separately
reviewed persistent last-known-good rules mechanism; this script does not
overwrite `/etc/nftables.conf` or persist a broad host ruleset.

For emergency removal, first disable the cron entries, then remove only this
table:

```sh
sudo nft delete table inet ofm_blocklist
```

Never use `nft flush ruleset`: that would also remove Docker and unrelated rules.

## Development validation

Run the focused tests from the repository root, without root or firewall access:

```sh
python3 -B -m unittest discover -s tests -p test_nftables_dissemination.py -v
```

During implementation, real nft check/apply transactions and HTTP-to-firewall
updates were also tested inside a separate user/network namespace. First
installation, replacement, IPv4/IPv6 CIDRs, empty snapshots, retention on HTTP
failure, and preservation of an unrelated table passed. The host's live firewall
was not changed. Real OFM credentials/feed selection and external-client blocking
still need validation during deployment.
