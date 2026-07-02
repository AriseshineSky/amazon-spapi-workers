# -*- coding: utf-8 -*-
"""Filter ASINs whose marketplace offers are missing or past TTL."""

import datetime

import dateutil.parser


def filter_stale_offer_asins(
    offer_service,
    offer_type,
    asins,
    marketplace,
    condition,
    ttl_hours,
    force=False,
):
    if force:
        return list(asins)

    now = datetime.datetime.utcnow()
    offer_expire_time = now - datetime.timedelta(hours=ttl_hours)
    stale = {}

    result = offer_service.search_offers(
        offer_type, asins, marketplace, condition
    )
    if not result:
        return list(asins)

    while isinstance(result, dict) and "hits" in result:
        result = result["hits"]

    if isinstance(result, list):
        offers = {
            offer["_source"]["asin"]: offer["_source"]
            for offer in result
            if offer
        }
    else:
        offers = result if isinstance(result, dict) else {}

    for asin in asins:
        offer = offers.get(asin)
        if not offer:
            stale[asin] = None
            continue

        offer_time_s = offer.get("time")
        if not offer_time_s or not offer.get("offers"):
            stale[asin] = None
            continue

        try:
            if dateutil.parser.parse(offer_time_s) < offer_expire_time:
                stale[asin] = None
        except Exception:
            stale[asin] = None

    return list(stale.keys())
