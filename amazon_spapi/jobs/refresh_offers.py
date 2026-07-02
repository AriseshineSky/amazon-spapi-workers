# -*- coding: utf-8 -*-
"""Background job: refresh Amazon marketplace offers."""

import sentry_sdk
from celery.exceptions import Ignore, Reject
from celery.utils.log import get_task_logger
from amazon_spapi.spapi import exceptions_not_retry, exceptions_to_retry
from sp_api.auth.exceptions import AuthorizationError
from sp_api.base.exceptions import SellingApiForbiddenException

from amazon_spapi.amazon.offers.refresh import RefreshMarketplaceOffers
from amazon_spapi.worker.worker_meta import build_worker_meta
from amazon_spapi.platform import sentry_enabled
from amazon_spapi.worker.app import app
from amazon_spapi.worker.worker_deps import WorkerContext

logger = get_task_logger(__name__)


@app.task(base=WorkerContext, bind=True, acks_late=True, rate_limit="8/m")
def refresh_offers(
    self,
    marketplace,
    asins,
    condition="new",
    ttl=24,
    force=False,
    callback=None,
):
    use_case = RefreshMarketplaceOffers(
        self.spapi,
        self.offer_service,
        marketplace,
        asins,
        condition,
        product_service=self.product_service,
        worker=build_worker_meta(self.request),
    )
    try:
        use_case.run()
    except (SellingApiForbiddenException, AuthorizationError) as e:
        logger.exception(e)
        app.control.broadcast("shutdown", destination=[self.request.hostname])
        try:
            self.bot.send_message(
                self.group_chat_id,
                (
                    f"[SellingApiForbidden] Host: {self.request.hostname}, "
                    f"API: GetItemOffersBatch\n"
                ),
            )
        except Exception:
            pass
        raise Reject(str(e), requeue=True)
    except exceptions_to_retry as e:
        self.rejected_tasks_cnt += 1
        if self.rejected_tasks_cnt > 250:
            try:
                message = (
                    f"[OffersRefreshRejectedReset] Host: "
                    f"{self.request.hostname}, API: GetItemOffersBatch, "
                    f"Error: {e}\n"
                )
                self.bot.send_message(self.group_chat_id, message)
            except Exception:
                pass
            self.rejected_tasks_cnt = 0
        raise Reject(str(e), requeue=True)
    except exceptions_not_retry as e:
        if sentry_enabled:
            sentry_sdk.capture_exception(e)
        logger.exception(e)
        raise Ignore()
    except Exception as e:
        if sentry_enabled:
            sentry_sdk.capture_exception(e)
        logger.exception(e)
        raise Ignore()


__all__ = ["refresh_offers"]
