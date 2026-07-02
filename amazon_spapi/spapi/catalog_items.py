# -*- coding: utf-8 -*-
"""Shared Catalog Items API helpers."""

from __future__ import annotations

from typing import Any, Dict, List

from amazon_spapi.spapi.spapi_catalog_items_parser import SpapiCatalogItemsParser

CATALOG_INCLUDED_DATA = [
    "summaries",
    "attributes",
    "dimensions",
    "identifiers",
    "images",
    "productTypes",
    "relationships",
    "salesRanks",
    "classifications",
]


class CatalogItemsApiResponse:
    """Minimal wrapper matching SP-API responses (``.payload``)."""

    def __init__(self, payload: Dict[str, Any]) -> None:
        self.payload = payload


def catalog_included_data_csv() -> str:
    return ",".join(CATALOG_INCLUDED_DATA)


def search_and_parse_catalog_items(
    client, marketplace: str, asins: List[str], metrics=None
):
    """Call ``client.search_catalog_items`` and parse with ``SpapiCatalogItemsParser``."""
    response = client.search_catalog_items(
        asins, marketplace=marketplace, metrics=metrics
    )
    if not response:
        return None
    return SpapiCatalogItemsParser.parse(response)
