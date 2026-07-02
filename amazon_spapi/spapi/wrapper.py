# -*- coding: utf-8
"""Retry wrapper for python-amazon-sp-api client classes."""

import os

from sp_api.base import Marketplaces


def get_marketplace(marketplace) -> Marketplaces:
    if isinstance(marketplace, Marketplaces):
        return marketplace
    try:
        return Marketplaces[str(marketplace).upper()]
    except (NameError, KeyError) as e:
        raise ValueError("Unsupported marketplace: {}".format(marketplace)) from e


def spapi_wrapper(cls):
    class SpapiWrapperClass(cls):
        status = dict()

        def __init__(
            self,
            marketplace=Marketplaces[
                os.environ.get("SP_API_DEFAULT_MARKETPLACE", Marketplaces.US.name)
            ],
            *,
            refresh_token=None,
            account="default",
            credentials=None,
            restricted_data_token=None,
            **kwargs,
        ):
            super().__init__(
                marketplace=get_marketplace(marketplace),
                refresh_token=refresh_token,
                account=account,
                credentials=credentials,
                restricted_data_token=restricted_data_token,
                **kwargs,
            )

        def is_active(self, marketplace_id):
            return self.__class__.status.get(
                self.credentials.refresh_token, {}
            ).get(marketplace_id, True)

        def deactivate(self, marketplace_id, reason=""):
            if not self.is_active(marketplace_id):
                return
            if self.credentials.refresh_token not in self.__class__.status:
                self.__class__.status[self.credentials.refresh_token] = {}
            self.__class__.status[self.credentials.refresh_token][
                marketplace_id
            ] = False

    return SpapiWrapperClass
