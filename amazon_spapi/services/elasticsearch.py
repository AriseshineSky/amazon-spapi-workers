# -*- coding: utf-8 -*-
"""Elasticsearch retry decorator."""

from __future__ import absolute_import

import time
from functools import wraps

from elasticsearch.exceptions import (
    AuthenticationException,
    AuthorizationException,
    ConnectionError,
    ConnectionTimeout,
    ElasticsearchException,
    ImproperlyConfigured,
    NotFoundError,
    RequestError,
    SSLError,
    TransportError,
)


class EsServerError(Exception):
    pass


class EsClientError(Exception):
    pass


class EsUnauthorizedError(Exception):
    pass


def es_retry(func):
    @wraps(func)
    def wrapper_es_retry(*args, **kwargs):
        val = None
        num_retries = 3

        while num_retries > 0:
            try:
                val = func(*args, **kwargs)
                break
            except NotFoundError:
                break
            except RequestError as e:
                raise EsClientError(str(e)) from e
            except (
                ImproperlyConfigured,
                AuthenticationException,
                AuthorizationException,
            ) as e:
                raise EsUnauthorizedError(str(e)) from e
            except (
                ConnectionTimeout,
                ConnectionError,
                SSLError,
                TransportError,
            ) as e:
                num_retries -= 1
                if num_retries <= 0:
                    raise EsServerError(str(e)) from e
                time.sleep(1)
            except ElasticsearchException as e:
                num_retries -= 1
                if num_retries <= 0:
                    raise e
                status_code = getattr(e, "status_code", None)
                if status_code == "N/A":
                    time.sleep(1)
            except Exception as e:
                num_retries -= 1
                if num_retries <= 0:
                    raise e

        return val

    return wrapper_es_retry
