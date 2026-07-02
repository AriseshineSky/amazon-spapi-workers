# -*- coding: utf-8 -*-
"""Background job: refresh Amazon catalog metadata."""

import sentry_sdk
from celery.exceptions import Ignore, Reject
from celery.utils.log import get_task_logger
from amazon_spapi.spapi import exceptions_not_retry, exceptions_to_retry
from sp_api.base.exceptions import SellingApiForbiddenException

from amazon_spapi.amazon.catalog.refresh import RefreshMarketplaceCatalog
from amazon_spapi.platform import sentry_enabled
from amazon_spapi.worker.app import app
from amazon_spapi.worker.worker_deps import WorkerContext
from amazon_spapi.worker.worker_meta import build_worker_meta

logger = get_task_logger(__name__)


@app.task(base=WorkerContext, bind=True, acks_late=True)
def refresh_catalog(
    self,
    marketplace,
    asins,
    ttl=168,
    force=False,
    callback=None,
):
    use_case = RefreshMarketplaceCatalog(
        self.spapi,
        self.product_service,
        marketplace,
        asins,
        worker=build_worker_meta(self.request),
    )
    try:
        use_case.run()
    except SellingApiForbiddenException as e:
        logger.exception(e)
        app.control.broadcast("shutdown", destination=[self.request.hostname])
        try:
            self.bot.send_message(
                self.group_chat_id,
                (
                    f"[SellingApiForbidden] Host: {self.request.hostname}, "
                    f"API: GetCatalogItems, Error: {e}\n"
                ),
            )
        except Exception:
            pass
        raise Reject(str(e), requeue=True)
    except exceptions_to_retry as e:
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


__all__ = ["refresh_catalog", "build_worker_meta"]
