# -*- coding: utf-8 -*-
"""Resolve which Elasticsearch time fields to use for stream scans and range queries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Sequence, Tuple, Any

# Canonical + legacy ES field names (lowercase snake_case).
CREATED_AT = "created_at"
UPDATED_AT = "updated_at"
LEGACY_TIMESTAMP = "timestamp"
LEGACY_TIME = "time"
DATE = "date"

DEFAULT_STREAM_TIME_FIELD = "auto"

VALID_STREAM_TIME_FIELDS = (
    DEFAULT_STREAM_TIME_FIELD,
    UPDATED_AT,
    CREATED_AT,
    LEGACY_TIMESTAMP,
    LEGACY_TIME,
    DATE,
)

# Read fallback order when loading documents during migration.
LEGACY_EVENT_TIME_FIELDS = (DATE, UPDATED_AT, LEGACY_TIMESTAMP, LEGACY_TIME, CREATED_AT)


@dataclass(frozen=True)
class StreamTimeQuery:
    """Resolved time-field plan for scanning an ES index."""

    time_field: str
    index_name: str
    sort_key: str
    query_keys: Tuple[str, ...]

    @property
    def uses_legacy_fallback(self) -> bool:
        return len(self.query_keys) > 1


def normalize_stream_time_field(time_field: str) -> str:
    return (time_field or DEFAULT_STREAM_TIME_FIELD).strip().lower()


def validate_stream_time_field(time_field: str) -> str:
    normalized = normalize_stream_time_field(time_field)
    if normalized not in VALID_STREAM_TIME_FIELDS:
        raise ValueError(
            "stream time_field must be one of {}; got {!r}".format(
                ", ".join(VALID_STREAM_TIME_FIELDS),
                time_field,
            )
        )
    return normalized


def resolve_stream_time_field(time_field: str, index_name: str) -> str:
    """
    Resolve config ``time_field`` to the primary ES field used for sort.

    ``auto`` rules:
      - unified bucket indices -> ``updated_at``
      - ``user1_*_products`` catalog indices -> ``date``
      - index name contains ``keyword`` or ``missing`` -> ``time``
      - legacy ``amz_asins_{mp}_no_info`` / ``_no_offer`` -> ``time``
      - otherwise -> ``timestamp``
    """
    from amazon_spapi.amazon.delivery.bucket_indices import is_unified_bucket_index

    tf = normalize_stream_time_field(time_field)
    if tf != DEFAULT_STREAM_TIME_FIELD:
        return tf
    if is_unified_bucket_index(index_name):
        return UPDATED_AT
    name = (index_name or "").lower()
    if name.startswith("user1_") and name.endswith("_products"):
        return DATE
    if "keyword" in name:
        return LEGACY_TIME
    if "missing" in name:
        return LEGACY_TIME
    if name.endswith("_no_info") or name.endswith("_no_offer"):
        return LEGACY_TIME
    return LEGACY_TIMESTAMP


def stream_time_fields_for_query(time_field: str, index_name: str) -> Tuple[str, ...]:
    """Primary field plus legacy fallbacks for range queries during migration."""
    primary = resolve_stream_time_field(time_field, index_name)
    tf = normalize_stream_time_field(time_field)

    if tf not in (DEFAULT_STREAM_TIME_FIELD, UPDATED_AT, CREATED_AT):
        return (primary,)

    if primary == UPDATED_AT:
        fallbacks = (UPDATED_AT, LEGACY_TIMESTAMP, LEGACY_TIME, CREATED_AT)
    elif primary == CREATED_AT:
        fallbacks = (CREATED_AT, LEGACY_TIMESTAMP, UPDATED_AT, LEGACY_TIME)
    elif primary == DATE:
        fallbacks = (DATE, LEGACY_TIMESTAMP, UPDATED_AT, LEGACY_TIME, CREATED_AT)
    elif primary == LEGACY_TIME:
        fallbacks = (LEGACY_TIME, LEGACY_TIMESTAMP, UPDATED_AT, CREATED_AT)
    else:
        fallbacks = (LEGACY_TIMESTAMP, UPDATED_AT, LEGACY_TIME, CREATED_AT)

    fields = []
    for name in fallbacks:
        if name not in fields:
            fields.append(name)
    return tuple(fields)


def resolve_stream_time_query(time_field: str, index_name: str) -> StreamTimeQuery:
    normalized = normalize_stream_time_field(time_field)
    sort_key = resolve_stream_time_field(normalized, index_name)
    query_keys = stream_time_fields_for_query(normalized, index_name)
    return StreamTimeQuery(
        time_field=normalized,
        index_name=index_name or "",
        sort_key=sort_key,
        query_keys=query_keys,
    )


def _index_mapping_properties(esclient, index_name: str) -> Dict[str, Any]:
    try:
        mapping = esclient.indices.get_mapping(index=index_name)
    except Exception:
        return {}
    for _idx_name, body in mapping.items():
        return dict((body.get("mappings") or {}).get("properties") or {})
    return {}


def refine_stream_time_query(esclient, query: StreamTimeQuery) -> StreamTimeQuery:
    """Prefer time fields that exist in the index mapping (migration-safe)."""
    props = _index_mapping_properties(esclient, query.index_name)
    if not props:
        return query
    available = tuple(key for key in query.query_keys if key in props)
    if not available:
        return query
    return StreamTimeQuery(
        time_field=query.time_field,
        index_name=query.index_name,
        sort_key=available[0],
        query_keys=available,
    )


def build_time_range_clause(cut_time: str, time_keys: Sequence[str]) -> Dict:
    keys = tuple(time_keys)
    if not keys:
        raise ValueError("time_keys must not be empty")
    if len(keys) == 1:
        return {"range": {keys[0]: {"gt": cut_time}}}
    return {
        "bool": {
            "should": [{"range": {key: {"gt": cut_time}}} for key in keys],
            "minimum_should_match": 1,
        }
    }
