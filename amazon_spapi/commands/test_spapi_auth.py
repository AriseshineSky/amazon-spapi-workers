# -*- coding: utf-8 -*-
"""Smoke test SP-API credentials with a single API call."""

from __future__ import annotations

import argparse
import sys
from typing import Optional

DEFAULT_TEST_ASIN = "B09V3KXJPB"


def _item_title(item) -> str:
    if item is None:
        return ""
    if isinstance(item, dict):
        summaries = item.get("summaries") or []
        if summaries and isinstance(summaries[0], dict):
            title = summaries[0].get("itemName") or summaries[0].get("title")
            if title:
                return str(title)
        title = item.get("title") or item.get("itemName")
        if title:
            return str(title)
    title = getattr(item, "title", None) or getattr(item, "itemName", None)
    return str(title) if title else ""


def test_catalog(spapi, marketplace: str, asin: str) -> None:
    print(f"Calling Catalog API (searchCatalogItems) — {marketplace} / {asin}")
    response = spapi.search_catalog_items([asin], marketplace=marketplace)
    items = None
    if response is not None:
        payload = getattr(response, "payload", response)
        if isinstance(payload, dict):
            items = payload.get("items") or payload.get("Items")
        elif isinstance(payload, list):
            items = payload
    count = len(items) if items else 0
    print(f"OK: catalog returned {count} item(s)")
    if items:
        title = _item_title(items[0])
        if title:
            print(f"title: {title[:120]}")


def test_offers(spapi, marketplace: str, asin: str) -> None:
    print(f"Calling Offers API (getItemOffersBatch) — {marketplace} / {asin}")
    offers = spapi.get_item_offers_batch(marketplace, [asin])
    count = len(offers) if offers else 0
    print(f"OK: offers returned {count} result(s)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Test Amazon SP-API credentials with one API request.",
    )
    parser.add_argument(
        "-m",
        "--marketplace",
        default="US",
        help="Marketplace code (default: US)",
    )
    parser.add_argument(
        "-a",
        "--asin",
        default=DEFAULT_TEST_ASIN,
        help=f"Test ASIN (default: {DEFAULT_TEST_ASIN})",
    )
    parser.add_argument(
        "--offers",
        action="store_true",
        help="Test Offers API instead of Catalog API",
    )
    parser.add_argument(
        "--both",
        action="store_true",
        help="Test both Catalog and Offers APIs",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    marketplace = args.marketplace.upper()
    asin = args.asin.strip().upper()

    try:
        from amazon_spapi.platform import get_spapi

        spapi = get_spapi()
    except Exception as exc:
        print(f"FAIL: could not load config — {exc}", file=sys.stderr)
        return 1

    try:
        if args.both:
            test_catalog(spapi, marketplace, asin)
            print()
            test_offers(spapi, marketplace, asin)
        elif args.offers:
            test_offers(spapi, marketplace, asin)
        else:
            test_catalog(spapi, marketplace, asin)
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    print("SP-API authorization looks good.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
