# -*- coding: utf-8 -*-
"""Use case: fetch marketplace offers and catalog for a batch of ASINs."""

import datetime
import json
import os
import time

import sp_api
from amazon_spapi.log import logger
from amazon_spapi.spapi.spapi_catalog_items_parser import SpapiCatalogItemsParser
from sp_api.base.exceptions import SellingApiRequestThrottledException


class FetchMarketplaceProducts:
    def __init__(
        self,
        spapi,
        offer_service,
        product_service,
        marketplace,
        asins,
        condition="new",
        force=False,
        batch_size=20,
    ):
        self.spapi = spapi
        self.offer_service = offer_service
        self.product_service = product_service
        self.marketplace = marketplace.lower()
        self.asins = asins
        self.condition = condition.lower()
        self.force = force
        self.batch_size = batch_size if batch_size and batch_size < 20 else 20
        self.indice_name = "amz_products_api_{}".format(self.marketplace)
        self.local_product_log = f"./{self.indice_name}.txt"

    def _append_to_local_file(self, path, data):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            json.dump(
                {
                    "timestamp": datetime.datetime.utcnow().isoformat(),
                    "data": data,
                },
                f,
                ensure_ascii=False,
            )
            f.write("\n")

    def run(self):
        offer_type = "lowest_offer_listings"
        cur_time = datetime.datetime.strftime(
            datetime.datetime.utcnow(), "%Y-%m-%dT%H:%M:%S"
        )

        if self.force:
            asins_to_fetch_offer = {asin: None for asin in self.asins}
        else:
            offers = self.offer_service.get_offers(
                self.marketplace, self.asins, self.condition
            )
            if not offers and not isinstance(offers, dict):
                return

            asins_to_fetch_offer = {asin: None for asin in self.asins}
            for asin in self.asins:
                if (
                    asin not in offers
                    or not offers[asin]
                    or offers[asin].get("expired", True)
                ):
                    continue

                asins_to_fetch_offer.pop(asin, None)

        if asins_to_fetch_offer:
            asins_to_fetch_offer = list(asins_to_fetch_offer.keys())
            chunks = [
                asins_to_fetch_offer[x : x + self.batch_size]
                for x in range(0, len(asins_to_fetch_offer), self.batch_size)
            ]
            for chunk in chunks:
                while True:
                    try:
                        offers = self.spapi.get_item_offers_batch(
                            self.marketplace, chunk, self.condition
                        )
                        if offers:
                            try:
                                self.offer_service.save_item_offers(
                                    offer_type,
                                    offers,
                                    self.marketplace,
                                    self.condition,
                                )
                                logger.debug("[OfferSaved] %s", offers)
                            except Exception as e:
                                logger.warning(
                                    (
                                        "[SaveOfferError] Marketplace: %s, "
                                        "Condition: %s, ASINs: %s"
                                    ),
                                    self.marketplace,
                                    self.condition,
                                    chunk,
                                )
                                logger.exception(e)

                        break
                    except SellingApiRequestThrottledException:
                        time.sleep(3)

        if self.force:
            asins_without_info = {asin: None for asin in self.asins}
        else:
            products_info = self.product_service.search_products(
                self.indice_name, self.asins
            )
            asins_without_info = dict()
            for asin in self.asins:
                if asin not in products_info or not products_info[asin]:
                    asins_without_info[asin] = None

        asins_without_info = list(asins_without_info.keys())
        chunks = [
            asins_without_info[x : x + self.batch_size]
            for x in range(0, len(asins_without_info), self.batch_size)
        ]
        for chunk in chunks:
            while True:
                try:
                    response = self.spapi.search_catalog_items(
                        chunk, marketplace=self.marketplace
                    )
                    if response:
                        products_info = SpapiCatalogItemsParser.parse(response)
                        if products_info:
                            for _, product_info in products_info.items():
                                product_info["_id"] = product_info["asin"]
                                product_info["time"] = cur_time
                            try:
                                self.product_service.save_products(
                                    self.indice_name,
                                    list(products_info.values()),
                                )
                            except Exception as e:
                                logger.warning(
                                    "[ProductSaveToServiceError] %s",
                                    products_info,
                                )
                                logger.exception(e)

                    break
                except (
                    sp_api.base.exceptions.SellingApiRequestThrottledException
                ):
                    time.sleep(3)
