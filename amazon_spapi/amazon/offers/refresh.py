# -*- coding: utf-8 -*-
"""Use case: refresh lowest marketplace offers for a batch of ASINs."""

import time

from amazon_spapi.spapi.exceptions import SellingApiInvalidAsinException
from amazon_spapi.log import logger
from amazon_spapi.amazon.delivery.stream_index_cleanup import (
    delete_asins_from_no_offer_indices,
)
from amazon_spapi.amazon.monitoring.task_stats import (
    JOB_TYPE_OFFERS,
    WorkerTaskStatsRecorder,
    now_ms,
)
from amazon_spapi.spapi import exceptions_not_retry, exceptions_to_retry
from sentry_sdk import capture_exception
from sp_api.base.exceptions import (
    SellingApiBadRequestException,
    SellingApiForbiddenException,
)

MISSING_OFFER_ASINS_INDEX = "spapi_item_offers_missing_asins"


class RefreshMarketplaceOffers:
    def __init__(
        self,
        spapi,
        offer_service,
        marketplace,
        asins,
        condition="new",
        product_service=None,
        worker=None,
    ):
        self.spapi = spapi
        self.offer_service = offer_service
        self.marketplace = marketplace.lower()
        self.asins = asins
        self.condition = condition.lower()
        self._product_service = product_service
        self.worker = worker
        self._stats = None

    def _product_service_for_monitoring(self):
        if self._product_service is not None:
            return self._product_service
        try:
            from amazon_spapi.platform import get_product_service

            self._product_service = get_product_service()
        except Exception:
            self._product_service = False
        return self._product_service or None

    def _stats_recorder(self):
        if self._stats is not None:
            return self._stats
        product_service = self._product_service_for_monitoring()
        if not product_service or not self.worker:
            self._stats = False
            return None
        self._stats = WorkerTaskStatsRecorder(
            product_service,
            self.worker,
            self.marketplace,
            JOB_TYPE_OFFERS,
        )
        return self._stats

    def run(self):
        offer_type = "lowest_offer_listings"
        total_asins = len(self.asins)
        stats = self._stats_recorder()
        task_start_ms = now_ms()
        fetch_gap_ms = stats.compute_fetch_gap_ms() if stats else 0

        offers = None
        spapi_start_ms = now_ms()
        spapi_metrics = {}
        while True:
            try:
                offers = self.spapi.get_item_offers_batch(
                    self.marketplace,
                    self.asins,
                    self.condition,
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
            except SellingApiInvalidAsinException:
                break
            except SellingApiBadRequestException:
                break
            except exceptions_not_retry:
                break

        spapi_duration_ms = now_ms() - spapi_start_ms
        task_duration_ms = now_ms() - task_start_ms

        if offers is None:
            if stats:
                stats.record_task(
                    total_asins=total_asins,
                    successful_asins=0,
                    failed_asins=0,
                    task_duration_ms=task_duration_ms,
                    spapi_duration_ms=spapi_duration_ms,
                    api_failed=1,
                    throttle_count=spapi_metrics.get("throttle_count", 0),
                    fetch_gap_ms=fetch_gap_ms,
                )
            return None

        successful_asins = 0
        for asin in self.asins:
            row = offers.get(asin)
            if row and row.get("offers"):
                successful_asins += 1
        failed_asins = max(total_asins - successful_asins, 0)

        saved = False
        try:
            result = self.offer_service.save_item_offers(
                offer_type, offers, self.marketplace, self.condition
            )
            saved = bool(result)
            if saved:
                logger.debug("[OfferSaved] %s", offers.keys())
                product_service = self._product_service_for_monitoring()
                if product_service:
                    delete_asins_from_no_offer_indices(
                        product_service, self.marketplace, offers.keys()
                    )
            else:
                logger.debug("[OfferSaveFailed] Fetched: %s", offers)
        except Exception as e:
            logger.debug("[OfferSaveFailed] Fetched: %s", offers)
            try:
                capture_exception(e)
            except Exception:
                pass

        if stats:
            stats.record_task(
                total_asins=total_asins,
                successful_asins=successful_asins if saved else 0,
                failed_asins=failed_asins if saved else total_asins,
                task_duration_ms=task_duration_ms,
                spapi_duration_ms=spapi_duration_ms,
                api_failed=0 if saved else 1,
                throttle_count=spapi_metrics.get("throttle_count", 0),
                fetch_gap_ms=fetch_gap_ms,
            )
            stats.maybe_flush()

        return offers
