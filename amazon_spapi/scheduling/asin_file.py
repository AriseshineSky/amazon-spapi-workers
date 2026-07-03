# -*- coding: utf-8 -*-
"""Read ASINs from plain-text or analytics TSV+JSON export files."""

from __future__ import annotations

import json
import re
from typing import Iterable, Iterator, List, Optional

from amazon_spapi.spapi.asin import is_asin_valid

_ASIN_IN_LINE_RE = re.compile(
    r"\b([A-Z0-9]{10}|[A-Z0-9]{9}X)\b",
    re.IGNORECASE,
)


def _normalize_asin(value: str) -> Optional[str]:
    asin = (value or "").strip().upper()
    if is_asin_valid(asin):
        return asin
    return None


def extract_asin_from_line(line: str, source_filter: str = "") -> Optional[str]:
    """Extract one ASIN from a file line.

    Supports:
    - plain ASIN per line
    - ``id<TAB>{json with source_product_id}`` analytics export
    - Amazon URL containing ``/dp/ASIN``
    """
    line = (line or "").strip()
    if not line or line.startswith("#"):
        return None

    if "\t" in line:
        _, payload = line.split("\t", 1)
        payload = payload.strip()
        if payload.startswith("{"):
            try:
                row = json.loads(payload)
            except json.JSONDecodeError:
                row = None
            if isinstance(row, dict):
                if source_filter:
                    source = str(row.get("source", "")).strip().upper()
                    if source != source_filter.strip().upper():
                        return None
                asin = _normalize_asin(str(row.get("source_product_id", "")))
                if asin:
                    return asin

    plain = _normalize_asin(line)
    if plain:
        return plain

    for match in _ASIN_IN_LINE_RE.finditer(line):
        asin = _normalize_asin(match.group(1))
        if asin:
            return asin
    return None


def iter_asins_from_file(
    path: str,
    *,
    source_filter: str = "",
    limit: Optional[int] = None,
) -> Iterator[str]:
    """Yield unique ASINs from ``path`` in file order."""
    seen = set()
    count = 0
    with open(path, encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            asin = extract_asin_from_line(line, source_filter=source_filter)
            if not asin or asin in seen:
                continue
            seen.add(asin)
            yield asin
            count += 1
            if limit is not None and count >= limit:
                return


def collect_asins_from_file(
    path: str,
    *,
    source_filter: str = "",
    limit: Optional[int] = None,
) -> List[str]:
    return list(
        iter_asins_from_file(path, source_filter=source_filter, limit=limit)
    )


def read_asin_batches(
    path: str,
    batch_size: int,
    *,
    source_filter: str = "",
    limit: Optional[int] = None,
) -> Iterable[List[str]]:
    batch: List[str] = []
    for asin in iter_asins_from_file(
        path, source_filter=source_filter, limit=limit
    ):
        batch.append(asin)
        if len(batch) >= batch_size:
            yield batch
            batch = []
    if batch:
        yield batch
