# -*- coding: utf-8 -*-
"""CLI: enqueue offer refresh jobs from an ASIN file at high priority."""

from __future__ import annotations

import logging
import logging.handlers
import os

import click

from amazon_spapi.amazon.offers.schedule_stale import StaleOfferEnqueueService
from amazon_spapi.config.env import get_broker_url
from amazon_spapi.config.paths import DEFAULT_LOG_DIR
from amazon_spapi.jobs.refresh_offers import refresh_offers
from amazon_spapi.log import logger
from amazon_spapi.platform import get_offer_service
from amazon_spapi.scheduling.asin_file import collect_asins_from_file, read_asin_batches
from amazon_spapi.scheduling.dedup import broker_url_to_dedup_redis_url
from amazon_spapi.scheduling.priority import PRIORITY_CRITICAL, normalize_user_priority
from amazon_spapi.worker.queue_names import marketplace_offers_queue


def _setup_log(name: str) -> None:
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


def _marketplace_from_source(source: str) -> str:
    """Map ``AMZ_CA`` → ``ca``, ``AMZ_US`` → ``us``."""
    source = (source or "").strip().upper()
    if source.startswith("AMZ_") and len(source) > 4:
        return source[4:].lower()
    return source.lower()


@click.command("Enqueue offer refresh jobs from an ASIN file.")
@click.option(
    "-m",
    "--marketplace",
    default=None,
    help="Marketplace code, e.g. ca, us. Inferred from --source when omitted.",
)
@click.option(
    "--source",
    default="",
    help="Filter analytics JSON rows by source, e.g. AMZ_CA.",
)
@click.option("-c", "--condition", default="new", show_default=True)
@click.option(
    "-p",
    "--priority",
    type=int,
    default=PRIORITY_CRITICAL,
    show_default=True,
    help="Task priority 0-9 (9=highest → Redis queue suffix :9).",
)
@click.option(
    "-q",
    "--qps",
    type=float,
    default=1.0,
    show_default=True,
    help="Max enqueue rate (tasks/sec).",
)
@click.option(
    "--limit",
    type=int,
    default=None,
    help="Only enqueue the first N unique ASINs (for small tests).",
)
@click.option(
    "--read-batch",
    type=int,
    default=500,
    show_default=True,
    help="Read this many ASINs from disk before handing to the enqueuer.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Parse file and print summary without enqueueing.",
)
@click.option("--no-dedup", is_flag=True, help="Disable enqueue deduplication.")
@click.option("--dedup-ttl-sec", type=int, default=3600, show_default=True)
@click.option("--dedup-db", type=int, default=6, show_default=True)
@click.option("--dedup-redis-url", default=None)
@click.argument("asins_path")
def main(
    asins_path,
    marketplace,
    source,
    condition,
    priority,
    qps,
    limit,
    read_batch,
    dry_run,
    no_dedup,
    dedup_ttl_sec,
    dedup_db,
    dedup_redis_url,
):
    asins_path = os.path.abspath(os.path.expanduser(asins_path))
    if not os.path.isfile(asins_path):
        logger.error("ASIN file not found: %s", asins_path)
        raise SystemExit(1)

    marketplace = (marketplace or _marketplace_from_source(source) or "").lower()
    if not marketplace:
        logger.error("Set -m/--marketplace or --source AMZ_CA (etc.)")
        raise SystemExit(1)

    source_filter = source.strip().upper()
    priority = normalize_user_priority(priority)
    queue = marketplace_offers_queue(marketplace)
    redis_queue_key = queue if priority == 0 else f"{queue}:{priority}"

    if dry_run:
        asins = collect_asins_from_file(
            asins_path, source_filter=source_filter, limit=limit
        )
        print(f"file: {asins_path}")
        print(f"marketplace: {marketplace}")
        print(f"priority: {priority} -> {redis_queue_key}")
        print(f"unique asins: {len(asins)}")
        if asins:
            print(f"sample: {', '.join(asins[:5])}")
        return

    _setup_log("enqueue_offers_from_file.log")
    broker_url = get_broker_url()
    dedup_client = None
    if not no_dedup:
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
        ttl_hours=0,
        force=True,
        priority=priority,
        dedup_redis_client=dedup_client,
        dedup_ttl_sec=dedup_ttl_sec,
    )
    if scheduler.should_skip():
        logger.error("Queue %s is full; aborting", scheduler.queue)
        raise SystemExit(1)

    total_read = 0
    total_enqueued = 0
    for batch in read_asin_batches(
        asins_path,
        read_batch,
        source_filter=source_filter,
        limit=limit,
    ):
        total_read += len(batch)
        total_enqueued += scheduler.enqueue_asins(batch)

    logger.info(
        "Enqueued %d ASINs from %d parsed (%s priority=%d queue=%s)",
        total_enqueued,
        total_read,
        marketplace,
        priority,
        redis_queue_key,
    )
    print(
        f"Enqueued {total_enqueued} ASINs to {redis_queue_key} "
        f"({total_read} parsed from file)"
    )


if __name__ == "__main__":
    main()
