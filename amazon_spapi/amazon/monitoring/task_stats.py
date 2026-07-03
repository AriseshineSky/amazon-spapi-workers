# -*- coding: utf-8 -*-
"""
Per-minute worker task stats for SP-API offers and catalog jobs.

All marketplaces share one index per job type; ``marketplace`` on each document
distinguishes sites. See ``docs/监控数据.md`` for index names and ``_id`` rules.
"""

from __future__ import annotations

import datetime
import os
import re
import time
from typing import Any, Dict, Optional

from amazon_spapi.amazon.delivery.indices import stats_index_settings
from amazon_spapi.log import logger

# One index per job type; every marketplace lives in the same index.
OFFERS_TASK_STATS_INDEX = "spapi_task_stats_offers"
CATALOG_TASK_STATS_INDEX = "spapi_task_stats_catalog"

DEFAULT_TASK_STATS_RETENTION_DAYS = 7
TASK_STATS_PURGE_LOCK_KEY = "spapi:task_stats:purge_lock"
TASK_STATS_PURGE_LOCK_SEC = 86400  # at most one purge attempt per day (cluster-wide)

JOB_TYPE_OFFERS = "offers"
JOB_TYPE_CATALOG = "catalog"

TASK_STATS_INDICES = (
    OFFERS_TASK_STATS_INDEX,
    CATALOG_TASK_STATS_INDEX,
)

_worker_task_stats_indices_ready = False


def now_ms() -> int:
    return int(time.perf_counter() * 1000)


def sanitize_worker_for_doc_id(worker_id: str) -> str:
    """Make ``celery@host`` safe for Elasticsearch ``_id``."""
    safe = (worker_id or "unknown").strip()
    safe = safe.replace("@", "_at_")
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", safe)
    return safe or "unknown"


def format_minute_bucket(minute_bucket: datetime.datetime) -> str:
    if minute_bucket.tzinfo is None:
        minute_bucket = minute_bucket.replace(tzinfo=datetime.timezone.utc)
    minute_bucket = minute_bucket.astimezone(datetime.timezone.utc).replace(
        second=0, microsecond=0
    )
    return minute_bucket.strftime("%Y-%m-%dT%H:%M:00Z")


def build_task_stats_doc_id(
    job_type: str,
    marketplace: str,
    worker_id: str,
    pid: int,
    minute_bucket: datetime.datetime,
) -> str:
    """
    Document ``_id`` (unique per worker process, site, job type, and minute).

    Pattern::
        {job_type}:{marketplace}:{worker_safe}:pid{pid}:{minute_utc}

    Example::
        offers:us:celery_at_gcp-us-1:pid88421:2026-07-02T15:04:00Z
    """
    mp = (marketplace or "").strip().lower()
    jt = (job_type or "").strip().lower()
    worker_safe = sanitize_worker_for_doc_id(worker_id)
    minute_utc = format_minute_bucket(minute_bucket)
    return f"{jt}:{mp}:{worker_safe}:pid{pid}:{minute_utc}"


def empty_stats_bucket() -> Dict[str, int]:
    return {
        "num_asins": 0,
        "successful_asins": 0,
        "failed_asins": 0,
        "task_count": 0,
        "task_duration_ms": 0,
        "spapi_duration_ms": 0,
        "api_failed": 0,
        "throttle_count": 0,
        "spapi_success_duration_ms": 0,
        "spapi_success_count": 0,
        "fetch_gap_ms": 0,
        "fetch_gap_count": 0,
    }


