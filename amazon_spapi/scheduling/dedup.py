# -*- coding: utf-8 -*-
"""Prevent duplicate offer-refresh work from entering the broker."""

from urllib.parse import urlparse


def broker_url_to_dedup_redis_url(broker_url, db=6):
    parsed = urlparse(broker_url)
    auth = ""
    if parsed.username:
        password = parsed.password or ""
        auth = "{}:{}@".format(parsed.username, password)
    host = parsed.hostname or "localhost"
    port = parsed.port or 6379
    return "redis://{}{}:{}/{}".format(auth, host, port, db)


def _dedup_key(marketplace, condition, asin):
    return "enqueue:offers:{}:{}:{}".format(
        marketplace.lower(), condition.lower(), asin
    )


def claim_asins_for_enqueue(
    redis_client, marketplace, condition, asins, ttl_sec
):
    if not redis_client or not asins:
        return list(asins) if asins else []

    claimed = []
    pipe = redis_client.pipeline()
    keys = []
    for asin in asins:
        key = _dedup_key(marketplace, condition, asin)
        keys.append((asin, key))
        pipe.set(key, b"1", nx=True, ex=int(ttl_sec))

    results = pipe.execute()
    for (asin, _), ok in zip(keys, results):
        if ok:
            claimed.append(asin)
    return claimed
