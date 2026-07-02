# -*- coding: utf-8 -*-
"""Tests for worker layout from environment variables."""

import os

import pytest

from amazon_spapi.config.workers import (
    DEFAULT_CATALOG_TASK_RATE,
    DEFAULT_OFFERS_TASK_RATE,
    ENV_CATALOG_CONCURRENCY,
    ENV_CATALOG_MARKETPLACES,
    ENV_CATALOG_QUEUES,
    ENV_CATALOG_WORKER_NAME,
    ENV_OFFERS_CONCURRENCY,
    ENV_OFFERS_MARKETPLACES,
    ENV_OFFERS_QUEUES,
    ENV_OFFERS_WORKER_NAME,
    default_worker_name,
    get_task_rate_limits,
    load_workers_config,
    load_workers_config_from_env,
)


@pytest.fixture
def clean_worker_env(monkeypatch):
    for key in list(os.environ):
        if key.startswith(("OFFERS_", "CATALOG_", "FETCH_PRODUCTS_")):
            monkeypatch.delenv(key, raising=False)


def test_load_workers_config_from_env_marketplaces(clean_worker_env, monkeypatch):
    monkeypatch.setenv(ENV_OFFERS_MARKETPLACES, " us, ca ,mx")
    monkeypatch.setenv(ENV_CATALOG_MARKETPLACES, "us")
    monkeypatch.setenv(ENV_OFFERS_CONCURRENCY, "3")
    monkeypatch.setenv(ENV_CATALOG_CONCURRENCY, "2")
    monkeypatch.setenv(ENV_OFFERS_WORKER_NAME, "my-offers")
    monkeypatch.setenv(ENV_CATALOG_WORKER_NAME, "")

    workers = load_workers_config_from_env()

    assert workers.offer_marketplaces == ("us", "ca", "mx")
    assert workers.catalog_marketplaces == ("us",)
    assert workers.offers_concurrency == 3
    assert workers.catalog_concurrency == 2
    assert workers.resolved_offers_worker_name() == "my-offers"
    assert workers.resolved_catalog_worker_name() == "catalog-us"
    assert workers.offer_queues == (
        "SpapiItemOffersUpdate_US",
        "SpapiItemOffersUpdate_CA",
        "SpapiItemOffersUpdate_MX",
    )


def test_load_workers_config_from_explicit_queues(clean_worker_env, monkeypatch):
    monkeypatch.setenv(
        ENV_OFFERS_QUEUES,
        "SpapiItemOffersUpdate_US,SpapiItemOffersUpdate_CA",
    )
    monkeypatch.setenv(
        ENV_CATALOG_QUEUES,
        "SpapiCatalogItemsUpdate_MX",
    )

    workers = load_workers_config_from_env()

    assert workers.offer_queues == (
        "SpapiItemOffersUpdate_US",
        "SpapiItemOffersUpdate_CA",
    )
    assert workers.catalog_queues == ("SpapiCatalogItemsUpdate_MX",)


def test_default_worker_name_multi_market():
    assert default_worker_name("offers", ("us", "ca")) == "offers-us-ca"


def test_get_task_rate_limits_from_env(clean_worker_env, monkeypatch):
    monkeypatch.setenv(ENV_OFFERS_MARKETPLACES, "us")
    monkeypatch.setenv(ENV_CATALOG_MARKETPLACES, "us")

    limits = get_task_rate_limits()
    assert (
        limits["amazon_spapi.jobs.refresh_offers.refresh_offers"]["rate_limit"]
        == DEFAULT_OFFERS_TASK_RATE
    )
    assert (
        limits["amazon_spapi.jobs.refresh_catalog.refresh_catalog"]["rate_limit"]
        == DEFAULT_CATALOG_TASK_RATE
    )


def test_load_workers_config_delegates_to_env(clean_worker_env, monkeypatch):
    monkeypatch.setenv(ENV_OFFERS_MARKETPLACES, "us")

    workers = load_workers_config()
    assert workers.offer_marketplaces == ("us",)