class WorkerTaskStatsRecorder:
    """Aggregate task metrics in memory and flush per-minute docs to ES."""

    _buffers: Dict[str, Dict[str, Dict[str, Dict[datetime.datetime, Dict[str, int]]]]] = {}
    _last_task_finish_ts: Dict[str, float] = {}
    _flush_cursor: Optional[datetime.datetime] = None

    def __init__(
        self,
        product_service,
        worker: Dict[str, Any],
        marketplace: str,
        job_type: str,
    ):
        self.product_service = product_service
        self.worker = worker
        self.marketplace = (marketplace or "").strip().lower()
        self.job_type = (job_type or "").strip().lower()
        self.worker_id = worker["worker_id"]
        self.stats_index = self._index_for_job_type(self.job_type)

    @staticmethod
    def _index_for_job_type(job_type: str) -> str:
        if job_type == JOB_TYPE_OFFERS:
            return OFFERS_TASK_STATS_INDEX
        if job_type == JOB_TYPE_CATALOG:
            return CATALOG_TASK_STATS_INDEX
        raise ValueError(f"Unknown job_type: {job_type}")

    def compute_fetch_gap_ms(self) -> int:
        pid = int(self.worker.get("pid") or 0)
        key = f"{self.job_type}:{self.worker_id}:{pid}"
        now = time.time()
        if key not in WorkerTaskStatsRecorder._last_task_finish_ts:
            gap = 0
        else:
            gap = int(
                (now - WorkerTaskStatsRecorder._last_task_finish_ts[key]) * 1000
            )
        WorkerTaskStatsRecorder._last_task_finish_ts[key] = now
        return gap

    def record_task(
        self,
        *,
        total_asins: int,
        successful_asins: int,
        failed_asins: int,
        task_duration_ms: int,
        spapi_duration_ms: int,
        api_failed: int = 0,
        throttle_count: int = 0,
        fetch_gap_ms: int = 0,
    ) -> None:
        if not self.product_service:
            return

        now = datetime.datetime.now(datetime.timezone.utc)
        minute_key = now.replace(second=0, microsecond=0)

        job_buffers = WorkerTaskStatsRecorder._buffers.setdefault(
            self.job_type, {}
        )
        pid = int(self.worker.get("pid") or 0)
        worker_buffers = job_buffers.setdefault(self.worker_id, {})
        pid_buffers = worker_buffers.setdefault(pid, {})
        mp_buffers = pid_buffers.setdefault(self.marketplace, {})
        stats = mp_buffers.setdefault(minute_key, empty_stats_bucket())

        stats["successful_asins"] += successful_asins
        stats["failed_asins"] += failed_asins
        requested = max(total_asins, successful_asins + failed_asins)
        stats["num_asins"] += requested
        stats["task_duration_ms"] += task_duration_ms
        stats["spapi_duration_ms"] += spapi_duration_ms
        stats["task_count"] += 1
        stats["api_failed"] += api_failed
        stats["throttle_count"] += throttle_count
        stats["fetch_gap_ms"] += fetch_gap_ms
        stats["fetch_gap_count"] += 1

        if api_failed == 0:
            stats["spapi_success_duration_ms"] += spapi_duration_ms
            stats["spapi_success_count"] += 1

        self.maybe_flush()

    def maybe_flush(self) -> None:
        now_minute = datetime.datetime.now(datetime.timezone.utc).replace(
            second=0, microsecond=0
        )
        if WorkerTaskStatsRecorder._flush_cursor is None:
            WorkerTaskStatsRecorder._flush_cursor = now_minute
            return

        if now_minute <= WorkerTaskStatsRecorder._flush_cursor:
            return

        previous = WorkerTaskStatsRecorder._flush_cursor
        self._flush_all_before(now_minute)
        WorkerTaskStatsRecorder._flush_cursor = now_minute

    def flush_current_minute(self) -> None:
        """Force flush buckets strictly before the current UTC minute."""
        now_minute = datetime.datetime.now(datetime.timezone.utc).replace(
            second=0, microsecond=0
        )
        self._flush_all_before(now_minute)

    def _flush_all_before(self, cutoff_minute: datetime.datetime) -> None:
        job_buffers = WorkerTaskStatsRecorder._buffers.get(self.job_type, {})
        for worker_id, worker_buffers in list(job_buffers.items()):
            for pid, pid_buffers in list(worker_buffers.items()):
                for marketplace, mp_buffers in list(pid_buffers.items()):
                    for minute_key in list(mp_buffers.keys()):
                        if minute_key >= cutoff_minute:
                            continue
                        stats = mp_buffers.pop(minute_key, None)
                        if not stats or not stats.get("task_count"):
                            continue
                        doc = self._build_doc(
                            worker_id=worker_id,
                            pid=int(pid),
                            marketplace=marketplace,
                            minute_bucket=minute_key,
                            stats=stats,
                        )
                        self._save_doc(doc)

        # Drop empty nested dicts to limit memory growth.
        self._prune_empty_buffers(self.job_type)

    def _build_doc(
        self,
        worker_id: str,
        pid: int,
        marketplace: str,
        minute_bucket: datetime.datetime,
        stats: Dict[str, int],
    ) -> Dict[str, Any]:
        task_count = stats["task_count"]
        spapi_success_count = stats["spapi_success_count"]
        fetch_gap_count = stats["fetch_gap_count"]
        minute_iso = format_minute_bucket(minute_bucket)

        return {
            "_id": build_task_stats_doc_id(
                self.job_type,
                marketplace,
                worker_id,
                pid,
                minute_bucket,
            ),
            "job_type": self.job_type,
            "marketplace": marketplace,
            "minute": minute_iso,
            "time": minute_iso,
            "worker": worker_id,
            "num_asins": stats["num_asins"],
            "successful_asins": stats["successful_asins"],
            "failed_asins": stats["failed_asins"],
            "api_failed": stats["api_failed"],
            "throttle_count": stats["throttle_count"],
            "task_count": task_count,
            "task_duration_ms": stats["task_duration_ms"],
            "spapi_duration_ms": stats["spapi_duration_ms"],
            "spapi_success_duration_ms": stats["spapi_success_duration_ms"],
            "spapi_success_count": spapi_success_count,
            "fetch_gap_ms": stats["fetch_gap_ms"],
            "fetch_gap_count": fetch_gap_count,
            "avg_task_duration_ms": (
                stats["task_duration_ms"] // task_count if task_count else 0
            ),
            "avg_spapi_duration_ms": (
                stats["spapi_duration_ms"] // task_count if task_count else 0
            ),
            "avg_spapi_success_ms": (
                stats["spapi_success_duration_ms"] // spapi_success_count
                if spapi_success_count
                else 0
            ),
            "avg_fetch_gap_ms": (
                stats["fetch_gap_ms"] // fetch_gap_count
                if fetch_gap_count
                else 0
            ),
        }

    def _save_doc(self, doc: Dict[str, Any]) -> None:
        try:
            self.product_service.save_products(self.stats_index, [doc])
        except Exception:
            logger.warning("[TaskStatsSaveError] index=%s doc_id=%s", self.stats_index, doc.get("_id"))
            logger.exception("ES task stats write failed")

    @classmethod
    def _prune_empty_buffers(cls, job_type: str) -> None:
        job_buffers = cls._buffers.get(job_type)
        if not job_buffers:
            return
        for worker_id in list(job_buffers.keys()):
            worker_buffers = job_buffers[worker_id]
            for pid in list(worker_buffers.keys()):
                pid_buffers = worker_buffers[pid]
                for marketplace in list(pid_buffers.keys()):
                    if not pid_buffers[marketplace]:
                        del pid_buffers[marketplace]
                if not pid_buffers:
                    del worker_buffers[pid]
            if not worker_buffers:
                del job_buffers[worker_id]
        if not job_buffers:
            cls._buffers.pop(job_type, None)


