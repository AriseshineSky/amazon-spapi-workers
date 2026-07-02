# -*- coding: utf-8
"""SP-API client: Catalog Items API + Product Pricing (offers) API."""

from amazon_spapi.spapi.catalog import CatalogApiClient
from amazon_spapi.spapi.exceptions import exceptions_not_retry, exceptions_to_retry
from amazon_spapi.spapi.marketplaces import (
    MARKETPLACE_IDS as marketplaceIdList,
    MARKETPLACE_REGIONS as marketplaceRegions,
    marketplace_locale,
    marketplace_region,
)
from amazon_spapi.spapi.offer_converter import SpItemOfferBatchConverter
from amazon_spapi.spapi.offers import OffersApiClient


class Spapi(CatalogApiClient, OffersApiClient):
    """Unified SP-API client used by Celery workers."""

    def __init__(self, credentials):
        self.credentials = credentials
        self._catalog_items_apis = {}
        self._products_apis = {}
        self.sp_item_offer_batch_converter = SpItemOfferBatchConverter()

    @classmethod
    def get_marketplace_region(cls, marketplace):
        return marketplace_region(marketplace)

    def get_locale(self, marketplace):
        return marketplace_locale(marketplace)


__all__ = [
    "Spapi",
    "CatalogApiClient",
    "OffersApiClient",
    "exceptions_to_retry",
    "exceptions_not_retry",
    "marketplaceIdList",
    "marketplaceRegions",
]
