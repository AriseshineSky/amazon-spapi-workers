# -*- coding: utf-8 -*-
"""Background job: fetch Amazon product offers and catalog snapshots."""

import sentry_sdk
from celery.exceptions import Ignore, Reject
from celery.utils.log import get_task_logger
from sp_api.base.exceptions import SellingApiForbiddenException

from amazon_spapi.amazon.products.fetch import FetchMarketplaceProducts
from amazon_spapi.platform import sentry_enabled
from amazon_spapi.worker.app import app
from amazon_spapi.worker.worker_deps import WorkerContext

logger = get_task_logger(__name__)


@app.task(base=WorkerContext, bind=True, acks_late=True)
def fetch_products(self, marketplace, asins, condition="new"):
    use_case = FetchMarketplaceProducts(
        self.spapi,
        self.offer_service,
        self.product_service,
        marketplace,
        asins,
        condition,
    )
    try:
        use_case.run()
    except SellingApiForbiddenException as e:
        logger.exception(e)
        app.control.broadcast("shutdown", destination=[self.request.hostname])
        try:
            self.bot.send_message(
                self.group_chat_id,
                "[SellingApiForbidden] Host: {}\n".format(
                    self.request.hostname
                ),
            )
        except Exception:
            pass
        raise Reject(str(e), requeue=True)
    except Exception as e:
        if sentry_enabled:
            sentry_sdk.capture_exception(e)
        logger.exception(e)
        raise Ignore()


__all__ = ["fetch_products"]