def ensure_worker_task_stats_indices(product_service) -> None:
    """Create unified offers/catalog task-stats indices (all marketplaces)."""
    global _worker_task_stats_indices_ready
    if _worker_task_stats_indices_ready:
        return
    if product_service is None:
        return

    settings = stats_index_settings()
    try:
        for index_name in TASK_STATS_INDICES:
            product_service.ensure_indice(index_name, settings=settings)
    except Exception:
        logger.exception(
            "[EnsureWorkerTaskStatsIndices] failed for %s",
            ", ".join(TASK_STATS_INDICES),
        )
        return
    _worker_task_stats_indices_ready = True
    maybe_purge_old_task_stats(product_service)


def get_task_stats_retention_days() -> int:
    """How long to keep minute-level task stats docs in ES (default 7)."""
    raw = os.getenv("SPAPI_TASK_STATS_RETENTION_DAYS", "").strip()
    if not raw:
        return DEFAULT_TASK_STATS_RETENTION_DAYS
    try:
        days = int(raw)
    except ValueError:
        return DEFAULT_TASK_STATS_RETENTION_DAYS
    return max(days, 0)


def purge_cutoff_minute(retention_days: int) -> datetime.datetime:
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
        days=retention_days
    )
    return cutoff.replace(second=0, microsecond=0)


