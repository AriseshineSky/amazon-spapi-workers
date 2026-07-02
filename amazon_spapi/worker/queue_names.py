# -*- coding: utf-8 -*-
"""Queue names shared by producers and workers (deployment contract)."""


def marketplace_offers_queue(marketplace):
    return "SpapiItemOffersUpdate_{}".format(marketplace.upper())


def marketplace_catalog_queue(marketplace):
    return "SpapiCatalogItemsUpdate_{}".format(marketplace.upper())
