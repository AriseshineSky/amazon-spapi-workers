# -*- coding: utf-8 -*-
"""Canonical created/updated timestamps for Elasticsearch documents."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional

from amazon_spapi.services.es_time_field import (
    CREATED_AT,
    LEGACY_EVENT_TIME_FIELDS,
    LEGACY_TIME,
    LEGACY_TIMESTAMP,
    UPDATED_AT,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_document_times(now: Optional[datetime] = None) -> Dict[str, datetime]:
    ts = now or utc_now()
    return {CREATED_AT: ts, UPDATED_AT: ts}


def mirror_legacy_timestamp(
    doc: Dict[str, Any],
    event_time: Optional[Any] = None,
) -> Dict[str, Any]:
    """Keep legacy ``timestamp`` aligned with ``updated_at`` for old readers."""
    ts = event_time if event_time is not None else doc.get(UPDATED_AT)
    if ts is None:
        ts = doc.get(CREATED_AT)
    if ts is not None:
        doc[LEGACY_TIMESTAMP] = ts
    return doc


def apply_write_timestamps(
    doc: Dict[str, Any],
    now: Optional[datetime] = None,
    *,
    created_at: Optional[Any] = None,
    mirror_legacy: bool = True,
) -> Dict[str, Any]:
    ts = now or utc_now()
    doc[UPDATED_AT] = ts
    if created_at is not None:
        doc[CREATED_AT] = created_at
    elif CREATED_AT not in doc:
        doc[CREATED_AT] = ts
    if mirror_legacy:
        mirror_legacy_timestamp(doc, ts)
    return doc


def document_event_time(doc: Mapping[str, Any]) -> Optional[Any]:
    """Best-effort event time for range queries and sorting."""
    for key in LEGACY_EVENT_TIME_FIELDS:
        value = doc.get(key)
        if value:
            return value
    return None


def coalesce_created_at(
    *,
    existing: Optional[Mapping[str, Any]] = None,
    incoming: Optional[Mapping[str, Any]] = None,
    default: Optional[datetime] = None,
) -> datetime:
    for source in (existing, incoming):
        if not source:
            continue
        for key in (CREATED_AT, LEGACY_TIMESTAMP, LEGACY_TIME):
            value = source.get(key)
            if value:
                if isinstance(value, datetime):
                    return value
                return value  # ES may return ISO strings
    return default or utc_now()
