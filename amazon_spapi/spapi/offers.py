# -*- coding: utf-8 -*-
"""SP-API Products Pricing API (getItemOffersBatch)."""

from __future__ import annotations

import time
from datetime import datetime

from sp_api.base.exceptions import SellingApiBadRequestException, SellingApiForbiddenException

from amazon_spapi.spapi.client import Products, base
from amazon_spapi.spapi.exceptions import (
    SellingApiInvalidAsinException,
    exceptions_not_retry,
    exceptions_to_retry,
)
from amazon_spapi.spapi.marketplaces import MARKETPLACE_IDS
from amazon_spapi.spapi.offer_converter import SpItemOfferBatchConverter


class OffersApiClient:
    """Product Pricing API — batch item offers."""

    def __init__(self, credentials):
        self.credentials = credentials
        self._products_apis = {}
        self.sp_item_offer_batch_converter = SpItemOfferBatchConverter()

    def get_products_api(self, marketplace: str):
        marketplace = marketplace.upper()
        if (
            marketplace not in base.Marketplaces.__members__
            or not base.Marketplaces.__members__[marketplace]
        ):
            raise ValueError("Unknown marketplace {}".format(marketplace))

        if marketplace not in self._products_apis:
            self._products_apis[marketplace] = Products(
                credentials=self.credentials,
                marketplace=marketplace,
            )
        return self._products_apis[marketplace]

    def get_item_offers_batch(
        self,
        marketplace,
        asins,
        condition="New",
        add_default_offer=True,
    ):
        marketplace = marketplace.upper()
        marketplace_id = MARKETPLACE_IDS[marketplace]
        sp_products_api = self.get_products_api(marketplace)

        offers = None
        now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        max_retries = 12
        while max_retries > 0:
            try:
                requests = []
                for asin in asins:
                    requests.append(
                        {
                            "uri": "/products/pricing/v0/items/{}/offers".format(
                                asin
                            ),
                            "method": "GET",
                            "MarketplaceId": marketplace_id,
                            "ItemCondition": condition,
                        }
                    )
                responses = sp_products_api.get_item_offers_batch(requests)
                offers = self.sp_item_offer_batch_converter.convert(responses)
                if offers and isinstance(offers, dict) and add_default_offer:
                    for asin in asins:
                        if asin in offers:
                            continue
                        offers[asin] = {
                            "asin": asin,
                            "offers": [],
                            "summary": "",
                            "time": now,
                        }
                break
            except SellingApiBadRequestException as e:
                if "invalid ASIN" in e.message:
                    raise SellingApiInvalidAsinException(
                        e.error, e.headers
                    ) from e
                raise
            except exceptions_not_retry as e:
                if isinstance(e, SellingApiForbiddenException):
                    time.sleep(7)
                raise
            except exceptions_to_retry:
                time.sleep(max_retries)
                max_retries -= 1
                if max_retries <= 0:
                    raise

        return offers
