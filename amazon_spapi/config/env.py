# -*- coding: utf-8 -*-
"""Environment-based configuration (12-factor)."""

import os

_BROKER_ENV_KEYS = ("BROKER_URL", "CELERY_BROKER_URL")


class MissingEnvError(RuntimeError):
    """Raised when a required environment variable is not set."""


def getenv_one_of(*names, required=True):
    """Return the first non-empty value among ``names``."""
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    if required:
        raise MissingEnvError(
            "Missing required environment variable: " + " or ".join(names)
        )
    return ""


def get_broker_url():
    """Celery/Redis broker URL from ``BROKER_URL`` or ``CELERY_BROKER_URL``."""
    return getenv_one_of(*_BROKER_ENV_KEYS)