def purge_old_task_stats(product_service, *, retention_days: Optional[int] = None) -> int:
    """
    Delete task-stats documents older than ``retention_days`` from both indices.

    Returns total documents deleted (best effort; 0 if disabled or ES unavailable).
    """
    if product_service is None:
        return 0

    days = retention_days if retention_days is not None else get_task_stats_retention_days()
    if days <= 0:
        return 0

    cutoff_iso = format_minute_bucket(purge_cutoff_minute(days))
    body = {
        "query": {
            "range": {
                "minute": {
                    "lt": cutoff_iso,
                    "format": "strict_date_optional_time",
                }
            }
        }
    }

    deleted = 0
    for index_name in TASK_STATS_INDICES:
        try:
            if not product_service.index_exists(index_name):
                continue
            resp = product_service.esclient.delete_by_query(
                index=index_name,
                body=body,
                conflicts="proceed",
                wait_for_completion=True,
                request_timeout=120,
            )
            removed = int(resp.get("deleted") or 0)
            deleted += removed
            if removed:
                logger.info(
                    "[TaskStatsPurge] index=%s deleted=%s older_than=%s",
                    index_name,
                    removed,
                    cutoff_iso,
                )
        except Exception:
            logger.exception(
                "[TaskStatsPurge] failed index=%s older_than=%s",
                index_name,
                cutoff_iso,
            )
    return deleted


def _acquire_task_stats_purge_lock() -> bool:
    """One purge per day cluster-wide (Redis SET NX on broker)."""
    try:
        import redis
        from amazon_spapi.config.env import get_broker_url
        from amazon_spapi.scheduling.dedup import broker_url_to_dedup_redis_url

        client = redis.from_url(
            broker_url_to_dedup_redis_url(get_broker_url(), db=0),
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        return bool(
            client.set(
                TASK_STATS_PURGE_LOCK_KEY,
                b"1",
                nx=True,
                ex=TASK_STATS_PURGE_LOCK_SEC,
            )
        )
    except Exception:
        logger.debug("[TaskStatsPurge] lock unavailable; skipping scheduled purge")
        return False


def maybe_purge_old_task_stats(product_service) -> None:
    """Run retention purge when a worker starts, at most once per day cluster-wide."""
    if get_task_stats_retention_days() <= 0:
        return
    if not _acquire_task_stats_purge_lock():
        return
    purge_old_task_stats(product_service)


def ensure_item_offers_aux_indices(product_service) -> None:
    """Indices used by offer refresh aside from task stats."""
    from amazon_spapi.amazon.offers.refresh import MISSING_OFFER_ASINS_INDEX

    if product_service is None:
        return
    try:
        product_service.ensure_indice(MISSING_OFFER_ASINS_INDEX)
    except Exception:
        logger.exception(
            "[EnsureItemOffersAuxIndices] failed for %s",
            MISSING_OFFER_ASINS_INDEX,
        )
