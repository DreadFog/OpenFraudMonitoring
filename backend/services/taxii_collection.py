"""Collection filtering, object retrieval, and keyset pagination for TAXII."""

from __future__ import annotations

import heapq
import base64
import binascii
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterator

from sqlalchemy import and_, func, or_

from models import StixRelationship, TaxiiFeed
from services.indicator_revocation import refresh_indicator_revocation
from services.stix_filters import TYPE_TO_MODEL, apply_filters


DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 1000
MAX_CONTENT_LENGTH = 10 * 1024 * 1024
SUPPORTED_TYPES = tuple(TYPE_TO_MODEL) + ("relationship",)
_DB_BATCH_SIZE = 500
VERSION_KEYWORDS = {"first", "last", "all"}


@dataclass
class TaxiiQuery:
    limit: int = DEFAULT_PAGE_SIZE
    added_after: datetime | None = None
    cursor: tuple[datetime, str] | None = None
    match: dict[str, list[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class TaxiiRecord:
    date_added: datetime
    stix_id: str
    version: str
    spec_version: str
    raw: dict

    @property
    def sort_key(self) -> tuple[datetime, str]:
        return self.date_added, self.stix_id


def _model_for_type(stix_type: str):
    return StixRelationship if stix_type == "relationship" else TYPE_TO_MODEL.get(stix_type)


def _date_added_column(model):
    if hasattr(model, "last_refreshed_at"):
        return func.coalesce(model.last_refreshed_at, model.created_at_platform)
    return model.created_at_platform


def _to_naive_utc(value: datetime) -> datetime:
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def parse_timestamp(value) -> datetime | None:
    if not isinstance(value, str) or "T" not in value:
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00").replace("z", "+00:00"))
    except ValueError:
        return None
    return _to_naive_utc(parsed)


def format_timestamp(value: datetime) -> str:
    return _to_naive_utc(value).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def record_from_row(row) -> TaxiiRecord:
    raw = row.raw if isinstance(row.raw, dict) else {}
    if row.stix_id.startswith("indicator--"):
        raw = {**raw, "revoked": bool(getattr(row, "revoked", False) or raw.get("revoked"))}
    date_added = getattr(row, "last_refreshed_at", None) or row.created_at_platform
    version = raw.get("modified") or raw.get("created")
    if not isinstance(version, str) or parse_timestamp(version) is None:
        version = format_timestamp(row.created_at_platform)
    return TaxiiRecord(
        date_added=_to_naive_utc(date_added),
        stix_id=row.stix_id,
        version=version,
        spec_version=str(raw.get("spec_version") or "2.1"),
        raw=raw,
    )


def feed_types(feed: TaxiiFeed) -> list[str]:
    configured = {str(item).strip().lower() for item in (feed.object_types or []) if str(item).strip()}
    if not configured:
        return list(SUPPORTED_TYPES)
    return [stix_type for stix_type in SUPPORTED_TYPES if stix_type in configured]


def _iter_model_records(
    feed: TaxiiFeed,
    stix_type: str,
    ids: list[str] | None,
    added_after: datetime | None,
    cursor: tuple[datetime, str] | None,
) -> Iterator[TaxiiRecord]:
    model = _model_for_type(stix_type)
    if model is None:
        return
    query = model.query
    if feed.filters:
        query, error = apply_filters(query, stix_type, feed.filters, getattr(feed, "filter_logic", "AND"))
        if error:
            return

    date_added = _date_added_column(model)
    stix_id = model.stix_id.collate("C")
    if ids:
        query = query.filter(model.stix_id.in_(ids))
    if added_after is not None:
        query = query.filter(date_added > added_after)
    query = query.order_by(date_added.asc(), stix_id.asc())

    position = cursor
    while True:
        page = query
        if position is not None:
            ts, sid = position
            page = page.filter(or_(date_added > ts, and_(date_added == ts, stix_id > sid)))
        rows = page.limit(_DB_BATCH_SIZE).all()
        for row in rows:
            record = record_from_row(row)
            yield record
            position = record.sort_key
        if len(rows) < _DB_BATCH_SIZE:
            return


def record_sources(
    feed: TaxiiFeed,
    types: list[str],
    ids: list[str] | None = None,
    added_after: datetime | None = None,
    cursor: tuple[datetime, str] | None = None,
) -> list[Iterator[TaxiiRecord]]:
    return [_iter_model_records(feed, stix_type, ids, added_after, cursor) for stix_type in types]


def _version_matches(record: TaxiiRecord, versions: list[str] | None) -> bool:
    if not versions:
        return True
    record_version = parse_timestamp(record.version)
    for value in versions:
        if value in VERSION_KEYWORDS:
            return True
        if record_version is not None and parse_timestamp(value) == record_version:
            return True
    return False


def _spec_version_matches(record: TaxiiRecord, spec_versions: list[str] | None) -> bool:
    return not spec_versions or record.spec_version in spec_versions


@dataclass
class Page:
    records: list[TaxiiRecord]
    more: bool

    @property
    def next(self) -> str | None:
        if not self.more or not self.records:
            return None
        last = self.records[-1]
        return encode_cursor(last.date_added, last.stix_id)

    @property
    def headers(self) -> dict:
        if not self.records:
            return {}
        return {
            "X-TAXII-Date-Added-First": format_timestamp(self.records[0].date_added),
            "X-TAXII-Date-Added-Last": format_timestamp(self.records[-1].date_added),
        }


def encode_cursor(date_added: datetime, stix_id: str) -> str:
    payload = json.dumps({"ts": format_timestamp(date_added), "sid": stix_id}, separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")


def decode_cursor(cursor: str) -> tuple[datetime, str] | None:
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8"))
    except (ValueError, UnicodeError, binascii.Error):
        return None
    if not isinstance(payload, dict):
        return None
    ts = parse_timestamp(payload.get("ts"))
    sid = payload.get("sid")
    if ts is None or not isinstance(sid, str) or not sid:
        return None
    return ts, sid


def fetch_page(
    feed: TaxiiFeed,
    query: TaxiiQuery,
    *,
    object_id: str | None = None,
    whole_date_groups: bool = False,
) -> Page:
    """Return one page of matching records ordered by (date_added, id)."""
    types = feed_types(feed)
    if "indicator" in types:
        refresh_indicator_revocation()
    requested_types = query.match.get("type")
    if requested_types:
        types = [stix_type for stix_type in types if stix_type in requested_types]
    ids = [object_id] if object_id else query.match.get("id")
    if ids:
        prefixes = {item.split("--", 1)[0] for item in ids}
        types = [stix_type for stix_type in types if stix_type in prefixes]

    sources = record_sources(feed, types, ids, query.added_after, query.cursor)
    merged = heapq.merge(*sources, key=lambda record: record.sort_key)
    versions = query.match.get("version")
    spec_versions = query.match.get("spec_version")
    records: list[TaxiiRecord] = []
    more = False
    for record in merged:
        if not _version_matches(record, versions) or not _spec_version_matches(record, spec_versions):
            continue
        if len(records) >= query.limit:
            more = True
            if whole_date_groups:
                kept = [item for item in records if item.date_added != record.date_added]
                if kept:
                    records = kept
            break
        records.append(record)
    return Page(records=records, more=more)
