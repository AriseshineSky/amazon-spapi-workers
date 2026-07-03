# -*- coding: utf-8 -*-
"""Tests for offer TTL filtering before enqueue."""

import datetime

from amazon_spapi.amazon.listing_rules.stale_offers import filter_stale_offer_asins


class _FakeOfferService:
    def __init__(self, offers_by_asin):
        self.offers_by_asin = offers_by_asin

    def search_offers(self, offer_type, asins, marketplace, condition):
        hits = []
        for asin in asins:
            src = self.offers_by_asin.get(asin)
            if src is not None:
                hits.append({"_source": src})
        return {"hits": {"hits": hits}}


def test_filter_stale_skips_fresh_offer():
    fresh_time = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
    service = _FakeOfferService(
        {
            "B000000001": {
                "asin": "B000000001",
                "time": fresh_time,
                "offers": "[{}]",
            }
        }
    )
    stale = filter_stale_offer_asins(
        service, "lowest_offer_listings", ["B000000001"], "ca", "new", 36
    )
    assert stale == []


def test_filter_stale_includes_missing_and_expired():
    old_time = (datetime.datetime.utcnow() - datetime.timedelta(hours=48)).strftime(
        "%Y-%m-%dT%H:%M:%S"
    )
    service = _FakeOfferService(
        {
            "B000000002": {
                "asin": "B000000002",
                "time": old_time,
                "offers": "[{}]",
            }
        }
    )
    stale = filter_stale_offer_asins(
        service,
        "lowest_offer_listings",
        ["B000000001", "B000000002"],
        "ca",
        "new",
        36,
    )
    assert stale == ["B000000001", "B000000002"]


def test_filter_stale_force_returns_all():
    service = _FakeOfferService({})
    asins = ["B000000003"]
    assert filter_stale_offer_asins(
        service, "lowest_offer_listings", asins, "ca", "new", 36, force=True
    ) == asins


if __name__ == "__main__":
    test_filter_stale_skips_fresh_offer()
    test_filter_stale_includes_missing_and_expired()
    test_filter_stale_force_returns_all()
    print("ok")
