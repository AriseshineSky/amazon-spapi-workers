# -*- coding: utf-8 -*-
"""Worker layout and Celery rate limits from environment / optional config.ini."""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass

from amazon_spapi.worker.queue_names import (
    marketplace_catalog_queue,
    marketplace_offers_queue,
)

DEFAULT_OFFERS_TASK_RATE = "16/m"
DEFAULT_CATALOG_TASK_RATE = "1/s"
DEFAULT_FETCH_PRODUCTS_TASK_RATE = "6/m"
DEFAULT_OFFERS_CONCURRENCY = 1
DEFAULT_CATALOG_CONCURRENCY = 1

ENV_OFFERS_MARKETPLACES = "OFFERS_MARKETPLACES"
ENV_OFFERS_QUEUES = "OFFERS_QUEUES"
ENV_OFFERS_CONCURRENCY = "OFFERS_CONCURRENCY"
ENV_OFFERS_WORKER_NAME = "OFFERS_WORKER_NAME"
ENV_OFFERS_TASK_RATE = "OFFERS_TASK_RATE"

ENV_CATALOG_MARKETPLACES = "CATALOG_MARKETPLACES"
ENV_CATALOG_QUEUES = "CATALOG_QUEUES"
ENV_CATALOG_CONCURRENCY = "CATALOG_CONCURRENCY"
ENV_CATALOG_WORKER_NAME = "CATALOG_WORKER_NAME"
ENV_CATALOG_TASK_RATE = "CATALOG_TASK_RATE"

ENV_FETCH_PRODUCTS_TASK_RATE = "FETCH_PRODUCTS_TASK_RATE"


def sanitize_worker_name(name: str) -> str:
    import re

    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", (name or "").strip())
    return cleaned.strip("-") or "worker"


def default_worker_name(kind: str, marketplaces: tuple[str, ...]) -> str:
    if not marketplaces:
        return kind
    if len(marketplaces) == 1:
        return "{}-{}".format(kind, marketplaces[0])
    return "{}-{}".format(kind, "-".join(marketplaces))


def resolve_worker_name(
    kind: str,
    marketplaces: tuple[str, ...],
    explicit: str = "",
) -> str:
    raw = (explicit or "").strip()
    if raw:
        return sanitize_worker_name(raw)
    return sanitize_worker_name(default_worker_name(kind, marketplaces))


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _parse_marketplaces(raw: str) -> list[str]:
    if not raw:
        return []
    return [part.strip().lower() for part in raw.split(",") if part.strip()]


def _parse_queues(raw: str) -> list[str]:
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def _parse_int(raw: str, default: int) -> int:
    if not raw:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(1, value)


def _marketplaces_from_queues(queues: list[str], prefix: str) -> list[str]:
    """Infer marketplace codes from queue names like SpapiItemOffersUpdate_US."""
    out = []
    needle = prefix
    for queue in queues:
        if needle in queue:
            out.append(queue.split("_")[-1].lower())
    return out


