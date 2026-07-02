# -*- coding: utf-8 -*-
"""Runtime wiring: config, Elasticsearch/SP-API clients, alerts."""

import os

import sentry_sdk
from amazon_spapi.services.offer_service import EsOfferService
from amazon_spapi.spapi import Spapi
from amazon_spapi.services.product_service import ProductService

from amazon_spapi.config.paths import (
    CONFIG_ENV_VAR,
    DEFAULT_CONFIG_PATH,
    LEGACY_CONFIG_ENV_VAR,
    LEGACY_EVERYMARKET_CONFIG_ENV_VAR,
    LEGACY_MWS_CONFIG_ENV_VAR,
)
from amazon_spapi.platform.config_loader import IniConfigLoader
from amazon_spapi.platform.telegram import TelegramBot

_cfg = None


def _config_path():
    return os.getenv(
        CONFIG_ENV_VAR,
        os.getenv(
            LEGACY_EVERYMARKET_CONFIG_ENV_VAR,
            os.getenv(
                LEGACY_CONFIG_ENV_VAR,
                os.getenv(LEGACY_MWS_CONFIG_ENV_VAR, DEFAULT_CONFIG_PATH),
            ),
        ),
    )


def get_config():
    global _cfg
    if _cfg is None:
        config = IniConfigLoader(_config_path(), False)
        _cfg = config.load()
    return _cfg


def get_store_product_service():
    config = get_config()
    product_cfg = config["store_es"]
    return ProductService(
        product_cfg["host"],
        product_cfg["port"],
        product_cfg["user"],
        product_cfg["password"],
    )


def get_product_service():
    config = get_config()
    product_cfg = config["product_service"]
    return ProductService(
        product_cfg["host"],
        product_cfg["port"],
        product_cfg["user"],
        product_cfg["password"],
    )


def get_offer_service():
    config = get_config()
    offer_cfg = config["offer_service"]
    return EsOfferService(
        offer_cfg["host"],
        offer_cfg["port"],
        offer_cfg["user"],
        offer_cfg["password"],
    )


def get_offer_service_config():
    return get_config()["offer_service"]


def get_broker_url():
    from amazon_spapi.config.env import get_broker_url as _get_broker_url

    return _get_broker_url()


def get_emp_offer_filter_config(marketplace):
    filter_cond = {
        "rating": 60,
        "feedback": 5,
        "domestic": True,
        "shipping_time": 7,
        "subcondition": 70,
        "expire_hour": 120,
    }
    config = get_config()
    amz_offer_filter_cfg = config.get(
        "emp.offer.filter.{}".format(marketplace),
        config.get("emp.offer.filter", None),
    )
    if amz_offer_filter_cfg:
        filter_cond = {
            "rating": int(amz_offer_filter_cfg.get("rating", 60)),
            "feedback": int(amz_offer_filter_cfg.get("feedback", 5)),
            "domestic": bool(amz_offer_filter_cfg.get("domestic", True)),
            "shipping_time": int(amz_offer_filter_cfg.get("shipping_time", 7)),
            "subcondition": int(amz_offer_filter_cfg.get("subcondition", 70)),
            "expire_hour": int(amz_offer_filter_cfg.get("expire_hour", 120)),
        }
    return filter_cond


def get_amz_offer_filter_config(marketplace):
    filter_cond = {
        "rating": 60,
        "feedback": 5,
        "domestic": True,
        "shipping_time": 7,
        "subcondition": 70,
        "expire_hour": 120,
    }
    config = get_config()
    amz_offer_filter_cfg = config.get(
        "amz.offer.filter.{}".format(marketplace),
        config.get("amz.offer.filter", None),
    )
    if amz_offer_filter_cfg:
        filter_cond = {
            "rating": int(amz_offer_filter_cfg.get("rating", 60)),
            "feedback": int(amz_offer_filter_cfg.get("feedback", 5)),
            "domestic": bool(amz_offer_filter_cfg.get("domestic", True)),
            "shipping_time": int(amz_offer_filter_cfg.get("shipping_time", 7)),
            "subcondition": int(amz_offer_filter_cfg.get("subcondition", 70)),
            "expire_hour": int(amz_offer_filter_cfg.get("expire_hour", 120)),
        }
    return filter_cond


def get_spapi():
    config = get_config()
    spapi_cfg = config["spapi"]
    credentials = {
        "refresh_token": spapi_cfg["lwa_refresh_token"],
        "lwa_app_id": spapi_cfg["lwa_client_id"],
        "lwa_client_secret": spapi_cfg["lwa_client_secret"],
        "aws_access_key": spapi_cfg["aws_access_key"],
        "aws_secret_key": spapi_cfg["aws_secret_key"],
    }
    return Spapi(credentials)


def get_scrapy_workers():
    workers = []
    config = get_config()
    for k, v in config.items():
        if not k.startswith("scrapyd.worker"):
            continue
        projects = {}
        for proj in v["project"].split(","):
            proj = proj.strip()
            parts = proj.split(":")
            if len(parts) < 2:
                continue
            proj_name = parts[0]
            projects.setdefault(proj_name, [])
            spider_name = parts[-1]
            if spider_name not in projects[proj_name]:
                projects[proj_name].append(spider_name)
        workers.append(
            {
                "url": v["url"],
                "project": projects,
                "username": v["username"],
                "password": v["password"],
            }
        )
    return workers


def get_bot():
    config = get_config()
    telegram_cfg = config.get("telegram", {})
    token = (
        os.getenv("TELEGRAM_BOT_TOKEN")
        or telegram_cfg.get("bot_token")
        or telegram_cfg.get("api_token")
    )
    if not token:
        return None
    return TelegramBot(token)


def get_group_chat_id():
    config = get_config()
    telegram_cfg = config.get("telegram", {})
    chat_id = (
        os.getenv("TELEGRAM_GROUP_CHAT_ID")
        or telegram_cfg.get("group_chat_id")
        or telegram_cfg.get("chat_id")
    )
    return chat_id


sentry_enabled = False
_sentry_initialized = False


def init_sentry():
    global _sentry_initialized, sentry_enabled
    if _sentry_initialized:
        return
    _sentry_initialized = True
    _sentry_cfg = get_config().get("sentry", {})
    _dsn = _sentry_cfg.get("dsn", None)
    if not _dsn:
        return
    _traces_sample_rate = _sentry_cfg.get("traces_sample_rate", 0.5)
    _profiles_sample_rate = _sentry_cfg.get("profiles_sample_rate", 0.1)
    sentry_sdk.init(
        dsn=_dsn,
        traces_sample_rate=_traces_sample_rate,
        profiles_sample_rate=_profiles_sample_rate,
    )
    sentry_enabled = True
