import csv
import io
import json
from datetime import datetime, timedelta

from models import StixRelationship, TaxiiFeed
from services.database import db
from services.indicator_revocation import refresh_indicator_revocation
from services.stix_filters import TYPE_TO_MODEL, apply_filters
from services.stix_objects import export_field_names


def validate_feed_options(body, feed=None):
    defaults = {
        "export_format": "taxii", "is_public": False, "include_headers": True,
        "auto_update": False, "update_interval_minutes": 60, "export_fields": [],
        "filter_logic": "AND", "csv_delimiter": ",",
    }
    options = {key: body.get(key, getattr(feed, key, default) if feed else default)
               for key, default in defaults.items()}
    if options["export_format"] not in ("csv", "taxii"):
        raise ValueError("export_format must be csv or taxii")
    if options["csv_delimiter"] not in (",", ";", "\t", "|"):
        raise ValueError("csv_delimiter must be comma, semicolon, tab or pipe")
    for key in ("is_public", "include_headers", "auto_update"):
        if not isinstance(options[key], bool):
            raise ValueError(f"{key} must be a boolean")
    interval = options["update_interval_minutes"]
    if isinstance(interval, bool) or not isinstance(interval, int) or not 1 <= interval <= 525600:
        raise ValueError("update_interval_minutes must be an integer between 1 and 525600")
    if options["filter_logic"] not in ("AND", "OR"):
        raise ValueError("filter_logic must be AND or OR")
    if options["export_format"] == "taxii" and options["auto_update"]:
        raise ValueError("Scheduled incremental updates are supported only for CSV feeds")
    fields = options["export_fields"]
    if not isinstance(fields, list) or any(not isinstance(field, str) for field in fields):
        raise ValueError("export_fields must be an array of field names")
    types = body.get("object_types", getattr(feed, "object_types", []) if feed else [])
    if options["export_format"] == "csv":
        if not isinstance(types, list) or len(types) != 1:
            raise ValueError("CSV feeds require exactly one object type")
        if not fields or len(fields) != len(set(fields)):
            raise ValueError("Select at least one unique export field")
        if set(fields) - set(export_field_names(types[0])):
            raise ValueError("Unknown export field for the selected object type")
    return options


def matching_rows(feed):
    stix_type = feed.object_types[0]
    model = StixRelationship if stix_type == "relationship" else TYPE_TO_MODEL[stix_type]
    if stix_type == "indicator":
        refresh_indicator_revocation(commit=False)
    query, error = apply_filters(model.query, stix_type, feed.filters, feed.filter_logic)
    if error:
        raise ValueError(error)
    return query.order_by(model.stix_id).yield_per(500)


def render_csv(rows, fields, include_headers, delimiter=","):
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=delimiter)
    if include_headers:
        writer.writerow(fields)
    for row in rows:
        payload = row.to_dict()
        raw = payload["stix_object"]
        values = []
        for field in fields:
            value = payload.get(field) if field in ("stix_id", "value", "created_at_platform", "last_refreshed_at", "source_connector_id") else raw.get(field)
            if isinstance(value, (dict, list)):
                value = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
            elif isinstance(value, bool):
                value = "true" if value else "false"
            if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
                value = "'" + value
            values.append("" if value is None else value)
        writer.writerow(values)
    return output.getvalue()


def update_csv_batch(feed, now=None):
    now = now or datetime.utcnow()
    if feed.last_generated_at is not None and now < feed.last_generated_at + timedelta(minutes=feed.update_interval_minutes):
        return False
    previous = set(feed.matching_ids or [])
    current = set()
    additions = []
    for row in matching_rows(feed):
        current.add(row.stix_id)
        if row.stix_id not in previous:
            additions.append(row)
    feed.csv_content = render_csv(additions, feed.export_fields, feed.include_headers, getattr(feed, "csv_delimiter", ","))
    feed.matching_ids = sorted(current)
    feed.last_generated_at = now
    return True


def refresh_csv_feed(feed_id):
    feed = TaxiiFeed.query.filter_by(id=feed_id).with_for_update().first()
    if feed is None or not feed.is_active or feed.export_format != "csv" or not feed.auto_update:
        return feed
    try:
        update_csv_batch(feed)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return feed


def refresh_due_csv_feeds():
    ids = [feed_id for feed_id, in db.session.query(TaxiiFeed.id).filter_by(
        export_format="csv", auto_update=True, is_active=True,
    ).all()]
    for feed_id in ids:
        refresh_csv_feed(feed_id)