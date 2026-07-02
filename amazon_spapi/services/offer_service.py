# -*- coding: utf-8 -*-
"""Elasticsearch-backed Amazon offer storage."""

import json
from datetime import datetime

from elasticsearch import Elasticsearch
from elasticsearch import helpers

from amazon_spapi.log import logger
from amazon_spapi.services.elasticsearch import (
    EsClientError,
    EsServerError,
    EsUnauthorizedError,
    es_retry,
)


class EsOfferService:
    def __init__(self, host, port, user, password, **kwargs):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.esclient = Elasticsearch(
            hosts=host,
            port=port,
            http_auth=(user, password),
            retry_on_timeout=True,
        )
        self.active = True

    def is_active(self):
        return self.active

    def deactivate(self, reason=""):
        self.active = False
        logger.warning("[EsOfferService] deactivated: %s", reason)

    def search(self, *args, **kwargs):
        if not self.is_active():
            return False

        wrapped_search = es_retry(self.esclient.search)
        try:
            return wrapped_search(*args, **kwargs)
        except EsServerError as e:
            logger.exception(e)
            return False
        except EsClientError as e:
            logger.exception(e)
            return None
        except EsUnauthorizedError as e:
            logger.exception(e)
            self.deactivate(str(e))
            return False
        except Exception as e:
            logger.exception(e)
            return None

    def _bulk(self, *args, **kwargs):
        if not self.is_active():
            return False

        opts = {"max_retries": 3}
        opts.update(kwargs)
        wrapped_bulk = es_retry(helpers.bulk)
        try:
            return wrapped_bulk(self.esclient, *args, **opts)
        except EsServerError as e:
            logger.exception(e)
            return False
        except EsClientError as e:
            logger.exception(e)
            return None
        except EsUnauthorizedError as e:
            logger.exception(e)
            self.deactivate(str(e))
            return False
        except Exception as e:
            logger.exception(e)
            return None

    def save_item_offers(
        self, offer_type, offers, country_code="us", condition="any"
    ):
        if not self.active:
            return False

        condition = condition.lower()
        if condition != "new":
            condition = "any"

        common_args = {
            "_op_type": "index",
            "_index": "{}_{}_{}".format(
                offer_type, country_code.lower(), condition
            ),
            "_type": "_doc",
        }
        cur_time = datetime.strftime(datetime.utcnow(), "%Y-%m-%dT%H:%M:%S")
        service_offers = []
        for asin, item_offer in offers.items():
            service_offer = dict(common_args)
            service_offer["_id"] = asin
            service_offer["_source"] = {
                "asin": asin,
                "offers": json.dumps(item_offer["offers"]),
                "summary": json.dumps(item_offer.get("summary", "")),
                "time": cur_time,
            }
            if "errors" in item_offer:
                service_offer["_source"]["errors"] = item_offer["errors"]
            service_offers.append(service_offer)

        return self._bulk(service_offers)

    def search_offers(self, offer_type, asins, country_code, condition):
        if not self.active:
            return False

        condition = condition.lower()
        if condition != "new":
            condition = "any"
        params = {
            "index": "{}_{}_{}".format(
                offer_type, country_code.lower(), condition
            ),
            "from_": 0,
            "size": len(asins),
            "doc_type": "_doc",
            "body": {"query": {"terms": {"_id": asins}}},
        }
        return self.search(**params)

    def get_offers(self, marketplace, asins, condition):
        """Return ``{asin: _source}`` from the lowest-offer listings index."""
        result = self.search_offers(
            "lowest_offer_listings", list(asins), marketplace, condition
        )
        if not result:
            return {}

        hits = result
        while isinstance(hits, dict) and "hits" in hits:
            hits = hits["hits"]
        if isinstance(hits, dict) and "hits" in hits:
            hits = hits["hits"]

        if not isinstance(hits, list):
            return hits if isinstance(hits, dict) else {}

        return {
            hit["_source"]["asin"]: hit["_source"]
            for hit in hits
            if hit and hit.get("_source", {}).get("asin")
        }
