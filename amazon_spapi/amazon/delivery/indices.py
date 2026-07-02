# -*- coding: utf-8 -*-
"""Elasticsearch index names and mappings for delivery catalog fetch."""

from __future__ import annotations

_STORE_ONLY = {"type": "object", "enabled": False}
_KEYWORD = {"type": "keyword", "ignore_above": 512}
_TEXT_KEYWORD = {
    "type": "text",
    "fields": {"keyword": {"type": "keyword", "ignore_above": 512}},
}


def catalog_index_name(marketplace: str) -> str:
    """Destination index for delivery API catalog writes (v3, compact mapping)."""
    return "amz_products_api_{}_v3".format((marketplace or "").strip().lower())


def missing_index_name(marketplace: str) -> str:
    return "amz_products_missing_{}".format((marketplace or "").strip().lower())


def stats_index_name(marketplace: str = "") -> str:
    """Unified catalog worker stats index (all marketplaces; ``marketplace`` field on docs)."""
    del marketplace
    return "spapi_task_stats_catalog"


def default_asin_index_name(marketplace: str) -> str:
    return "amz_asins_{}_no_info".format((marketplace or "").strip().lower())


def default_no_offer_asin_index_name(marketplace: str) -> str:
    return "amz_asins_{}_no_offer".format((marketplace or "").strip().lower())


def default_unuploadable_asin_index_name(marketplace: str) -> str:
    return "amz_asins_{}_unuploadable".format((marketplace or "").strip().lower())


def default_invalid_offer_asin_index_name(marketplace: str) -> str:
    return "amz_asins_{}_invalid_offer".format((marketplace or "").strip().lower())


def catalog_index_settings() -> dict:
    """v3 mapping: index TTL/search scalars; store SP-API blobs without field explosion."""
    return {
        "settings": {
            "index.mapping.total_fields.limit": 256,
        },
        "mappings": {
            "dynamic": True,
            "properties": {
                "asin": {"type": "keyword"},
                "time": {"type": "date"},
                "title": _TEXT_KEYWORD,
                "brand": _KEYWORD,
                "manufacturer": _KEYWORD,
                "format": _KEYWORD,
                "weight": {"type": "float"},
                "item_weight": {"type": "float"},
                "item_package_weight": {"type": "float"},
                "lwh": {"type": "long"},
                "sales_rank": {"type": "long"},
                "top_category": _KEYWORD,
                "second_category": _KEYWORD,
                "third_category": _KEYWORD,
                "attributes": _STORE_ONLY,
                "classifications": _STORE_ONLY,
                "dimensions": _STORE_ONLY,
                "identifiers": _STORE_ONLY,
                "images": _STORE_ONLY,
                "relationships": _STORE_ONLY,
                "salesRanks": _STORE_ONLY,
                "sales_ranks": _STORE_ONLY,
                "categories": _STORE_ONLY,
                "summaries": _STORE_ONLY,
                "productTypes": _STORE_ONLY,
                "item_dimensions": _STORE_ONLY,
                "item_package_dimensions": _STORE_ONLY,
                "list_price": _STORE_ONLY,
                "subject_keyword": _STORE_ONLY,
                "generic_keyword": _STORE_ONLY,
            },
            "dynamic_templates": [
                {
                    "strings_as_keywords": {
                        "match_mapping_type": "string",
                        "mapping": _KEYWORD,
                    }
                }
            ],
        },
    }


def stats_index_settings() -> dict:
    return {
        "mappings": {
            "properties": {
                "job_type": {"type": "keyword"},
                "marketplace": {"type": "keyword"},
                "minute": {"type": "date"},
                "worker": {"type": "keyword"},
                "time": {"type": "date"},
                "num_asins": {"type": "integer"},
                "successful_asins": {"type": "integer"},
                "failed_asins": {"type": "integer"},
                "task_count": {"type": "integer"},
                "api_failed": {"type": "integer"},
                "task_duration_ms": {"type": "long"},
                "spapi_duration_ms": {"type": "long"},
                "spapi_success_duration_ms": {"type": "long"},
                "spapi_success_count": {"type": "integer"},
                "fetch_gap_ms": {"type": "long"},
                "fetch_gap_count": {"type": "integer"},
                "avg_task_duration_ms": {"type": "long"},
                "avg_spapi_duration_ms": {"type": "long"},
                "avg_spapi_success_ms": {"type": "long"},
                "avg_fetch_gap_ms": {"type": "long"},
            }
        }
    }
