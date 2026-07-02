# -*- coding: utf-8 -*-
"""Schedule stale marketplace offer refresh jobs onto Celery queues."""

import time

import redis
from kombu import Connection

from amazon_spapi.amazon.listing_rules.stale_offers import (
    filter_stale_offer_asins,
)
from amazon_spapi.log import logger
from amazon_spapi.scheduling.backpressure import should_pause_enqueue
from amazon_spapi.scheduling.dedup import claim_asins_for_enqueue
from amazon_spapi.scheduling.send import (
    PRIORITY_NORMAL,
    dispatch_task,
)
from amazon_spapi.worker.queue_names import marketplace_offers_queue

ASIN_BATCH_SIZE = 20
DEFAULT_MAX_QUEUE_DEPTH = 5000


class StaleOfferEnqueueService:
    """Enqueue offer-refresh work for ASINs that lack fresh listing data."""

    offer_type = "lowest_offer_listings"

    def __init__(
        self,
        broker_url,
        marketplace,
        condition,
        offer_service,
        refresh_task,
        qps=None,
        ttl_hours=36,
        force=False,
        priority=PRIORITY_NORMAL,
        max_queue_depth=DEFAULT_MAX_QUEUE_DEPTH,
        dedup_redis_client=None,
        dedup_ttl_sec=3600,
    ):
        self.broker_url = broker_url
        self.marketplace = marketplace.lower()
        self.condition = condition
        self.offer_service = offer_service
        self.refresh_task = refresh_task
        self.qps = qps
        self.ttl_hours = ttl_hours
        self.force = force
        self.priority = priority
        self.max_queue_depth = max_queue_depth
        self.dedup_redis_client = dedup_redis_client
        self.dedup_ttl_sec = dedup_ttl_sec
        self.connection = Connection(broker_url)
        self.queue = marketplace_offers_queue(marketplace)
        self._redis = redis.Redis.from_url(broker_url)
        self._last_send_time = None

    def should_skip(self):
        if self.force:
            return False
        return should_pause_enqueue(
            self._redis, self.queue, self.max_queue_depth
        )

    def enqueue_asins(self, asins):
        if not asins:
            return 0

        stale_asins = filter_stale_offer_asins(
            self.offer_service,
            self.offer_type,
            asins,
            self.marketplace,
            self.condition,
            self.ttl_hours,
            force=self.force,
        )
        if not stale_asins:
            return 0

        sent = 0
        chunks = [
            stale_asins[i : i + ASIN_BATCH_SIZE]
            for i in range(0, len(stale_asins), ASIN_BATCH_SIZE)
        ]
        for chunk in chunks:
            to_send = chunk
            if self.dedup_redis_client is not None and not self.force:
                to_send = claim_asins_for_enqueue(
                    self.dedup_redis_client,
                    self.marketplace,
                    self.condition,
                    chunk,
                    self.dedup_ttl_sec,
                )
            if not to_send:
                continue

            self._throttle()
            dispatch_task(
                self.refresh_task,
                args=(self.marketplace, to_send, self.condition),
                queue=self.queue,
                connection=self.connection,
                priority=self.priority,
            )
            sent += len(to_send)
            logger.debug(
                "Enqueued offer refresh %s %s (%d asins)",
                self.marketplace,
                self.condition,
                len(to_send),
            )
        return sent

    def _throttle(self):
        if not self.qps or not self._last_send_time:
            self._last_send_time = time.time()
            return
        wait_time = 1 / self.qps - (time.time() - self._last_send_time)
        if wait_time > 0:
            time.sleep(wait_time)
        self._last_send_time = time.time()
