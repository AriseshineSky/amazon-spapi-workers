# -*- coding: utf-8
"""Wrapped python-amazon-sp-api clients used by workers."""

from sp_api.api import CatalogItems, CatalogItemsVersion, Products
from sp_api import base
from sp_api.base.marketplaces import Marketplaces

import amazon_spapi.spapi.monkey_patches  # noqa: F401 — side-effect patch
from amazon_spapi.spapi.monkey_patches import from_marketplace_id
from amazon_spapi.spapi.wrapper import spapi_wrapper

Marketplaces.from_marketplace_id = from_marketplace_id

Products = spapi_wrapper(Products)
CatalogItems = spapi_wrapper(CatalogItems)

__all__ = [
    "Products",
    "CatalogItems",
    "CatalogItemsVersion",
    "base",
    "Marketplaces",
]
