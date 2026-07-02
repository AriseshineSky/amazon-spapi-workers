# -*- coding: utf-8 -*-
"""Unified Elasticsearch bucket index names (stream cleanup)."""

from __future__ import annotations

BUCKET_SUFFIXES = (
    "blacklist",
    "em",
    "unuploadable",
    "no_info",
    "no_offer",
    "pipeline_filtered",
    "invalid_offer",
    "to_upload",
)

BUCKET_SUFFIX_TO_INDEX = {
    suffix: "amz_asin_bucket_{}".format(suffix) for suffix in BUCKET_SUFFIXES
}


def normalize_marketplace(marketplace: str) -> str:
    return (marketplace or "").strip().lower()


def bucket_index_for_suffix(suffix: str) -> str:
    key = (suffix or "").strip().lower()
    index = BUCKET_SUFFIX_TO_INDEX.get(key)
    if not index:
        raise ValueError("unknown bucket suffix: {!r}".format(suffix))
    return index


def bucket_doc_id(marketplace: str, asin: str) -> str:
    return "{}:{}".format(normalize_marketplace(marketplace), asin)


def bucket_doc_ids(marketplace: str, asins) -> list:
    mp = normalize_marketplace(marketplace)
    return ["{}:{}".format(mp, asin) for asin in asins]


def is_unified_bucket_index(index_name: str) -> bool:
    return (index_name or "") in set(BUCKET_SUFFIX_TO_INDEX.values())