def _resolve_side(
    *,
    marketplaces_env: str,
    queues_env: str,
    queue_builder,
    queue_prefix: str,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    queues_raw = _parse_queues(_env(queues_env))
    if queues_raw:
        queues = tuple(queues_raw)
        marketplaces = tuple(_marketplaces_from_queues(list(queues), queue_prefix))
        if not marketplaces:
            marketplaces = tuple(_parse_marketplaces(_env(marketplaces_env)))
        return marketplaces, queues

    marketplaces = tuple(_parse_marketplaces(_env(marketplaces_env)))
    if not marketplaces:
        return (), ()
    queues = tuple(queue_builder(mp) for mp in marketplaces)
    return marketplaces, queues


@dataclass(frozen=True)
class WorkersConfig:
    offer_marketplaces: tuple[str, ...]
    catalog_marketplaces: tuple[str, ...]
    offer_queues: tuple[str, ...] = ()
    catalog_queues: tuple[str, ...] = ()
    offers_concurrency: int = DEFAULT_OFFERS_CONCURRENCY
    catalog_concurrency: int = DEFAULT_CATALOG_CONCURRENCY
    offers_task_rate: str = DEFAULT_OFFERS_TASK_RATE
    catalog_task_rate: str = DEFAULT_CATALOG_TASK_RATE
    fetch_products_task_rate: str = DEFAULT_FETCH_PRODUCTS_TASK_RATE
    offers_worker_name: str = ""
    catalog_worker_name: str = ""

    def resolved_offers_worker_name(self) -> str:
        return resolve_worker_name(
            "offers", self.offer_marketplaces, self.offers_worker_name
        )

    def resolved_catalog_worker_name(self) -> str:
        return resolve_worker_name(
            "catalog", self.catalog_marketplaces, self.catalog_worker_name
        )

    @property
    def has_offers(self) -> bool:
        return bool(self.offer_queues)

    @property
    def has_catalog(self) -> bool:
        return bool(self.catalog_queues)

    def offers_queue_csv(self) -> str:
        return ",".join(self.offer_queues)

    def catalog_queue_csv(self) -> str:
        return ",".join(self.catalog_queues)


def workers_section_from_config(config: dict) -> dict:
    return dict(config.get("workers") or {})


def load_workers_config_from_env() -> WorkersConfig:
    offer_mps, offer_queues = _resolve_side(
        marketplaces_env=ENV_OFFERS_MARKETPLACES,
        queues_env=ENV_OFFERS_QUEUES,
        queue_builder=marketplace_offers_queue,
        queue_prefix="SpapiItemOffersUpdate_",
    )
    catalog_mps, catalog_queues = _resolve_side(
        marketplaces_env=ENV_CATALOG_MARKETPLACES,
        queues_env=ENV_CATALOG_QUEUES,
        queue_builder=marketplace_catalog_queue,
        queue_prefix="SpapiCatalogItemsUpdate_",
    )
    return WorkersConfig(
        offer_marketplaces=offer_mps,
        catalog_marketplaces=catalog_mps,
        offer_queues=offer_queues,
        catalog_queues=catalog_queues,
        offers_concurrency=_parse_int(
            _env(ENV_OFFERS_CONCURRENCY), DEFAULT_OFFERS_CONCURRENCY
        ),
        catalog_concurrency=_parse_int(
            _env(ENV_CATALOG_CONCURRENCY), DEFAULT_CATALOG_CONCURRENCY
        ),
        offers_task_rate=_env(ENV_OFFERS_TASK_RATE) or DEFAULT_OFFERS_TASK_RATE,
        catalog_task_rate=_env(ENV_CATALOG_TASK_RATE) or DEFAULT_CATALOG_TASK_RATE,
        fetch_products_task_rate=_env(ENV_FETCH_PRODUCTS_TASK_RATE)
        or DEFAULT_FETCH_PRODUCTS_TASK_RATE,
        offers_worker_name=_env(ENV_OFFERS_WORKER_NAME),
        catalog_worker_name=_env(ENV_CATALOG_WORKER_NAME),
    )


def load_workers_config_from_ini(config: dict) -> WorkersConfig:
    section = workers_section_from_config(config)
    offer_mps = tuple(_parse_marketplaces(section.get("offer_marketplaces", "")))
    catalog_mps = tuple(_parse_marketplaces(section.get("catalog_marketplaces", "")))
    return WorkersConfig(
        offer_marketplaces=offer_mps,
        catalog_marketplaces=catalog_mps,
        offer_queues=tuple(marketplace_offers_queue(mp) for mp in offer_mps),
        catalog_queues=tuple(marketplace_catalog_queue(mp) for mp in catalog_mps),
        offers_concurrency=_parse_int(
            section.get("offers_concurrency"), DEFAULT_OFFERS_CONCURRENCY
        ),
        catalog_concurrency=_parse_int(
            section.get("catalog_concurrency"), DEFAULT_CATALOG_CONCURRENCY
        ),
        offers_task_rate=(
            section.get("offers_task_rate") or DEFAULT_OFFERS_TASK_RATE
        ).strip(),
        catalog_task_rate=(
            section.get("catalog_task_rate") or DEFAULT_CATALOG_TASK_RATE
        ).strip(),
        fetch_products_task_rate=(
            section.get("fetch_products_task_rate")
            or DEFAULT_FETCH_PRODUCTS_TASK_RATE
        ).strip(),
        offers_worker_name=(section.get("offers_worker_name") or "").strip(),
        catalog_worker_name=(section.get("catalog_worker_name") or "").strip(),
    )


def _env_workers_configured() -> bool:
    keys = (
        ENV_OFFERS_MARKETPLACES,
        ENV_OFFERS_QUEUES,
        ENV_CATALOG_MARKETPLACES,
        ENV_CATALOG_QUEUES,
        ENV_OFFERS_CONCURRENCY,
        ENV_CATALOG_CONCURRENCY,
        ENV_OFFERS_WORKER_NAME,
        ENV_CATALOG_WORKER_NAME,
        ENV_OFFERS_TASK_RATE,
        ENV_CATALOG_TASK_RATE,
    )
    return any(_env(key) for key in keys)


def load_workers_config(config: dict | None = None) -> WorkersConfig:
    """Load worker layout from environment variables (/etc/conf.d/celery_spapi)."""
    del config
    return load_workers_config_from_env()


def load_workers_config_safe(config: dict | None = None) -> WorkersConfig:
    try:
        return load_workers_config(config)
    except Exception:
        if _env_workers_configured():
            try:
                return load_workers_config_from_env()
            except Exception:
                pass
        return WorkersConfig(
            offer_marketplaces=(),
            catalog_marketplaces=(),
            offer_queues=(),
            catalog_queues=(),
        )


def get_task_rate_limits(config: dict | None = None) -> dict:
    workers = load_workers_config_safe(config)
    return {
        "amazon_spapi.jobs.refresh_offers.refresh_offers": {
            "rate_limit": workers.offers_task_rate,
        },
        "amazon_spapi.jobs.refresh_catalog.refresh_catalog": {
            "rate_limit": workers.catalog_task_rate,
        },
        "amazon_spapi.jobs.fetch_products.fetch_products": {
            "rate_limit": workers.fetch_products_task_rate,
        },
    }


def _print_systemd_plan(workers: WorkersConfig) -> None:
    if workers.has_offers:
        print(
            "offers",
            workers.offers_queue_csv(),
            workers.offers_concurrency,
            workers.resolved_offers_worker_name(),
            sep="\t",
        )
    if workers.has_catalog:
        print(
            "catalog",
            workers.catalog_queue_csv(),
            workers.catalog_concurrency,
            workers.resolved_catalog_worker_name(),
            sep="\t",
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read worker layout from environment or config.ini."
    )
    parser.add_argument(
        "--env-file",
        help="Source this file before reading environment (KEY=VALUE).",
    )
    parser.add_argument(
        "--systemd-plan",
        action="store_true",
        help="Print tab-separated rows: kind<TAB>queues<TAB>concurrency<TAB>worker_name",
    )
    args = parser.parse_args(argv)

    if args.env_file:
        _load_env_file(args.env_file)

    workers = load_workers_config()

    if args.systemd_plan:
        if not workers.has_offers and not workers.has_catalog:
            print(
                "Set OFFERS_MARKETPLACES/OFFERS_QUEUES and/or "
                "CATALOG_MARKETPLACES/CATALOG_QUEUES in environment",
                file=sys.stderr,
            )
            return 1
        _print_systemd_plan(workers)
        return 0

    print(workers)
    return 0


def _load_env_file(path: str) -> None:
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if key and key not in os.environ:
                os.environ[key] = value


if __name__ == "__main__":
    raise SystemExit(main())
