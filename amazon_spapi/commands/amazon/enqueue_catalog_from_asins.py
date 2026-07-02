# -*- coding: utf-8 -*-
import datetime
import logging
import logging.handlers
import os
import time

import click
import dateutil
import dateutil.parser
from amazon_spapi.spapi.asin import is_asin_valid
from kombu import Connection

from amazon_spapi.config.paths import DEFAULT_LOG_DIR
from amazon_spapi.jobs.refresh_catalog import refresh_catalog
from amazon_spapi.platform import get_product_service, logger


@click.command("Send spapi update catalog items task to worker.")
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
    help="Amazon marketplace to fetch catalog items.",
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
@click.argument("asins_path")
def send_spapi_catalog_items_update_task(
    asins_path, broker_url, qps, marketplace="us", ttl=168, force=False
):
    asins_path = os.path.abspath(os.path.expanduser(asins_path))
    if not os.path.isfile(asins_path):
        logger.error("Could not find asins file {}".format(asins_path))
        return

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

    sender = SpapiUpdateCatalogItemsTaskSender(
        broker_url, qps, marketplace.lower(), asins_path, ttl, force
    )
    sender.run()


class SpapiUpdateCatalogItemsTaskSender:
    def __init__(self, broker_url, qps, marketplace, asins_path, ttl, force):
        self.product_service = get_product_service()
        self.broker_url = broker_url
        self.qps = qps
        self.marketplace = marketplace.lower()
        self.asins_path = asins_path
        self.ttl = ttl
        self.force = force
        self.indice_name = "amz_products_api_{}_v2".format(self.marketplace)
        self.last_send_time = None
        self.queue = "SpapiCatalogItemsUpdate_{}".format(
            self.marketplace.upper()
        )
        self.connection = Connection(self.broker_url)
        self.product_service.ensure_indice(self.indice_name)
        self.search_opts = {"_source": ["asin", "time"]}

    def run(self):
        asins_buf = []
        batch_size = 500
        with open(self.asins_path, encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                s = line.strip()
                if not s:
                    continue

                if not is_asin_valid(s):
                    continue

                asins_buf.append(s)
                if len(asins_buf) < batch_size:
                    continue

                self.process_products(asins_buf)
                asins_buf = []

            if asins_buf:
                self.process_products(asins_buf)
                asins_buf = []

    def process_products(self, asins):
        asins_without_info = None
        if self.force:
            asins_without_info = list(asins)
        else:
            now = datetime.datetime.now()
            product_expire_time = now - datetime.timedelta(hours=self.ttl)

            products_info = self.product_service.search_products(
                self.indice_name, asins, self.search_opts
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
            asins_without_info[x : x + 20]
            for x in range(0, len(asins_without_info), 20)
        ]
        for chunk in chunks:
            if self.last_send_time:
                wait_time = 1 / self.qps - (time.time() - self.last_send_time)
                if wait_time > 0:
                    logger.debug(
                        "Waiting %.3fs to send next message", wait_time
                    )
                    time.sleep(wait_time)

            self.last_send_time = time.time()

            refresh_catalog.apply_async(
                args=(self.marketplace, chunk),
                queue=self.queue,
                connection=self.connection,
            )
            logger.debug(
                "Added spapi_update_catalog_items(%s, %s)",
                self.marketplace,
                chunk,
            )


if __name__ == "__main__":
    send_spapi_catalog_items_update_task()
