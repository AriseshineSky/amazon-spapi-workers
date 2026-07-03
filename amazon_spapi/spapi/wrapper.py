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
    if getattr(cls, "_spapi_wrapped", False):
        return cls

    class_attrs = {"_spapi_wrapped": True, "status": dict()}

    if cls.__dict__.get("_DISPATCH", False):
        class_attrs["_DISPATCH"] = True
        class_attrs["_VERSION_MAP"] = {
            version: spapi_wrapper(impl) for version, impl in cls._VERSION_MAP.items()
        }
        class_attrs["_VERSION_ALIASES"] = dict(getattr(cls, "_VERSION_ALIASES", {}))
        class_attrs["_DEFAULT_VERSION"] = getattr(cls, "_DEFAULT_VERSION", None)

    class SpapiWrapperClass(cls):
        pass

    for name, value in class_attrs.items():
        setattr(SpapiWrapperClass, name, value)

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
        super(SpapiWrapperClass, self).__init__(
            marketplace=get_marketplace(marketplace),
            refresh_token=refresh_token,
            account=account,
            credentials=credentials,
            restricted_data_token=restricted_data_token,
            **kwargs,
        )

    def is_active(self, marketplace_id):
        return self.__class__.status.get(self.credentials.refresh_token, {}).get(
            marketplace_id, True
        )

    def deactivate(self, marketplace_id, reason=""):
        if not self.is_active(marketplace_id):
            return
        if self.credentials.refresh_token not in self.__class__.status:
            self.__class__.status[self.credentials.refresh_token] = {}
        self.__class__.status[self.credentials.refresh_token][marketplace_id] = False

    SpapiWrapperClass.__init__ = __init__
    SpapiWrapperClass.is_active = is_active
    SpapiWrapperClass.deactivate = deactivate
    SpapiWrapperClass.__name__ = cls.__name__
    SpapiWrapperClass.__qualname__ = cls.__qualname__
    return SpapiWrapperClass
