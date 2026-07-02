# -*- coding: utf-8 -*-
"""Per-task worker context: lazy SP-API and ES connections."""

from celery import Task
from celery.utils.log import get_task_logger
from amazon_spapi.spapi import Spapi

from amazon_spapi.platform import (
    get_bot,
    get_config,
    get_offer_service,
    get_product_service,
)

logger = get_task_logger(__name__)


class WorkerContext(Task):
    _cfg = None
    _spapi = None
    _offer_service = None
    _product_service = None
    _bot = None
    rejected_tasks_cnt = 0

    @property
    def spapi(self):
        if self._spapi is None:
            spapi_cfg = self.cfg["spapi"]
            credentials = {
                "refresh_token": spapi_cfg["lwa_refresh_token"],
                "lwa_app_id": spapi_cfg["lwa_client_id"],
                "lwa_client_secret": spapi_cfg["lwa_client_secret"],
                "aws_access_key": spapi_cfg["aws_access_key"],
                "aws_secret_key": spapi_cfg["aws_secret_key"],
            }
            self._spapi = Spapi(credentials)
        return self._spapi

    @property
    def offer_service(self):
        if self._offer_service is None:
            self._offer_service = get_offer_service()
        return self._offer_service

    @property
    def product_service(self):
        if self._product_service is None:
            self._product_service = get_product_service()
        return self._product_service

    @property
    def bot(self):
        if self._bot is None:
            self._bot = get_bot()
        return self._bot

    @property
    def group_chat_id(self):
        from amazon_spapi.platform import get_group_chat_id

        return get_group_chat_id()

    @property
    def cfg(self):
        if self._cfg is None:
            self._cfg = get_config()
        return self._cfg
