# -*- coding: utf-8 -*-
"""CLI: schedule stale Amazon offer refresh jobs from an ASIN file."""

import logging
import logging.handlers
import os

import click
from amazon_spapi.spapi.asin import is_asin_valid

from amazon_spapi.amazon.offers.schedule_stale import StaleOfferEnqueueService
from amazon_spapi.config.env import get_broker_url
from amazon_spapi.config.paths import DEFAULT_LOG_DIR
from amazon_spapi.jobs.refresh_offers import refresh_offers
from amazon_spapi.platform import get_offer_service, logger
from amazon_spapi.scheduling.dedup import broker_url_to_dedup_redis_url
from amazon_spapi.scheduling.send import PRIORITY_NORMAL, normalize_user_priority


def _setup_log(name):
    log_dir = DEFAULT_LOG_DIR
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, name)
    handler = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=20 * 1024**2, backupCount=5
    )
    handler.setLevel(logging.INFO)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(name)s [%(levelname)s]:%(message)s")
    )
    logger.addHandler(handler)


@click.command("Schedule stale Amazon offer refresh jobs.")
@click.option("-m", "--marketplace", default="us", help="Marketplace code.")
@click.option("-c", "--condition", default="new")
@click.option(
    "-t", "--ttl", type=int, default=36, help="Offer freshness window (hours)."
)
@click.option("-f", "--force", is_flag=True, help="Skip TTL filter.")
@click.option("-q", "--qps", type=float, help="Max schedule rate (jobs/sec).")
@click.option(
    "-p",
    "--priority",
    type=int,
    default=PRIORITY_NORMAL,
    show_default=True,
    help="Task priority 0-9 (9=highest, 0=bulk).",
)
@click.option("--no-enqueue-dedup", is_flag=True)
@click.option("--dedup-ttl-sec", type=int, default=3600, show_default=True)
@click.option("--dedup-db", type=int, default=6, show_default=True)
@click.option("--dedup-redis-url", default=None)
@click.argument("asins_path")
def main(
    asins_path,
    marketplace,
    condition,
    ttl,
    force,
    qps,
    priority,
    no_enqueue_dedup,
    dedup_ttl_sec,
    dedup_db,
    dedup_redis_url,
):
    broker_url = get_broker_url()
    asins_path = os.path.abspath(os.path.expanduser(asins_path))
    if not os.path.isfile(asins_path):
        logger.error("ASIN file not found: %s", asins_path)
        return

    _setup_log("schedule_stale_offers.log")
    dedup_client = None
    if not no_enqueue_dedup and not force:
        import redis

        url = dedup_redis_url or broker_url_to_dedup_redis_url(
            broker_url, dedup_db
        )
        dedup_client = redis.Redis.from_url(url, decode_responses=False)

    scheduler = StaleOfferEnqueueService(
        broker_url=broker_url,
        marketplace=marketplace,
        condition=condition,
        offer_service=get_offer_service(),
        refresh_task=refresh_offers,
        qps=qps,
        ttl_hours=ttl,
        force=force,
        priority=normalize_user_priority(priority),
        dedup_redis_client=dedup_client,
        dedup_ttl_sec=dedup_ttl_sec,
    )
    if scheduler.should_skip():
        logger.info("Queue %s is full; skipping", scheduler.queue)
        return

    batch = []
    with open(asins_path, encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            asin = line.strip()
            if asin and is_asin_valid(asin):
                batch.append(asin)
            if len(batch) >= 500:
                scheduler.enqueue_asins(batch)
                batch = []
        if batch:
            scheduler.enqueue_asins(batch)


if __name__ == "__main__":
    main()
