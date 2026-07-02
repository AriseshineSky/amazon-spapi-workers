# -*- coding: utf-8 -*-
import datetime
import logging
import logging.handlers
import os
import time
from urllib.parse import urlparse

import click
import dateutil
import dateutil.parser
import redis
from amazon_spapi.spapi.asin import is_asin_valid
from kombu import Connection

from amazon_spapi.config.paths import DEFAULT_LOG_DIR
from amazon_spapi.jobs.refresh_offers import refresh_offers
from amazon_spapi.platform import get_offer_service, get_product_service, logger


@click.command("Send spapi update item offers task to worker.")
@click.option(
    "-b",
    "--broker_url",
    type=str,
    required=True,
    help="Celery worker broker URL.",
)
@click.option(
    "-m",
    "--marketplace",
    type=str,
    default="us",
    help="Amazon marketplace to fetch offers.",
)
@click.option(
    "-i",
    "--index",
    type=str,
    default=None,
    help="Amazon marketplace to fetch catalog items.",
)
@click.option("-c", "--condition", type=str, default="new")
@click.option(
    "-t",
    "--ttl",
    type=int,
    default=36,
    help="Offer alive hours, default is 36.",
)
@click.option("-f", "--force", is_flag=True, help="Force to update offers.")
def send_spapi_item_offers_update_task(
    broker_url, index, marketplace="us", condition="new", ttl=36, force=False
):
    log_dir = DEFAULT_LOG_DIR
    if not os.path.isdir(log_dir):
        os.makedirs(log_dir)
    log_path = os.path.join(
        log_dir, "spapi_update_item_offers_task_sender.log"
    )
    level = logging.INFO
    max_bytes = 20 * 1024**2
    fh = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=max_bytes, backupCount=5
    )
    fh.setLevel(level)
    formatter = logging.Formatter(
        "%(asctime)s %(name)s [%(levelname)s]:%(message)s"
    )
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    sender = SpapiUpdateItemOffersTaskSender(
        broker_url, marketplace, condition, index, ttl, force
    )
    sender.run()


class SpapiUpdateItemOffersTaskSender:
    def get_redis_client(self, broker_url):
        url = urlparse(broker_url)
        redis_host = url.hostname
        redis_port = url.port
        redis_db = int(url.path.lstrip("/") or 0)
        redis_password = url.password

        return redis.StrictRedis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            password=redis_password,
            decode_responses=True,
        )

    def __init__(self, broker_url, marketplace, condition, index, ttl, force):
        self.offer_service = get_offer_service()
        self.broker_url = broker_url
        self.marketplace = marketplace.lower()
        self.condition = condition
        self.ttl = ttl
        self.force = force
        self.connection = Connection(broker_url)
        self.queue = "SpapiItemOffersUpdate_{}".format(marketplace.upper())
        self.offer_type = "lowest_offer_listings"
        self.last_send_time = None
        self.marketplace = marketplace
        self.asin_indice_name = f"amz_asins_{self.marketplace}_no_offer"
        if index:
            self.asin_indice_name = index
        self.redis = self.get_redis_client(broker_url)
        self.product_service = get_product_service()
        self.queue_limit = 10000

    def is_queue_full(self):
        queue_size = self.redis.llen(self.queue)

        logger.debug(f"[current queue size] {self.queue}: {queue_size}")
        return queue_size >= self.queue_limit

    def run(self):
        asins_buf = []
        batch_size = 500
        while True:
            for s, _ in self.product_service.load_products_by_after_search(
                self.asin_indice_name
            ):
                if not is_asin_valid(s):
                    continue

                asins_buf.append(s)
                if len(asins_buf) < batch_size:
                    continue

                self.process_products(asins_buf)
                asins_buf = []

                if self.is_queue_full():
                    time.sleep(60 * 10)

            if asins_buf:
                self.process_products(asins_buf)
                asins_buf = []
                if self.is_queue_full():
                    time.sleep(60 * 10)

            time.sleep(60 * 30)

    def process_products(self, asins):
        if self.force:
            asins_without_offer = list(asins)
        else:
            now = datetime.datetime.utcnow()
            offer_expire_time = now - datetime.timedelta(hours=self.ttl)

            asins_without_offer = dict()
            offers = dict()
            result = self.offer_service.search_offers(
                self.offer_type, asins, self.marketplace, self.condition
            )
            if not result:
                asins_without_offer = list(asins)
            else:
                while isinstance(result, dict) and "hits" in result:
                    result = result["hits"]
                if isinstance(result, list):
                    for offer in result:
                        if not offer:
                            continue

                        offers[offer["_source"]["asin"]] = offer["_source"]
                else:
                    offers = result
                for asin in asins:
                    if asin not in offers or not offers[asin]:
                        asins_without_offer[asin] = None
                        continue

                    offer = offers[asin]
                    offer_time_s = offer.get("time", None)
                    if not offer_time_s:
                        asins_without_offer[asin] = None
                        continue

                    try:
                        offer_time = dateutil.parser.parse(offer_time_s)

                        # Offer expired
                        if offer_time < offer_expire_time:
                            asins_without_offer[asin] = None
                            continue
                    except Exception:
                        asins_without_offer[asin] = None

                    logger.debug("[ASINHasOffer] %s", asin)

                asins_without_offer = list(asins_without_offer.keys())

        chunks = [
            asins_without_offer[x : x + 20]
            for x in range(0, len(asins_without_offer), 20)
        ]
        for chunk in chunks:
            refresh_offers.apply_async(
                args=(self.marketplace, chunk, self.condition),
                queue=self.queue,
                connection=self.connection,
            )
            logger.debug(
                "Added spapi_update_item_offers(%s, %s, %s)",
                self.marketplace,
                chunk,
                self.condition,
            )


if __name__ == "__main__":
    send_spapi_item_offers_update_task()
