# -*- coding: utf-8 -*-
"""Tests for worker task stats monitoring."""

import datetime

from amazon_spapi.amazon.monitoring.task_stats import (
    build_task_stats_doc_id,
    sanitize_worker_for_doc_id,
)


def test_sanitize_worker_for_doc_id():
    assert sanitize_worker_for_doc_id("celery@host.example") == "celery_at_host.example"


def test_build_task_stats_doc_id():
    minute = datetime.datetime(2026, 7, 2, 15, 4, 30, tzinfo=datetime.timezone.utc)
    doc_id = build_task_stats_doc_id(
        "offers",
        "US",
        "celery@worker-1",
        88421,
        minute,
    )
    assert doc_id == "offers:us:celery_at_worker-1:pid88421:2026-07-02T15:04:00Z"


def test_catalog_and_offers_doc_ids_differ_by_job_type():
    minute = datetime.datetime(2026, 7, 2, 15, 4, tzinfo=datetime.timezone.utc)
    worker = "celery@host"
    offers_id = build_task_stats_doc_id("offers", "uk", worker, 1, minute)
    catalog_id = build_task_stats_doc_id("catalog", "uk", worker, 1, minute)
    assert offers_id != catalog_id
    assert offers_id.startswith("offers:uk:")
    assert catalog_id.startswith("catalog:uk:")
