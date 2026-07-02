# -*- coding: utf-8 -*-
"""Celery application bootstrap."""

from __future__ import absolute_import

from celery import Celery
from celery.signals import worker_process_init
from celery.utils.log import get_logger

logger = get_logger(__name__)

HANDLER_MODULES = [
    "amazon_spapi.jobs.refresh_offers",
    "amazon_spapi.jobs.fetch_products",
    "amazon_spapi.jobs.refresh_catalog",
]

app = Celery("amazon_spapi", include=HANDLER_MODULES)
app.config_from_object("amazon_spapi.worker.settings")


@worker_process_init.connect
def _on_worker_process_init(**kwargs):
    """Once per forked worker process."""
    try:
        from amazon_spapi.platform import init_sentry

        init_sentry()
    except Exception:
        logger.exception("init_sentry on worker_process_init failed")

    try:
        from amazon_spapi.amazon.monitoring.task_stats import (
            ensure_item_offers_aux_indices,
            ensure_worker_task_stats_indices,
        )
        from amazon_spapi.platform import get_product_service

        product_service = get_product_service()
        ensure_worker_task_stats_indices(product_service)
        ensure_item_offers_aux_indices(product_service)
    except Exception:
        logger.exception(
            "ensure_worker_task_stats_indices on worker_process_init failed"
        )


if __name__ == "__main__":
    app.start()
