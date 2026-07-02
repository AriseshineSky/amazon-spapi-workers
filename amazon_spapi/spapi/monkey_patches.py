# -*- coding: utf-8
"""Monkey patches applied to python-amazon-sp-api."""

from wrapt import patch_function_wrapper
from sp_api.base.client import Client
from sp_api.base.marketplaces import Marketplaces

from sp_api.base.exceptions import SellingApiBadRequestException

from amazon_spapi.spapi.exceptions import SellingApiInvalidAsinException


@patch_function_wrapper(Client, "_request")
def _request(wrapped, instance, args, kwargs):
    try:
        return wrapped(*args, **kwargs)
    except SellingApiBadRequestException as e:
        if "invalid ASIN" in e.message:
            raise SellingApiInvalidAsinException(e.error, e.headers) from e


def from_marketplace_id(marketplace_id):
    for marketplace in Marketplaces:
        if marketplace.marketplace_id == marketplace_id:
            return marketplace
    return None
