# -*- coding: utf-8 -*-
"""Use case: refresh marketplace catalog metadata for a batch of ASINs."""

import datetime
import time

from amazon_spapi.spapi.exceptions import SellingApiInvalidAsinException
from amazon_spapi.log import logger
from amazon_spapi.amazon.delivery.stream_index_cleanup import (
    delete_asins_from_no_info_indices,
)
from amazon_spapi.amazon.monitoring.task_stats import (
    JOB_TYPE_CATALOG,
    WorkerTaskStatsRecorder,
    now_ms,
)
from amazon_spapi.spapi import exceptions_not_retry, exceptions_to_retry
from amazon_spapi.spapi.catalog_items import search_and_parse_catalog_items
from sp_api.base.exceptions import (
    SellingApiBadRequestException,
    SellingApiException,
    SellingApiForbiddenException,
)


class RefreshMarketplaceCatalog:
    def __init__(
        self,
        spapi,
        product_service,
        marketplace,
        asins,
        worker,
        catalog_index=None,
        missing_index=None,
    ):
        self.spapi = spapi
        self.product_service = product_service
        self.worker = worker
        self.marketplace = marketplace.lower()
        self.asins = asins
        self.catalog_index = catalog_index or "amz_products_api_{}_v2".format(
            self.marketplace
        )
        self.missing_index = missing_index or "amz_products_missing_{}".format(
            self.marketplace
        )
        self.stats = WorkerTaskStatsRecorder(
            product_service,
            worker,
            self.marketplace,
            JOB_TYPE_CATALOG,
        )

    def run(self):
        task_start_ms = now_ms()
        fetch_gap_ms = self.stats.compute_fetch_gap_ms()

        cur_time = datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )

        indice_name = self.catalog_index
        missing_index = self.missing_index

        products_info = None
        spapi_start_ms = now_ms()
        spapi_metrics = {}
        while True:
            try:
                products_info = self.search_catalog_items(
                    self.spapi,
                    self.marketplace,
                    self.asins,
                    metrics=spapi_metrics,
                )
                break
            except SellingApiForbiddenException as e:
                raise e
            except exceptions_to_retry as e:
                from sp_api.base.exceptions import SellingApiRequestThrottledException

                if isinstance(e, SellingApiRequestThrottledException):
                    spapi_metrics["throttle_count"] = (
                        spapi_metrics.get("throttle_count", 0) + 1
                    )
                time.sleep(3)
            except exceptions_not_retry:
                break
            except (
                SellingApiInvalidAsinException,
                SellingApiBadRequestException,
                SellingApiException,
            ):
                break

        spapi_duration_ms = now_ms() - spapi_start_ms
        total_asins = len(self.asins)

        if products_info is None:
            successful_asins = 0
            failed_asins = 0
            api_failed = 1
        else:
            successful_asins = len(products_info)
            failed_asins = total_asins - successful_asins
            api_failed = 0

        task_duration_ms = now_ms() - task_start_ms

        self.stats.record_task(
            total_asins=total_asins,
            successful_asins=successful_asins,
            failed_asins=failed_asins,
            task_duration_ms=task_duration_ms,
            spapi_duration_ms=spapi_duration_ms,
            api_failed=api_failed,
            throttle_count=spapi_metrics.get("throttle_count", 0),
            fetch_gap_ms=fetch_gap_ms,
        )

        if products_info is None:
            return {
                "requested_asins": total_asins,
                "api_failed": 1,
                "parsed_asins": 0,
                "saved_catalog": 0,
                "saved_missing": 0,
            }

        returned_asins = set(products_info.keys())
        missing_asins = [
            asin for asin in self.asins if asin not in returned_asins
        ]
        saved_missing = 0
        if missing_asins:
            self.save_missing_asins(missing_asins, missing_index, cur_time)
            saved_missing = len(missing_asins)
            delete_asins_from_no_info_indices(
                self.product_service, self.marketplace, missing_asins
            )

        saved_catalog = 0
        for _, product_info in products_info.items():
            product_info["_id"] = product_info["asin"]
            product_info["time"] = cur_time
        try:
            if products_info:
                self.product_service.save_products(
                    indice_name, list(products_info.values())
                )
                saved_catalog = len(products_info)
                delete_asins_from_no_info_indices(
                    self.product_service,
                    self.marketplace,
                    products_info.keys(),
                )
        except Exception as e:
            logger.warning("[ProductSaveToServiceError] %s", products_info)
            logger.exception(e)
            raise e

        self.stats.maybe_flush()
        return {
            "requested_asins": total_asins,
            "api_failed": api_failed,
            "parsed_asins": len(products_info),
            "saved_catalog": saved_catalog,
            "saved_missing": saved_missing,
        }

    def save_missing_asins(self, missing_asins, index_name, cur_time):
        docs = [
            {"_id": asin, "asin": asin, "time": cur_time}
            for asin in missing_asins
        ]
        try:
            self.product_service.save_products(index_name, docs)
        except Exception as e:
            logger.warning("[MissingASINSaveError] %s", missing_asins)
            logger.exception(e)

    def search_catalog_items(self, spapi, marketplace, asins, metrics=None):
        return search_and_parse_catalog_items(
            spapi, marketplace, asins, metrics=metrics
        )
