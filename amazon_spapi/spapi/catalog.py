# -*- coding: utf-8 -*-
"""SP-API Catalog Items API (searchCatalogItems)."""

from __future__ import annotations

import time
from typing import List

from sp_api.base.exceptions import (
    SellingApiBadRequestException,
    SellingApiForbiddenException,
    SellingApiRequestThrottledException,
)

from amazon_spapi.spapi.catalog_items import (
    CATALOG_INCLUDED_DATA,
    search_and_parse_catalog_items,
)
from amazon_spapi.spapi.client import CatalogItems, CatalogItemsVersion, base
from amazon_spapi.spapi.exceptions import (
    SellingApiInvalidAsinException,
    exceptions_not_retry,
    exceptions_to_retry,
)
from amazon_spapi.spapi.marketplaces import MARKETPLACE_IDS, marketplace_locale


class CatalogApiClient:
    """Catalog Items API v2022-04-01."""

    def __init__(self, credentials):
        self.credentials = credentials
        self._catalog_items_apis = {}

    def get_catalog_items_api(self, marketplace: str):
        marketplace = marketplace.upper()
        if (
            marketplace not in base.Marketplaces.__members__
            or not base.Marketplaces.__members__[marketplace]
        ):
            raise ValueError("Unknown marketplace {}".format(marketplace))

        if marketplace not in self._catalog_items_apis:
            self._catalog_items_apis[marketplace] = CatalogItems(
                credentials=self.credentials,
                marketplace=marketplace,
                version=CatalogItemsVersion.V_2022_04_01,
            )
        return self._catalog_items_apis[marketplace]

    def search_catalog_items(
        self,
        asins,
        marketplace="US",
        locale="en_GB",
        search_type="identifiers",
        metrics=None,
        **kwargs,
    ):
        marketplace = marketplace.upper()
        market_id = MARKETPLACE_IDS[marketplace]
        included_data = list(CATALOG_INCLUDED_DATA)

        possible_locale = marketplace_locale(marketplace)
        if possible_locale:
            locale = possible_locale

        items = None
        max_retries = 12
        params = {
            "marketplaceIds": [market_id],
            "includedData": ",".join(included_data),
            "locale": locale,
        }
        if search_type == "identifiers":
            params["identifiers"] = ",".join(asins)
            params["identifiersType"] = "ASIN"
        else:
            params["keywords"] = ",".join(asins)
            params["pageSize"] = 20
        if kwargs:
            params.update(kwargs)

        while max_retries > 0:
            try:
                items = self.get_catalog_items_api(
                    marketplace
                ).search_catalog_items(**params)
                break
            except SellingApiBadRequestException as e:
                msg = e.message.lower()
                if "invalid asin" in msg:
                    raise SellingApiInvalidAsinException(
                        e.error, e.headers
                    ) from e
                raise
            except exceptions_not_retry as e:
                if isinstance(e, SellingApiForbiddenException):
                    time.sleep(3)
                raise
            except exceptions_to_retry as e:
                if isinstance(e, SellingApiRequestThrottledException) and metrics is not None:
                    metrics["throttle_count"] = metrics.get("throttle_count", 0) + 1
                time.sleep(max_retries)
                max_retries -= 1
                if max_retries <= 0:
                    raise

        return items

    def search_and_parse(self, marketplace: str, asins: List[str]):
        return search_and_parse_catalog_items(self, marketplace, asins)

    def get_locale(self, marketplace: str):
        return marketplace_locale(marketplace)
