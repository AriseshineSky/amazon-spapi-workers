# -*- coding: utf-8 -*-
"""Tests for worker task stats monitoring."""

import datetime
from unittest.mock import MagicMock, patch

from amazon_spapi.amazon.monitoring.task_stats import (
    TASK_STATS_INDICES,
    build_task_stats_doc_id,
    get_task_stats_retention_days,
    purge_cutoff_minute,
    purge_old_task_stats,
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


def test_get_task_stats_retention_days_default():
    with patch.dict("os.environ", {}, clear=True):
        assert get_task_stats_retention_days() == 7


def test_get_task_stats_retention_days_from_env():
    with patch.dict("os.environ", {"SPAPI_TASK_STATS_RETENTION_DAYS": "14"}):
        assert get_task_stats_retention_days() == 14


def test_purge_old_task_stats_deletes_from_both_indices():
    product_service = MagicMock()
    product_service.index_exists.return_value = True
    product_service.esclient.delete_by_query.return_value = {"deleted": 3}

    deleted = purge_old_task_stats(product_service, retention_days=7)

    assert deleted == len(TASK_STATS_INDICES) * 3
    assert product_service.esclient.delete_by_query.call_count == len(TASK_STATS_INDICES)
    body = product_service.esclient.delete_by_query.call_args.kwargs["body"]
    cutoff = body["query"]["range"]["minute"]["lt"]
    assert cutoff.endswith("Z")


def test_purge_cutoff_minute_aligns_to_minute():
    with patch(
        "amazon_spapi.amazon.monitoring.task_stats.datetime.datetime"
    ) as mock_dt:
        fixed = datetime.datetime(2026, 7, 10, 12, 34, 56, tzinfo=datetime.timezone.utc)
        mock_dt.now.return_value = fixed
        mock_dt.timedelta = datetime.timedelta
        mock_dt.timezone = datetime.timezone
        cutoff = purge_cutoff_minute(7)
    assert cutoff == datetime.datetime(2026, 7, 3, 12, 34, 0, tzinfo=datetime.timezone.utc)
