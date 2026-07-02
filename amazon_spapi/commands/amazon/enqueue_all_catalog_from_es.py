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
from amazon_spapi.jobs.refresh_catalog import refresh_catalog
from amazon_spapi.platform import get_product_service, logger

marketplaces = [
    "us",
    "uk",
    "de",
    "it",
    "jp",
    "ca",
    "mx",
    "ae",
    "in",
    "fr",
    "pl",
    "be",
    "nl",
]
task_batch_size_by_marketplace = {"jp": 10}

# Empty indices need a timestamp mapping for after-search pagination.
ASIN_NO_INFO_INDEX_BODY = {
    "mappings": {
        "properties": {
            "asin": {"type": "keyword"},
            "timestamp": {"type": "date"},
            "time": {"type": "date"},
        }
    }
}


@click.command("Send spapi update catalog items task to worker.")
@click.option(
    "-b",
    "--broker_url",
    type=str,
    required=True,
    help="Celery worker broker URL.",
)
@click.option(
    "-t",
    "--ttl",
    type=int,
    default=168,
    help="Catalog items alive hours, default is 168.",
)
@click.option(
    "-f", "--force", is_flag=True, help="Force to update catalog items."
)
@click.option(
    "-q", "--qps", type=float, help="Quantity per second (QPS) to send task."
)
def send_spapi_catalog_items_update_task(
    broker_url, qps, ttl=168, force=False
):
    log_dir = DEFAULT_LOG_DIR
    if not os.path.isdir(log_dir):
        os.makedirs(log_dir)
    log_path = os.path.join(
        log_dir, "spapi_update_catalog_items_task_sender.log"
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

    sender = SpapiUpdateCatalogItemsTaskSender(broker_url, qps, ttl, force)
    sender.run()


class SpapiUpdateCatalogItemsTaskSender:
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

    def __init__(self, broker_url, qps, ttl, force):
        self.product_service = get_product_service()
        self.broker_url = broker_url
        self.qps = qps
        self.ttl = ttl
        self.force = force
        self.last_send_time = None
        self.connection = Connection(self.broker_url)
        self.search_opts = {"_source": ["asin", "time"]}
        self.redis = self.get_redis_client(broker_url)
        self.queue_limit = 10000
        self.queue_low_cut = 100

    def is_queue_need_to_send(self, queue):
        queue_size = self.redis.llen(queue)

        logger.debug(f"[current queue size] {queue}: {queue_size}")
        return queue_size <= self.queue_low_cut

    def is_queue_full(self, queue):
        queue_size = self.redis.llen(queue)

        logger.debug(f"[current queue size] {queue}: {queue_size}")
        return queue_size >= self.queue_limit

    def run(self):
        asins_buf = []
        batch_size = 2000
        time_key = "timestamp"
        default_task_batch_size = 20

        while True:
            for marketplace in marketplaces:
                indice_name = "amz_products_api_{}_v2".format(marketplace)
                queue = "SpapiCatalogItemsUpdate_{}".format(
                    marketplace.upper()
                )

                if not self.is_queue_need_to_send(queue):
                    continue

                search_opts = {"_source": ["asin", "time"]}
                asin_indice_name = "amz_asins_{}_no_info".format(marketplace)
                task_batch_size = (
                    task_batch_size_by_marketplace[marketplace]
                    if marketplace in task_batch_size_by_marketplace
                    else default_task_batch_size
                )

                if not self.product_service.ensure_indice(
                    asin_indice_name, ASIN_NO_INFO_INDEX_BODY
                ):
                    logger.warning(
                        "Skipping %s: index %s missing, could not create "
                        "(e.g. cluster shard limit).",
                        marketplace,
                        asin_indice_name,
                    )
                    continue
                for s, _ in self.product_service.load_products_by_after_search(
                    asin_indice_name,
                    "1999-01-01T00:00:01.722593+00:00",
                    time_key,
                ):
                    if not is_asin_valid(s):
                        continue

                    asins_buf.append(s)
                    if len(asins_buf) < batch_size:
                        continue

                    self.process_products(
                        asins_buf,
                        indice_name,
                        search_opts,
                        marketplace,
                        queue,
                        task_batch_size,
                    )
                    asins_buf = []

                    if self.is_queue_full(queue):
                        break

                if asins_buf:
                    self.process_products(
                        asins_buf,
                        indice_name,
                        search_opts,
                        marketplace,
                        queue,
                        task_batch_size,
                    )
                    asins_buf = []
                    if self.is_queue_full(queue):
                        break

            time.sleep(60 * 10)

    def process_products(
        self,
        asins,
        indice_name,
        search_opts,
        marketplace,
        queue,
        task_batch_size,
    ):
        asins_without_info = None
        if self.force:
            asins_without_info = list(asins)
        else:
            now = datetime.datetime.now()
            product_expire_time = now - datetime.timedelta(hours=self.ttl)

            self.product_service.ensure_indice(indice_name)
            products_info = self.product_service.search_products(
                indice_name, asins, search_opts
            )
            if products_info:
                asins_without_info = dict()
                for asin in asins:
                    if asin not in products_info or not products_info[asin]:
                        asins_without_info[asin] = None
                        continue

                    product_info = products_info[asin]
                    product_time_s = product_info.get("time", None)
                    if not product_time_s:
                        asins_without_info[asin] = None
                        continue

                    try:
                        product_time = dateutil.parser.parse(product_time_s)

                        # Product information expired
                        if product_time < product_expire_time:
                            asins_without_info[asin] = None
                            continue
                    except Exception:
                        asins_without_info[asin] = None

                asins_without_info = list(asins_without_info.keys())
            else:
                asins_without_info = list(asins)

        chunks = [
            asins_without_info[x : x + task_batch_size]
            for x in range(0, len(asins_without_info), task_batch_size)
        ]
        for chunk in chunks:
            refresh_catalog.apply_async(
                args=(marketplace, chunk),
                queue=queue,
                connection=self.connection,
            )
            logger.debug(
                "Added spapi_update_catalog_items(%s, %s)", marketplace, chunk
            )


if __name__ == "__main__":
    send_spapi_catalog_items_update_task()
